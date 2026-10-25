from __future__ import annotations

import json
import logging
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from py_modules.cache import CacheManager  # noqa: E402
from py_modules.server import LocalMediaServer, parse_range  # noqa: E402
from py_modules.subsonic import SubsonicError  # noqa: E402


class FakeResponse:
    def __init__(self, data: bytes, status: int = 200, headers: dict | None = None):
        self.status = status
        self.headers = headers or {}
        self._data = data
        self._offset = 0
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self) -> None:
        self.song_calls: list[tuple[str, str | None]] = []
        self.cover_calls: list[tuple[str, int]] = []

    def open_song(self, song_id: str, range_header: str | None = None):
        self.song_calls.append((song_id, range_header))
        if song_id == "missing":
            raise SubsonicError("Track not found")
        data = b"proxied-audio-data"
        if range_header == "bytes=0-3":
            return FakeResponse(
                data[:4],
                status=206,
                headers={
                    "Content-Type": "audio/mpeg",
                    "Content-Range": f"bytes 0-3/{len(data)}",
                    "Content-Length": "4",
                },
            )
        return FakeResponse(
            data,
            headers={
                "Content-Type": "audio/mpeg",
                "Content-Length": str(len(data)),
            },
        )

    def open_cover(self, cover_id: str, size: int = 300):
        self.cover_calls.append((cover_id, size))
        data = b"\xff\xd8cover"
        return FakeResponse(
            data,
            headers={"Content-Type": "image/jpeg", "Content-Length": str(len(data))},
        )


def song_meta(song_id: str) -> dict:
    return {
        "id": song_id,
        "title": f"Song {song_id}",
        "artist": "Artist",
        "album": "Album",
        "albumId": "album-1",
        "coverArt": "cover-1",
        "duration": 100,
        "suffix": "mp3",
        "track": 1,
        "year": 2025,
    }


class RangeTests(unittest.TestCase):
    def test_ranges(self) -> None:
        self.assertEqual(parse_range("bytes=0-3", 10), (0, 3))
        self.assertEqual(parse_range("bytes=5-", 10), (5, 9))
        self.assertEqual(parse_range("bytes=-3", 10), (7, 9))
        self.assertEqual(parse_range("bytes=8-99", 10), (8, 9))
        self.assertIsNone(parse_range("bytes=20-30", 10))
        self.assertIsNone(parse_range("bytes=abc", 10))
        self.assertIsNone(parse_range(None, 10))


class MediaServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = CacheManager(self._tmp.name, 10 * 1024 * 1024)
        self.client = FakeClient()
        self.server = LocalMediaServer(lambda: self.client, self.cache, logging.getLogger("test"))
        self.base = self.server.base_url

    def tearDown(self) -> None:
        self.server.stop()
        self._tmp.cleanup()

    def _cache_song(self, song_id: str, data: bytes) -> None:
        temp = self.cache.new_temp_path(song_id)
        with open(temp, "wb") as fh:
            fh.write(data)
        self.cache.put(song_meta(song_id), temp, pinned=False)

    def get(self, path: str, headers: dict | None = None, method: str = "GET"):
        request = urllib.request.Request(self.base + path, headers=headers or {}, method=method)
        return urllib.request.urlopen(request, timeout=5)

    def test_cached_stream_full_and_ranges(self) -> None:
        self._cache_song("cached", b"abcdefghij")
        with self.get("/stream/cached") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"abcdefghij")
            self.assertEqual(response.headers["Accept-Ranges"], "bytes")

        with self.get("/stream/cached", {"Range": "bytes=2-5"}) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), b"cdef")
            self.assertEqual(response.headers["Content-Range"], "bytes 2-5/10")

        with self.get("/stream/cached", {"Range": "bytes=-2"}) as response:
            self.assertEqual(response.read(), b"ij")

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/stream/cached", {"Range": "bytes=50-60"})
        self.assertEqual(ctx.exception.code, 416)
        self.assertEqual(ctx.exception.headers["Content-Range"], "bytes */10")
        ctx.exception.close()

    def test_head_has_no_body(self) -> None:
        self._cache_song("cached", b"abcdefghij")
        with self.get("/stream/cached", method="HEAD") as response:
            self.assertEqual(response.headers["Content-Length"], "10")
            self.assertEqual(response.read(), b"")

    def test_proxy_stream_and_range_forwarding(self) -> None:
        with self.get("/stream/proxy") as response:
            self.assertEqual(response.read(), b"proxied-audio-data")
        self.assertEqual(self.client.song_calls[-1], ("proxy", None))

        with self.get("/stream/proxy", {"Range": "bytes=0-3"}) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), b"prox")
            self.assertEqual(response.headers["Content-Range"], "bytes 0-3/18")
        self.assertEqual(self.client.song_calls[-1], ("proxy", "bytes=0-3"))

    def test_cover_proxy_size(self) -> None:
        with self.get("/art/cover-1?size=128") as response:
            self.assertEqual(response.headers["Content-Type"], "image/jpeg")
            self.assertEqual(response.read(), b"\xff\xd8cover")
        self.assertEqual(self.client.cover_calls[-1], ("cover-1", 128))

    def test_token_is_required(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/m/wrong-token/stream/cached")
        self.assertEqual(ctx.exception.code, 404)
        ctx.exception.close()

    def test_unknown_song_returns_502(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/stream/missing")
        self.assertEqual(ctx.exception.code, 502)
        body = json.loads(ctx.exception.read())
        self.assertIn("Track not found", body["error"])
        ctx.exception.close()


if __name__ == "__main__":
    unittest.main()
