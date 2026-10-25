"""Persistent settings for the Navidrome Player plugin.

Everything here is pure standard library so the plugin runs unchanged on
x86_64 and arm64 Decky installations.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

DEFAULT_CACHE_LIMIT_BYTES = 1024 * 1024 * 1024  # 1 GiB
MIN_CACHE_LIMIT_BYTES = 64 * 1024 * 1024
MAX_CACHE_LIMIT_BYTES = 512 * 1024 * 1024 * 1024

ALLOWED_BITRATES = (0, 64, 96, 128, 192, 256, 320)


class SettingsError(ValueError):
    """Raised when the user supplies invalid settings."""


@dataclass
class Settings:
    server_url: str = ""
    username: str = ""
    password: str = ""
    cache_limit_bytes: int = DEFAULT_CACHE_LIMIT_BYTES
    cache_played_songs: bool = True
    show_playlists: bool = True
    max_bitrate: int = 0

    @property
    def configured(self) -> bool:
        return bool(self.server_url and self.username)


def normalize_server_url(value: str) -> str:
    """Return a canonical base URL or raise SettingsError."""
    url = (value or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SettingsError("Server URL must start with http:// or https://")
    if not parsed.hostname:
        raise SettingsError("Server URL is missing a hostname")
    if parsed.username or parsed.password:
        raise SettingsError("Do not put credentials inside the server URL")
    # Navidrome endpoints live under the root, but reverse proxies may mount
    # them under a sub-path, so keep the path and only drop trailing slashes.
    path = parsed.path.rstrip("/")
    netloc = parsed.netloc
    return f"{parsed.scheme}://{netloc}{path}"


def clamp_cache_limit(value: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = DEFAULT_CACHE_LIMIT_BYTES
    return max(MIN_CACHE_LIMIT_BYTES, min(MAX_CACHE_LIMIT_BYTES, value))


def sanitize_settings(raw: dict) -> Settings:
    if not isinstance(raw, dict):
        raise SettingsError("Settings must be an object")

    bitrate = raw.get("max_bitrate", 0)
    try:
        bitrate = int(bitrate)
    except (TypeError, ValueError):
        bitrate = 0
    if bitrate not in ALLOWED_BITRATES:
        bitrate = 0

    return Settings(
        server_url=normalize_server_url(str(raw.get("server_url", ""))),
        username=str(raw.get("username", "")).strip(),
        password=str(raw.get("password", "")),
        cache_limit_bytes=clamp_cache_limit(
            raw.get("cache_limit_bytes", DEFAULT_CACHE_LIMIT_BYTES)
        ),
        cache_played_songs=bool(raw.get("cache_played_songs", True)),
        show_playlists=bool(raw.get("show_playlists", True)),
        max_bitrate=bitrate,
    )


class SettingsStore:
    def __init__(self, settings_dir: str):
        self._path = os.path.join(settings_dir, "settings.json")
        self._lock = threading.RLock()
        os.makedirs(settings_dir, exist_ok=True)
        self._settings = self._load()

    def _load(self) -> Settings:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                return sanitize_settings(json.load(fh))
        except FileNotFoundError:
            return Settings()
        except (OSError, ValueError, SettingsError):
            # Corrupt settings should never prevent the plugin from loading.
            return Settings()

    def get(self) -> Settings:
        with self._lock:
            return Settings(**asdict(self._settings))

    def save(self, raw: dict) -> Settings:
        settings = sanitize_settings(raw)
        with self._lock:
            self._settings = settings
            self._write()
        return self.get()

    def update(self, **changes) -> Settings:
        with self._lock:
            merged = asdict(self._settings)
            merged.update(changes)
            settings = sanitize_settings(merged)
            self._settings = settings
            self._write()
            return self.get()

    def _write(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(self._settings), fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self._path)
