from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from py_modules.cache import CacheError, CacheManager  # noqa: E402
from py_modules.config import (  # noqa: E402
    DEFAULT_CACHE_LIMIT_BYTES,
    SettingsStore,
    normalize_server_url,
    sanitize_settings,
)


def song(song_id: str, size: int = 60) -> dict:
    return {
        "id": song_id,
        "title": f"Song {song_id}",
        "artist": "Artist",
        "album": "Album",
        "albumId": "album-1",
        "coverArt": "cover-1",
        "duration": 200,
        "suffix": "mp3",
        "track": 1,
        "year": 2024,
        "size": size,
    }


class ConfigTests(unittest.TestCase):
    def test_normalize_urls(self) -> None:
        self.assertEqual(normalize_server_url("192.168.1.2:4533/"), "http://192.168.1.2:4533")
        self.assertEqual(
            normalize_server_url("https://music.example.com/sub/"),
            "https://music.example.com/sub",
        )
        self.assertEqual(normalize_server_url(""), "")

    def test_rejects_bad_urls(self) -> None:
        with self.assertRaises(ValueError):
            normalize_server_url("ftp://example.com")
        with self.assertRaises(ValueError):
            normalize_server_url("http://user:pass@example.com")

    def test_sanitize_defaults_and_limits(self) -> None:
        settings = sanitize_settings({})
        self.assertEqual(settings.cache_limit_bytes, DEFAULT_CACHE_LIMIT_BYTES)
        self.assertEqual(settings.max_bitrate, 0)
        self.assertTrue(settings.cache_played_songs)
        self.assertTrue(settings.show_playlists)
        self.assertFalse(settings.configured)

        hidden = sanitize_settings({"show_playlists": False})
        self.assertFalse(hidden.show_playlists)

        low = sanitize_settings({"cache_limit_bytes": 1})
        self.assertGreaterEqual(low.cache_limit_bytes, 64 * 1024 * 1024)
        bad_bitrate = sanitize_settings({"max_bitrate": 999})
        self.assertEqual(bad_bitrate.max_bitrate, 0)

    def test_settings_store_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SettingsStore(tmp)
            self.assertFalse(store.get().configured)
            saved = store.save(
                {
                    "server_url": "music.local:4533",
                    "username": "yan",
                    "password": "secret",
                    "cache_limit_bytes": 2 * 1024 * 1024 * 1024,
                    "cache_played_songs": False,
                    "show_playlists": False,
                    "max_bitrate": 192,
                }
            )
            self.assertTrue(saved.configured)
            self.assertEqual(saved.server_url, "http://music.local:4533")

            reloaded = SettingsStore(tmp).get()
            self.assertEqual(reloaded.username, "yan")
            self.assertEqual(reloaded.password, "secret")
            self.assertEqual(reloaded.max_bitrate, 192)
            self.assertFalse(reloaded.cache_played_songs)
            self.assertFalse(reloaded.show_playlists)


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.cache = CacheManager(self.root, 100)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _put(self, song_id: str, data: bytes, pinned: bool = False) -> dict:
        tmp_path = self.cache.new_temp_path(song_id)
        with open(tmp_path, "wb") as fh:
            fh.write(data)
        return self.cache.put(song(song_id), tmp_path, pinned=pinned)

    def test_put_and_read(self) -> None:
        entry = self._put("a", b"x" * 60)
        self.assertEqual(entry["size"], 60)
        self.assertTrue(self.cache.is_cached("a"))
        path = self.cache.local_path("a")
        self.assertIsNotNone(path)
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), b"x" * 60)

    def test_lru_eviction(self) -> None:
        self._put("old", b"a" * 60)
        self._put("new", b"b" * 60)
        self.assertFalse(self.cache.is_cached("old"))
        self.assertTrue(self.cache.is_cached("new"))
        stats = self.cache.stats()
        self.assertEqual(stats["totalBytes"], 60)
        self.assertFalse(stats["overLimit"])

    def test_pinned_survives_and_auto_is_dropped(self) -> None:
        self._put("keep", b"k" * 60, pinned=True)
        with self.assertRaises(CacheError):
            self._put("auto", b"a" * 60)
        self.assertTrue(self.cache.is_cached("keep"))
        self.assertFalse(self.cache.is_cached("auto"))
        self.assertEqual(self.cache.stats()["totalBytes"], 60)

    def test_pin_promotes_auto_entry(self) -> None:
        self._put("song", b"s" * 60)
        self.assertFalse(self.cache.peek("song")["pinned"])
        self.cache.pin("song")
        self.assertTrue(self.cache.peek("song")["pinned"])
        self.assertEqual(len(self.cache.pinned_songs()), 1)

    def test_manifest_persistence_and_missing_file(self) -> None:
        self._put("a", b"a" * 40, pinned=True)
        self._put("b", b"b" * 40)
        path = self.cache.local_path("b")
        os.unlink(path)
        reloaded = CacheManager(self.root, 100)
        self.assertTrue(reloaded.is_cached("a"))
        self.assertFalse(reloaded.is_cached("b"))

    def test_clear_keeps_downloads_unless_requested(self) -> None:
        self._put("auto", b"a" * 30)
        self._put("manual", b"m" * 30, pinned=True)
        stats = self.cache.clear(False)
        self.assertEqual(stats["totalBytes"], 30)
        self.assertEqual(stats["pinnedCount"], 1)
        stats = self.cache.clear(True)
        self.assertEqual(stats["totalBytes"], 0)

    def test_lower_limit_never_deletes_pinned(self) -> None:
        self._put("manual", b"m" * 80, pinned=True)
        self.cache.set_limit(10)
        self.assertTrue(self.cache.is_cached("manual"))
        self.assertTrue(self.cache.stats()["overLimit"])

    def test_replacing_same_song_keeps_one_file(self) -> None:
        self._put("same", b"a" * 20)
        self._put("same", b"b" * 20, pinned=True)
        files = os.listdir(self.cache.audio_dir)
        self.assertEqual(len(files), 1)
        self.assertTrue(self.cache.peek("same")["pinned"])


if __name__ == "__main__":
    unittest.main()
