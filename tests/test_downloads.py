from __future__ import annotations

import logging
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from py_modules.cache import CacheManager  # noqa: E402
from py_modules.downloads import DownloadManager  # noqa: E402
from py_modules.subsonic import SubsonicError  # noqa: E402


class FakeResponse:
    def __init__(self, data: bytes):
        self.headers = {"Content-Length": str(len(data))}
        self._data = data
        self._offset = 0
        self.status = 200

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        return


class FakeClient:
    def open_song(self, song_id: str, range_header: str | None = None):
        if song_id == "bad":
            raise SubsonicError("Server unavailable")
        return FakeResponse(b"audio-" + song_id.encode())


def song(song_id: str) -> dict:
    return {
        "id": song_id,
        "title": f"Song {song_id}",
        "artist": "Artist",
        "album": "Album",
        "albumId": "album",
        "coverArt": "cover",
        "duration": 120,
        "suffix": "mp3",
        "track": 1,
        "year": 2025,
    }


def wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class DownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = CacheManager(self._tmp.name, 10 * 1024 * 1024)
        self.events: list[tuple[str, dict]] = []
        self.client = FakeClient()
        self.manager = DownloadManager(
            lambda: self.client,
            self.cache,
            lambda event, payload: self.events.append((event, payload)),
            logging.getLogger("test"),
        )
        self.manager.start()

    def tearDown(self) -> None:
        self.manager.stop()
        self._tmp.cleanup()

    def test_manual_download_is_pinned(self) -> None:
        result = self.manager.enqueue([song("one")], pinned=True)
        self.assertEqual(result["queued"], 1)
        # Wait for the completion event, not just the file: the manifest is
        # written just before the worker emits download_complete.
        self.assertTrue(
            wait_for(lambda: any(event == "download_complete" for event, _ in self.events))
        )
        self.assertTrue(self.cache.is_cached("one"))
        entry = self.cache.peek("one")
        self.assertTrue(entry["pinned"])
        self.assertEqual(entry["title"], "Song one")
        progress = [payload for event, payload in self.events if event == "download_progress"]
        self.assertTrue(progress)
        self.assertEqual(progress[-1]["percent"], 100)

    def test_auto_cache_not_pinned_and_duplicate_prefetch_ignored(self) -> None:
        self.assertTrue(self.manager.prefetch(song("auto")))
        self.assertTrue(wait_for(lambda: self.cache.is_cached("auto")))
        self.assertFalse(self.cache.peek("auto")["pinned"])
        self.assertFalse(self.manager.prefetch(song("auto")))

    def test_manual_download_pins_already_auto_cached(self) -> None:
        self.manager.prefetch(song("promote"))
        self.assertTrue(wait_for(lambda: self.cache.is_cached("promote")))
        result = self.manager.enqueue([song("promote")], pinned=True)
        self.assertEqual(result["queued"], 0)
        self.assertTrue(wait_for(lambda: self.cache.peek("promote")["pinned"]))

    def test_failure_reports_pinned_flag(self) -> None:
        self.manager.enqueue([song("bad")], pinned=True)
        self.assertTrue(wait_for(lambda: any(event == "download_failed" for event, _ in self.events)))
        failures = [payload for event, payload in self.events if event == "download_failed"]
        self.assertTrue(failures[-1]["pinned"])
        self.assertIn("Server unavailable", failures[-1]["error"])
        self.assertFalse(self.cache.is_cached("bad"))


if __name__ == "__main__":
    unittest.main()
