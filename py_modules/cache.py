"""Disk cache with a size limit, LRU eviction and pinned manual downloads.

The manifest is a small JSON document, which keeps the plugin dependency-free
and portable across architectures. Audio files are stored under
``<runtime>/cache/audio`` using a hash of the song id, so ids containing slashes
or unicode characters are safe.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from typing import Any

MANIFEST_VERSION = 1
_SUFFIX_RE = re.compile(r"^[a-z0-9]{1,5}$")


class CacheError(RuntimeError):
    pass


def _safe_suffix(value: Any) -> str:
    suffix = str(value or "").strip().lower().lstrip(".")
    return suffix if _SUFFIX_RE.match(suffix) else "mp3"


def _file_stem(song_id: str) -> str:
    return hashlib.sha1(song_id.encode("utf-8")).hexdigest()


class CacheManager:
    def __init__(self, root: str, limit_bytes: int):
        self.root = root
        self.audio_dir = os.path.join(root, "audio")
        self.tmp_dir = os.path.join(root, "tmp")
        self._manifest_path = os.path.join(root, "manifest.json")
        self._lock = threading.RLock()
        self._limit = max(0, int(limit_bytes))
        self._entries: dict[str, dict[str, Any]] = {}
        os.makedirs(self.audio_dir, exist_ok=True)
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._clean_temp_files()
        self._load()

    # --------------------------------------------------------------- settings
    @property
    def limit_bytes(self) -> int:
        with self._lock:
            return self._limit

    def set_limit(self, limit_bytes: int) -> None:
        with self._lock:
            self._limit = max(0, int(limit_bytes))
            self._enforce_limit()
            self._save()

    # -------------------------------------------------------------- read side
    def peek(self, song_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._entries.get(song_id)
            return dict(entry) if entry else None

    def get(self, song_id: str, touch: bool = True) -> dict[str, Any] | None:
        with self._lock:
            entry = self._entries.get(song_id)
            if not entry:
                return None
            if not os.path.isfile(os.path.join(self.audio_dir, entry["file"])):
                self._entries.pop(song_id, None)
                self._save()
                return None
            if touch:
                entry["lastUsed"] = time.time()
                self._save()
            return dict(entry)

    def is_cached(self, song_id: str) -> bool:
        return self.peek(song_id) is not None

    def local_path(self, song_id: str) -> str | None:
        entry = self.get(song_id, touch=True)
        if not entry:
            return None
        return os.path.join(self.audio_dir, entry["file"])

    def pinned_songs(self) -> list[dict[str, Any]]:
        with self._lock:
            entries = [dict(item) for item in self._entries.values() if item.get("pinned")]
        entries.sort(key=lambda item: item.get("added", 0), reverse=True)
        return [self._entry_to_song(item) for item in entries]

    # ------------------------------------------------------------- write side
    def new_temp_path(self, song_id: str) -> str:
        os.makedirs(self.tmp_dir, exist_ok=True)
        return os.path.join(
            self.tmp_dir, f"{_file_stem(song_id)}-{uuid.uuid4().hex}.part"
        )

    def put(self, song: dict[str, Any], temp_path: str, pinned: bool) -> dict[str, Any]:
        """Move a completed download into the cache and register it."""
        song_id = str(song.get("id") or "")
        if not song_id:
            raise CacheError("Song has no id")
        if not os.path.isfile(temp_path):
            raise CacheError("Downloaded file is missing")

        suffix = _safe_suffix(song.get("suffix"))
        filename = f"{_file_stem(song_id)}.{suffix}"
        destination = os.path.join(self.audio_dir, filename)
        now = time.time()

        with self._lock:
            old = self._entries.get(song_id)
            if old and old.get("file") != filename:
                self._unlink_quietly(os.path.join(self.audio_dir, old["file"]))
            os.replace(temp_path, destination)
            size = os.path.getsize(destination)
            entry = {
                "id": song_id,
                "file": filename,
                "suffix": suffix,
                "title": str(song.get("title") or "Unknown title"),
                "artist": str(song.get("artist") or ""),
                "album": str(song.get("album") or ""),
                "albumId": str(song.get("albumId") or ""),
                "coverArt": str(song.get("coverArt") or ""),
                "duration": int(song.get("duration") or 0),
                "track": int(song.get("track") or 0),
                "year": int(song.get("year") or 0),
                "size": size,
                "pinned": bool(pinned),
                "added": now,
                "lastUsed": now,
            }
            self._entries[song_id] = entry
            self._enforce_limit(protected_id=song_id)
            if not pinned and self._total_size() > self._limit:
                # Pinned downloads fill the limit and this auto-cached copy
                # cannot be kept without exceeding it.
                self._entries.pop(song_id, None)
                self._unlink_quietly(destination)
                self._save()
                raise CacheError("Cache is full")
            self._save()
            stored = self._entries.get(song_id)
            if not stored:
                raise CacheError("Cache is full")
            return dict(stored)

    def pin(self, song_id: str) -> dict[str, Any] | None:
        """Promote an automatically cached song to a keep-forever download."""
        with self._lock:
            entry = self._entries.get(song_id)
            if not entry:
                return None
            entry["pinned"] = True
            entry["lastUsed"] = time.time()
            self._save()
            return dict(entry)

    def remove(self, song_id: str) -> bool:
        with self._lock:
            entry = self._entries.pop(song_id, None)
            if not entry:
                return False
            self._unlink_quietly(os.path.join(self.audio_dir, entry["file"]))
            self._save()
            return True

    def clear(self, include_downloads: bool = False) -> dict[str, Any]:
        with self._lock:
            for song_id, entry in list(self._entries.items()):
                if entry.get("pinned") and not include_downloads:
                    continue
                self._entries.pop(song_id, None)
                self._unlink_quietly(os.path.join(self.audio_dir, entry["file"]))
            self._save()
            return self.stats()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            auto_bytes = sum(
                int(item.get("size", 0))
                for item in self._entries.values()
                if not item.get("pinned")
            )
            pinned_bytes = sum(
                int(item.get("size", 0))
                for item in self._entries.values()
                if item.get("pinned")
            )
            auto_count = sum(1 for item in self._entries.values() if not item.get("pinned"))
            pinned_count = sum(1 for item in self._entries.values() if item.get("pinned"))
            total = auto_bytes + pinned_bytes
            disk_free = 0
            try:
                disk_free = shutil.disk_usage(self.root).free
            except OSError:
                pass
            return {
                "totalBytes": total,
                "limitBytes": self._limit,
                "autoBytes": auto_bytes,
                "pinnedBytes": pinned_bytes,
                "autoCount": auto_count,
                "pinnedCount": pinned_count,
                "trackCount": auto_count + pinned_count,
                "overLimit": total > self._limit,
                "diskFreeBytes": disk_free,
                "cacheDir": self.audio_dir,
            }

    # --------------------------------------------------------------- internal
    def _enforce_limit(self, protected_id: str | None = None) -> None:
        while self._total_size() > self._limit:
            candidates = [
                entry
                for entry in self._entries.values()
                if not entry.get("pinned") and entry["id"] != protected_id
            ]
            if not candidates:
                # Only pinned downloads remain. They are never evicted
                # automatically; stats will report overLimit.
                break
            victim = min(candidates, key=lambda item: item.get("lastUsed", 0))
            self._entries.pop(victim["id"], None)
            self._unlink_quietly(os.path.join(self.audio_dir, victim["file"]))

    def _total_size(self) -> int:
        return sum(int(item.get("size", 0)) for item in self._entries.values())

    def _entry_to_song(self, entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": entry["id"],
            "title": entry.get("title", ""),
            "artist": entry.get("artist", ""),
            "album": entry.get("album", ""),
            "albumId": entry.get("albumId", ""),
            "coverArt": entry.get("coverArt", ""),
            "duration": int(entry.get("duration") or 0),
            "suffix": entry.get("suffix", "mp3"),
            "track": int(entry.get("track") or 0),
            "year": int(entry.get("year") or 0),
            "sizeBytes": int(entry.get("size") or 0),
            "pinned": bool(entry.get("pinned")),
            "added": float(entry.get("added") or 0),
        }

    def _clean_temp_files(self) -> None:
        """Remove partial downloads left behind by a previous run."""
        try:
            for name in os.listdir(self.tmp_dir):
                if name.endswith(".part"):
                    self._unlink_quietly(os.path.join(self.tmp_dir, name))
        except OSError:
            pass

    def _load(self) -> None:
        with self._lock:
            try:
                with open(self._manifest_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                entries = data.get("entries") or {}
                if not isinstance(entries, dict):
                    return
                for song_id, entry in entries.items():
                    if not isinstance(entry, dict):
                        continue
                    filename = str(entry.get("file") or "")
                    # Never trust a manifest to point outside the audio dir.
                    if not filename or os.path.basename(filename) != filename:
                        continue
                    path = os.path.join(self.audio_dir, filename)
                    if not os.path.isfile(path):
                        continue
                    entry = dict(entry)
                    entry["id"] = str(song_id)
                    entry["size"] = os.path.getsize(path)
                    entry["sizeBytes"] = entry["size"]
                    entry["pinned"] = bool(entry.get("pinned"))
                    self._entries[str(song_id)] = entry
                # A lowered limit may have been saved before shutdown.
                self._enforce_limit()
            except FileNotFoundError:
                pass
            except (OSError, ValueError):
                self._entries = {}

    def _save(self) -> None:
        try:
            os.makedirs(self.root, exist_ok=True)
            tmp = self._manifest_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(
                    {"version": MANIFEST_VERSION, "entries": self._entries},
                    fh,
                    separators=(",", ":"),
                )
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._manifest_path)
        except OSError:
            # Cache metadata is recoverable; never crash playback over it.
            pass

    @staticmethod
    def _unlink_quietly(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass
