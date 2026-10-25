from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# py_modules.plugin imports decky, which only exists inside decky-loader.
# Replace it with a tiny fake before importing the backend.
fake_decky = types.ModuleType("decky")
fake_decky.DECKY_PLUGIN_SETTINGS_DIR = tempfile.mkdtemp(prefix="navidrome-settings-")
fake_decky.DECKY_PLUGIN_RUNTIME_DIR = tempfile.mkdtemp(prefix="navidrome-runtime-")
fake_decky.logger = logging.getLogger("fake-decky")


async def _emit(*_args, **_kwargs) -> None:
    return


fake_decky.emit = _emit
sys.modules["decky"] = fake_decky

from py_modules.cache import CacheManager  # noqa: E402
from py_modules.config import SettingsStore  # noqa: E402
from py_modules.plugin import NavidromePlugin  # noqa: E402


class FakeDownloads:
    def __init__(self) -> None:
        self.enqueued: list[tuple[list[dict], bool]] = []
        self.prefetched: list[dict] = []

    def enqueue(self, songs: list[dict], pinned: bool) -> dict[str, int]:
        self.enqueued.append((songs, pinned))
        return {"queued": len(songs), "skipped": 0}

    def prefetch(self, song: dict) -> bool:
        self.prefetched.append(song)
        return True


class FakeServer:
    base_url = "http://127.0.0.1:1234/m/test-token"


def song(song_id: str) -> dict:
    return {
        "id": song_id,
        "title": f"Song {song_id}",
        "artist": "Artist",
        "album": "Album",
        "albumId": "album",
        "coverArt": "cover",
        "duration": 100,
        "suffix": "mp3",
        "track": 1,
        "year": 2025,
    }


class PluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = NavidromePlugin()
        self.plugin._settings = SettingsStore(self._tmp.name)
        self.plugin._settings.save(
            {
                "server_url": "http://music.local:4533",
                "username": "yan",
                "password": "secret",
            }
        )
        self.plugin._cache = CacheManager(self._tmp.name + "/cache", 10 * 1024 * 1024)
        self.plugin._downloads = FakeDownloads()
        self.plugin._server = FakeServer()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def test_settings_are_public_and_flagged_configured(self) -> None:
        settings = self.run_async(self.plugin.get_settings())
        self.assertTrue(settings["configured"])
        self.assertEqual(settings["server_url"], "http://music.local:4533")

    def test_song_decoration_uses_cache_manifest(self) -> None:
        temp = self.plugin._cache.new_temp_path("one")
        with open(temp, "wb") as fh:
            fh.write(b"abc")
        self.plugin._cache.put(song("one"), temp, pinned=True)
        decorated = self.plugin._decorate_song(song("one"))
        self.assertTrue(decorated["isCached"])
        self.assertTrue(decorated["isDownloaded"])
        self.assertEqual(decorated["sizeBytes"], 3)

    def test_download_pins_cached_and_queues_missing(self) -> None:
        temp = self.plugin._cache.new_temp_path("cached")
        with open(temp, "wb") as fh:
            fh.write(b"abc")
        self.plugin._cache.put(song("cached"), temp, pinned=False)

        result = self.run_async(
            self.plugin.download_songs([song("cached"), song("new")])
        )
        self.assertEqual(result, {"queued": 1, "skipped": 1})
        self.assertTrue(self.plugin._cache.peek("cached")["pinned"])
        queued, pinned = self.plugin._downloads.enqueued[-1]
        self.assertEqual([item["id"] for item in queued], ["new"])
        self.assertTrue(pinned)

    def test_prefetch_respects_cache_setting(self) -> None:
        self.assertTrue(self.run_async(self.plugin.prefetch_song(song("song"))))
        self.plugin._settings.update(cache_played_songs=False)
        self.assertFalse(self.run_async(self.plugin.prefetch_song(song("song2"))))

    def test_media_urls_are_tokenized(self) -> None:
        stream = self.run_async(self.plugin.get_stream_url("a/b"))
        art = self.run_async(self.plugin.get_art_url("cover 1", 128))
        self.assertEqual(stream, "http://127.0.0.1:1234/m/test-token/stream/a%2Fb")
        self.assertEqual(
            art, "http://127.0.0.1:1234/m/test-token/art/cover%201?size=128"
        )

    def test_cache_stats_and_clear(self) -> None:
        temp = self.plugin._cache.new_temp_path("one")
        with open(temp, "wb") as fh:
            fh.write(b"abc")
        self.plugin._cache.put(song("one"), temp, pinned=True)
        stats = self.run_async(self.plugin.get_cache_stats())
        self.assertEqual(stats["pinnedCount"], 1)
        cleared = self.run_async(self.plugin.clear_cache(True))
        self.assertEqual(cleared["totalBytes"], 0)


if __name__ == "__main__":
    unittest.main()
