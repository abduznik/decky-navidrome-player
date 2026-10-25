"""Background download queue for manual downloads and auto-caching."""

from __future__ import annotations

import os
import queue
import threading
import time
from typing import Any, Callable

from .cache import CacheManager, CacheError

CHUNK_SIZE = 64 * 1024
PROGRESS_STEP = 1024 * 1024


class DownloadManager:
    def __init__(
        self,
        client_factory: Callable[[], Any | None],
        cache: CacheManager,
        notify: Callable[[str, dict[str, Any]], None],
        logger: Any,
    ):
        self._client_factory = client_factory
        self._cache = cache
        self._notify = notify
        self._logger = logger
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._lock = threading.RLock()
        self._pending_manual: set[str] = set()
        self._auto_wanted: set[str] = set()
        self._downloading: set[str] = set()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._completed = 0
        self._failed = 0

    # ------------------------------------------------------------------ API
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name="navidrome-downloads", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=3)

    def enqueue(self, songs: list[dict[str, Any]], pinned: bool) -> dict[str, int]:
        queued = 0
        skipped = 0
        with self._lock:
            for song in songs:
                song_id = str(song.get("id") or "")
                if not song_id:
                    skipped += 1
                    continue
                existing = self._cache.peek(song_id)
                if existing:
                    if pinned and not existing.get("pinned"):
                        self._cache.pin(song_id)
                    skipped += 1
                    continue
                active_job = self._jobs.get(song_id)
                if active_job and active_job["state"] in ("queued", "downloading"):
                    # Promote an auto-cache job to a pinned download instead
                    # of queuing the same song twice.
                    if pinned and not active_job["pinned"]:
                        active_job["pinned"] = True
                        self._pending_manual.add(song_id)
                    skipped += 1
                    continue
                if song_id in self._downloading:
                    skipped += 1
                    continue
                if pinned:
                    if song_id in self._pending_manual:
                        skipped += 1
                        continue
                    self._pending_manual.add(song_id)
                else:
                    # Only the most recently played track should be auto-cached.
                    self._auto_wanted.discard(song_id)
                    self._auto_wanted.add(song_id)
                title = str(song.get("title") or "")
                self._jobs[song_id] = {
                    "id": song_id,
                    "title": title,
                    "state": "queued",
                    "percent": 0,
                    "pinned": pinned,
                    "error": "",
                    "added": time.time(),
                }
                self._queue.put(
                    {
                        "song": {
                            "id": song_id,
                            "title": title,
                            "artist": str(song.get("artist") or ""),
                            "album": str(song.get("album") or ""),
                            "albumId": str(song.get("albumId") or ""),
                            "coverArt": str(song.get("coverArt") or ""),
                            "duration": int(song.get("duration") or 0),
                            "suffix": str(song.get("suffix") or ""),
                            "track": int(song.get("track") or 0),
                            "year": int(song.get("year") or 0),
                        },
                        "pinned": pinned,
                    }
                )
                queued += 1
        if queued:
            self._notify("downloads_updated", self._summary())
        return {"queued": queued, "skipped": skipped}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            order = {"downloading": 0, "queued": 1, "failed": 2, "done": 3}
            items = [
                {
                    "id": job["id"],
                    "title": job["title"],
                    "state": job["state"],
                    "percent": int(job.get("percent") or 0),
                    "pinned": bool(job.get("pinned")),
                    "error": job.get("error", ""),
                }
                for job in self._jobs.values()
            ]
            items.sort(key=lambda item: (order.get(item["state"], 4), item["id"]))
            return {
                "items": items,
                "downloading": sum(1 for item in items if item["state"] == "downloading"),
                "pending": sum(1 for item in items if item["state"] == "queued"),
                "done": sum(1 for item in items if item["state"] == "done"),
                "failed": sum(1 for item in items if item["state"] == "failed"),
                "active": any(item["state"] == "downloading" for item in items),
            }

    def clear_finished(self) -> dict[str, Any]:
        with self._lock:
            for song_id, job in list(self._jobs.items()):
                if job["state"] in ("done", "failed"):
                    self._jobs.pop(song_id, None)
            return self.snapshot()

    def prefetch(self, song: dict[str, Any]) -> bool:
        song_id = str(song.get("id") or "")
        if not song_id or self._cache.is_cached(song_id):
            return False
        with self._lock:
            if song_id in self._downloading or song_id in self._pending_manual:
                return False
            self._auto_wanted = {song_id}
        self.enqueue([song], pinned=False)
        return True

    # --------------------------------------------------------------- worker
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if job is None:
                break

            song_id = job["song"]["id"]
            with self._lock:
                tracked = self._jobs.get(song_id)
                if tracked is None:
                    continue
                pinned = bool(tracked.get("pinned"))
                if not pinned and song_id not in self._auto_wanted:
                    self._jobs.pop(song_id, None)
                    self._notify("downloads_updated", self._summary())
                    continue
                if pinned:
                    self._pending_manual.discard(song_id)
                else:
                    self._auto_wanted.discard(song_id)
                existing = self._cache.peek(song_id)
                if existing:
                    if pinned and not existing.get("pinned"):
                        self._cache.pin(song_id)
                    tracked["state"] = "done"
                    tracked["percent"] = 100
                    self._downloading.discard(song_id)
                    self._notify("downloads_updated", self._summary())
                    continue
                tracked["state"] = "downloading"
                tracked["percent"] = 0
                self._downloading.add(song_id)

            try:
                self._download(job["song"], pinned)
                self._completed += 1
                with self._lock:
                    tracked = self._jobs.get(song_id)
                    if tracked:
                        tracked["state"] = "done"
                        tracked["percent"] = 100
                self._notify(
                    "download_complete",
                    {
                        "id": song_id,
                        "title": job["song"]["title"],
                        "pinned": pinned,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - reports errors to the UI
                self._failed += 1
                self._logger.warning(
                    "Download failed for %s: %s", job["song"]["title"], exc
                )
                with self._lock:
                    tracked = self._jobs.get(song_id)
                    if tracked:
                        tracked["state"] = "failed"
                        tracked["error"] = str(exc)
                self._notify(
                    "download_failed",
                    {
                        "id": song_id,
                        "title": job["song"]["title"],
                        "error": str(exc),
                        "pinned": pinned,
                    },
                )
            finally:
                with self._lock:
                    self._downloading.discard(song_id)
                    self._trim_jobs()
                self._notify("downloads_updated", self._summary())

    def _trim_jobs(self) -> None:
        finished = [
            song_id
            for song_id, item in self._jobs.items()
            if item["state"] in ("done", "failed")
        ]
        for song_id in finished[:-30]:
            self._jobs.pop(song_id, None)

    def _download(self, song: dict[str, Any], pinned: bool) -> None:
        client = self._client_factory()
        if client is None:
            raise CacheError("Navidrome is not configured")
        response = client.open_song(song["id"])
        temp_path = self._cache.new_temp_path(song["id"])
        try:
            try:
                length = int(response.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                length = 0
            received = 0
            last_emitted = -PROGRESS_STEP
            self._progress(song["id"], song["title"], 0, pinned)
            with open(temp_path, "wb") as fh:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    fh.write(chunk)
                    received += len(chunk)
                    if received - last_emitted >= PROGRESS_STEP:
                        last_emitted = received
                        percent = int(received * 100 / length) if length else 0
                        self._progress(
                            song["id"], song["title"], min(99, percent), pinned
                        )
            if received == 0:
                raise CacheError("Server returned an empty file")
            with self._lock:
                tracked = self._jobs.get(song["id"])
                pinned_now = bool(tracked.get("pinned")) if tracked else pinned
            self._cache.put(song, temp_path, pinned=pinned_now)
            self._progress(song["id"], song["title"], 100, pinned_now)
        finally:
            try:
                response.close()
            except Exception:  # noqa: BLE001
                pass
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def _progress(
        self, song_id: str, title: str, percent: int, pinned: bool
    ) -> None:
        with self._lock:
            job = self._jobs.get(song_id)
            if job:
                job["percent"] = percent
                job["state"] = "downloading"
        self._notify(
            "download_progress",
            {
                "id": song_id,
                "title": title,
                "percent": percent,
                "pinned": pinned,
            },
        )

    def _summary(self) -> dict[str, Any]:
        with self._lock:
            states = [item["state"] for item in self._jobs.values()]
            return {
                "active": bool(self._downloading),
                "downloading": sorted(self._downloading),
                "pending": states.count("queued"),
                "completed": self._completed,
                "failed": self._failed,
            }
