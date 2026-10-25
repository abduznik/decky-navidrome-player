from __future__ import annotations

import hashlib
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from py_modules.subsonic import SubsonicClient, SubsonicError  # noqa: E402

USER = "yan"
PASSWORD = "hunter2"
SONG = {
    "id": "song-1",
    "title": "Test Song",
    "artist": "Artist",
    "album": "Album",
    "albumId": "album-1",
    "coverArt": "cover-1",
    "duration": 180,
    "suffix": "flac",
    "track": 3,
    "year": 2025,
    "size": 12345,
}


class FakeNavidrome(BaseHTTPRequestHandler):
    requests: list[tuple[str, dict[str, list[str]], dict[str, str]]] = []

    def log_message(self, *_args) -> None:  # silence test output
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        self.requests.append((parsed.path, query, dict(self.headers)))
        endpoint = parsed.path.rsplit("/", 1)[-1].replace(".view", "")

        salt = query.get("s", [""])[0]
        expected_token = hashlib.md5((PASSWORD + salt).encode()).hexdigest()
        if query.get("u", [""])[0] != USER or query.get("t", [""])[0] != expected_token:
            return self._json({"subsonic-response": {"status": "failed", "error": {"code": 40, "message": "Wrong username or password"}}})

        if endpoint == "stream":
            data = b"0123456789"
            range_header = self.headers.get("Range")
            if range_header == "bytes=2-5":
                self.send_response(206)
                self.send_header("Content-Type", "audio/flac")
                self.send_header("Content-Range", "bytes 2-5/10")
                self.send_header("Content-Length", "4")
                self.end_headers()
                self.wfile.write(data[2:6])
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/flac")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if endpoint == "getCoverArt":
            data = b"\xff\xd8fakejpeg"
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if endpoint == "ping":
            payload = {"subsonic-response": {"status": "ok", "version": "1.16.1"}}
        elif endpoint == "getRandomSongs":
            payload = {"subsonic-response": {"status": "ok", "randomSongs": {"song": [SONG]}}}
        elif endpoint == "getPlaylists":
            payload = {
                "subsonic-response": {
                    "status": "ok",
                    "playlists": {
                        "playlist": [
                            {"id": "pl-1", "name": "Favorites", "songCount": 4, "duration": 600}
                        ]
                    },
                }
            }
        elif endpoint == "getPlaylist":
            payload = {
                "subsonic-response": {
                    "status": "ok",
                    "playlist": {"id": "pl-1", "entry": [SONG]},
                }
            }
        elif endpoint == "getAlbumList2":
            payload = {
                "subsonic-response": {
                    "status": "ok",
                    "albumList2": {
                        "album": [
                            {
                                "id": "album-1",
                                "name": "Album",
                                "artist": "Artist",
                                "songCount": 10,
                                "duration": 3000,
                                "year": 2025,
                                "coverArt": "cover-1",
                            }
                        ]
                    },
                }
            }
        elif endpoint == "getAlbum":
            payload = {
                "subsonic-response": {
                    "status": "ok",
                    "album": {"id": "album-1", "name": "Album", "song": [SONG]},
                }
            }
        elif endpoint == "search3":
            payload = {
                "subsonic-response": {
                    "status": "ok",
                    "searchResult3": {"song": [SONG], "album": []},
                }
            }
        elif endpoint == "scrobble":
            payload = {"subsonic-response": {"status": "ok"}}
        else:
            payload = {"subsonic-response": {"status": "ok"}}
        self._json(payload)

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class SubsonicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        FakeNavidrome.requests = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeNavidrome)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def client(self) -> SubsonicClient:
        return SubsonicClient(self.base, USER, PASSWORD)

    def test_token_auth_is_used(self) -> None:
        self.client().ping()
        _path, query, _headers = FakeNavidrome.requests[-1]
        salt = query["s"][0]
        expected = hashlib.md5((PASSWORD + salt).encode()).hexdigest()
        self.assertEqual(query["t"][0], expected)
        self.assertNotIn(PASSWORD, json.dumps(query))
        self.assertEqual(query["v"][0], "1.16.1")
        self.assertEqual(query["f"][0], "json")

    def test_data_endpoints_map_to_camel_case(self) -> None:
        songs = self.client().get_random_songs(12)
        self.assertEqual(songs[0]["id"], "song-1")
        self.assertEqual(songs[0]["albumId"], "album-1")
        self.assertEqual(songs[0]["duration"], 180)
        self.assertEqual(songs[0]["suffix"], "flac")

        playlists = self.client().get_playlists()
        self.assertEqual(playlists[0]["name"], "Favorites")
        self.assertEqual(playlists[0]["songCount"], 4)

        albums = self.client().get_albums("newest", 10, 0)
        self.assertEqual(albums[0]["name"], "Album")
        self.assertEqual(albums[0]["artist"], "Artist")
        for kind in ("newest", "recent", "frequent", "random"):
            self.client().get_albums(kind, 10, 0)
            _path, query, _headers = FakeNavidrome.requests[-1]
            self.assertEqual(query["type"][0], kind)

        result = self.client().search("test")
        self.assertEqual(result["songs"][0]["title"], "Test Song")
        self.assertEqual(self.client().get_album_songs("album-1")[0]["id"], "song-1")
        self.assertEqual(self.client().get_playlist_songs("pl-1")[0]["id"], "song-1")

    def test_error_is_raised(self) -> None:
        client = SubsonicClient(self.base, "wrong", PASSWORD)
        with self.assertRaises(SubsonicError) as ctx:
            client.ping()
        self.assertIn("Wrong username", str(ctx.exception))

    def test_stream_forwards_range(self) -> None:
        response = self.client().open_song("song-1", "bytes=2-5")
        try:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), b"2345")
            _path, _query, headers = FakeNavidrome.requests[-1]
            self.assertEqual(headers.get("Range"), "bytes=2-5")
        finally:
            response.close()

    def test_cover_request_uses_size(self) -> None:
        response = self.client().open_cover("cover-1", 128)
        try:
            self.assertEqual(response.read(), b"\xff\xd8fakejpeg")
            _path, query, _headers = FakeNavidrome.requests[-1]
            self.assertEqual(query["size"][0], "128")
        finally:
            response.close()


if __name__ == "__main__":
    unittest.main()
