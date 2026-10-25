"""Decky plugin backend for Navidrome Player."""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict
from typing import Any
from urllib.parse import quote

import decky

from .cache import CacheManager
from .config import SettingsStore
from .downloads import DownloadManager
from .server import LocalMediaServer
from .subsonic import SubsonicClient, SubsonicError


class NavidromePlugin:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._settings: SettingsStore | None = None
        self._cache: CacheManager | None = None
        self._server: LocalMediaServer | None = None
        self._downloads: DownloadManager | None = None

    # -------------------------------------------------------------- lifecycle
    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        settings_dir = decky.DECKY_PLUGIN_SETTINGS_DIR
        runtime_dir = decky.DECKY_PLUGIN_RUNTIME_DIR
        self._settings = SettingsStore(settings_dir)
        cache_root = os.path.join(runtime_dir, "cache")
        self._cache = CacheManager(cache_root, self._settings.get().cache_limit_bytes)
        self._server = LocalMediaServer(self._client_or_none, self._cache, decky.logger)
        self._server.start()
        self._downloads = DownloadManager(
            self._client_or_none, self._cache, self._notify, decky.logger
        )
        self._downloads.start()
        decky.logger.info("Navidrome Player started. Cache directory: %s", cache_root)

    async def _unload(self) -> None:
        if self._downloads:
            self._downloads.stop()
        if self._server:
            self._server.stop()
        self._loop = None
        decky.logger.info("Navidrome Player stopped")

    async def _uninstall(self) -> None:
        decky.logger.info("Navidrome Player uninstalled")

    async def _migration(self) -> None:
        # No legacy locations to migrate yet.
        return

    # ----------------------------------------------------------------- helpers
    def _settings_store(self) -> SettingsStore:
        if not self._settings:
            raise RuntimeError("Plugin is still starting")
        return self._settings

    def _cache_manager(self) -> CacheManager:
        if not self._cache:
            raise RuntimeError("Plugin is still starting")
        return self._cache

    def _client_or_none(self) -> SubsonicClient | None:
        settings = self._settings_store().get()
        if not settings.configured:
            return None
        return SubsonicClient(
            settings.server_url,
            settings.username,
            settings.password,
            max_bitrate=settings.max_bitrate,
        )

    def _require_client(self) -> SubsonicClient:
        client = self._client_or_none()
        if client is None:
            raise RuntimeError("Set your Navidrome server, username and password first")
        return client

    def _notify(self, event: str, payload: dict[str, Any]) -> None:
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(decky.emit(event, payload), loop)

    def _decorate_song(self, song: dict[str, Any]) -> dict[str, Any]:
        entry = self._cache_manager().peek(str(song.get("id") or ""))
        decorated = dict(song)
        decorated["isCached"] = entry is not None
        decorated["isDownloaded"] = bool(entry and entry.get("pinned"))
        if entry:
            decorated["sizeBytes"] = int(entry.get("size") or 0)
            decorated["pinned"] = bool(entry.get("pinned"))
        return decorated

    def _decorate_songs(self, songs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._decorate_song(song) for song in songs]

    # ---------------------------------------------------------------- settings
    def _public_settings(self, raw: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = self._settings_store().get()
        public = raw if raw is not None else asdict(settings)
        public["configured"] = settings.configured
        return public

    async def get_settings(self) -> dict[str, Any]:
        return self._public_settings()

    async def save_settings(self, raw: dict[str, Any]) -> dict[str, Any]:
        try:
            saved = self._settings_store().save(raw)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        self._cache_manager().set_limit(saved.cache_limit_bytes)
        decky.logger.info("Settings saved (server=%s, cache limit=%s)", saved.server_url, saved.cache_limit_bytes)
        return self._public_settings(asdict(saved))

    async def test_connection(self, raw: dict[str, Any]) -> dict[str, Any]:
        try:
            from .config import sanitize_settings

            settings = sanitize_settings(raw)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        if not settings.configured:
            return {"ok": False, "message": "Enter the server URL and a username first"}
        client = SubsonicClient(
            settings.server_url,
            settings.username,
            settings.password,
            max_bitrate=settings.max_bitrate,
        )
        try:
            body = await asyncio.to_thread(client.ping)
        except (SubsonicError, RuntimeError) as exc:
            return {"ok": False, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001 - surface any connection failure
            return {"ok": False, "message": str(exc)}
        version = body.get("version") or "unknown"
        return {
            "ok": True,
            "message": f"Connected to Navidrome (Subsonic API {version})",
            "serverVersion": str(version),
        }

    # ------------------------------------------------------------------- media
    async def get_media_base(self) -> str:
        if not self._server:
            raise RuntimeError("Plugin is still starting")
        return self._server.base_url

    async def get_stream_url(self, song_id: str) -> str:
        base = await self.get_media_base()
        return f"{base}/stream/{quote(str(song_id), safe='')}"

    async def get_art_url(self, cover_id: str, size: int = 300) -> str:
        if not cover_id:
            return ""
        base = await self.get_media_base()
        return f"{base}/art/{quote(str(cover_id), safe='')}?size={int(size)}"

    # ----------------------------------------------------------------- library
    async def get_random_songs(self, size: int = 30) -> list[dict[str, Any]]:
        client = self._require_client()
        songs = await asyncio.to_thread(client.get_random_songs, size)
        return self._decorate_songs(songs)

    async def get_playlists(self) -> list[dict[str, Any]]:
        client = self._require_client()
        return await asyncio.to_thread(client.get_playlists)

    async def get_playlist_songs(self, playlist_id: str) -> list[dict[str, Any]]:
        client = self._require_client()
        songs = await asyncio.to_thread(client.get_playlist_songs, playlist_id)
        return self._decorate_songs(songs)

    async def get_albums(
        self, kind: str = "random", size: int = 30, offset: int = 0
    ) -> list[dict[str, Any]]:
        client = self._require_client()
        return await asyncio.to_thread(client.get_albums, kind, size, offset)

    async def get_album_songs(self, album_id: str) -> list[dict[str, Any]]:
        client = self._require_client()
        songs = await asyncio.to_thread(client.get_album_songs, album_id)
        return self._decorate_songs(songs)

    async def search(self, query: str) -> dict[str, Any]:
        client = self._require_client()
        trimmed = str(query or "").strip()
        if not trimmed:
            return {"songs": [], "albums": []}
        result = await asyncio.to_thread(client.search, trimmed)
        result["songs"] = self._decorate_songs(result["songs"])
        return result

    # --------------------------------------------------------------- downloads
    async def download_songs(self, songs: list[dict[str, Any]]) -> dict[str, int]:
        if not isinstance(songs, list) or not songs:
            return {"queued": 0, "skipped": 0}
        self._require_client()
        if self._downloads is None:
            raise RuntimeError("Download queue is still starting")

        cache = self._cache_manager()
        to_queue: list[dict[str, Any]] = []
        skipped = 0
        for song in songs[:1000]:
            if not isinstance(song, dict) or not song.get("id"):
                skipped += 1
                continue
            entry = cache.peek(str(song["id"]))
            if entry:
                if not entry.get("pinned"):
                    cache.pin(str(song["id"]))
                skipped += 1
                continue
            to_queue.append(song)

        result = self._downloads.enqueue(to_queue, pinned=True)
        return {
            "queued": result["queued"],
            "skipped": skipped + result["skipped"],
        }

    async def prefetch_song(self, song: dict[str, Any]) -> bool:
        settings = self._settings_store().get()
        if not settings.cache_played_songs or not settings.configured:
            return False
        if not isinstance(song, dict) or not song.get("id"):
            return False
        song_id = str(song["id"])
        if self._cache_manager().peek(song_id):
            return False
        if self._downloads is None:
            return False
        return self._downloads.prefetch(song)

    async def get_downloads(self) -> list[dict[str, Any]]:
        songs = self._cache_manager().pinned_songs()
        for song in songs:
            song["isCached"] = True
            song["isDownloaded"] = True
        return songs

    async def delete_download(self, song_id: str) -> bool:
        return self._cache_manager().remove(str(song_id))

    async def get_cache_stats(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._cache_manager().stats)

    async def set_cache_limit(self, limit_bytes: int) -> dict[str, Any]:
        settings = self._settings_store().update(cache_limit_bytes=limit_bytes)
        self._cache_manager().set_limit(settings.cache_limit_bytes)
        return self._cache_manager().stats()

    async def clear_cache(self, include_downloads: bool = False) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._cache_manager().clear, bool(include_downloads)
        )

    async def report_play(self, song_id: str) -> None:
        try:
            await asyncio.to_thread(self._require_client().scrobble, str(song_id))
        except Exception as exc:  # noqa: BLE001 - scrobbling is best-effort
            decky.logger.debug("Scrobble failed for %s: %s", song_id, exc)
