"""Loopback HTTP server that streams cached or proxied Navidrome audio.

The browser (Steam's CEF) cannot read arbitrary files from disk, so cached
tracks are exposed through 127.0.0.1 with a per-session secret token in the
path. Range requests are implemented for seeking, which also makes offline
playback behave like a normal media URL.
"""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from .subsonic import SubsonicError

CHUNK_SIZE = 64 * 1024
MAX_COVER_SIZE = 1024


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Parse a single byte range. Returns (start, end) or None when invalid."""
    if not header or not header.startswith("bytes="):
        return None
    spec = header[len("bytes=") :].split(",")[0].strip()
    if "-" not in spec:
        return None
    start_raw, end_raw = spec.split("-", 1)
    try:
        if start_raw == "":
            suffix = int(end_raw)
            if suffix <= 0:
                return None
            start = max(0, size - suffix)
            end = size - 1
        else:
            start = int(start_raw)
            end = int(end_raw) if end_raw else size - 1
    except ValueError:
        return None
    if start < 0 or end < start or start >= size:
        return None
    return start, min(end, size - 1)


class LocalMediaServer:
    def __init__(
        self,
        client_factory: Callable[[], Any | None],
        cache: Any,
        logger: Any,
    ):
        self._client_factory = client_factory
        self._cache = cache
        self._logger = logger
        self._token = secrets.token_urlsafe(18)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._base_url = ""

    @property
    def base_url(self) -> str:
        if not self._base_url:
            self.start()
        return self._base_url

    def start(self) -> None:
        if self._httpd:
            return
        app = self

        class Handler(_MediaHandler):
            server_app = app

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        httpd.daemon_threads = True
        self._httpd = httpd
        self._thread = threading.Thread(
            target=httpd.serve_forever,
            kwargs={"poll_interval": 0.2},
            name="navidrome-media",
            daemon=True,
        )
        self._thread.start()
        port = httpd.server_address[1]
        self._base_url = f"http://127.0.0.1:{port}/m/{self._token}"
        self._logger.info("Local media server listening on 127.0.0.1:%s", port)

    def stop(self) -> None:
        httpd = self._httpd
        thread = self._thread
        self._httpd = None
        self._thread = None
        self._base_url = ""
        if httpd:
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
        if thread and thread.is_alive():
            thread.join(timeout=3)


class _MediaHandler(BaseHTTPRequestHandler):
    server_app: LocalMediaServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        self.server_app._logger.debug("media: " + fmt, *args)

    # ------------------------------------------------------------- verbs
    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(204, {})

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle(head=True)

    def do_GET(self) -> None:  # noqa: N802
        self._handle(head=False)

    # ------------------------------------------------------------ routing
    def _handle(self, head: bool) -> None:
        parsed = urlparse(self.path)
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        app = self.server_app
        if (
            len(parts) < 3
            or parts[0] != "m"
            or not secrets.compare_digest(parts[1], app._token)
        ):
            self._send_json(404, {"error": "Not found"})
            return

        try:
            if parts[2] == "stream" and len(parts) == 4:
                self._stream(parts[3], head)
            elif parts[2] == "art" and len(parts) == 4:
                self._art(parts[3], parse_qs(parsed.query), head)
            elif parts[2] == "health":
                self._send_json(200, {"ok": True})
            else:
                self._send_json(404, {"error": "Not found"})
        except SubsonicError as exc:
            self._send_json(502, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001
            app._logger.warning("Media request failed: %s", exc)
            try:
                self._send_json(500, {"error": "Internal media server error"})
            except (BrokenPipeError, ConnectionResetError):
                pass

    # ------------------------------------------------------------ handlers
    def _stream(self, song_id: str, head: bool) -> None:
        app = self.server_app
        entry = app._cache.get(song_id)
        if entry:
            path = os.path.join(app._cache.audio_dir, entry["file"])
            if os.path.isfile(path):
                self._send_file(path, entry.get("suffix", "mp3"), head)
                return
        client = app._client_factory()
        if client is None:
            self._send_json(503, {"error": "Navidrome is not configured"})
            return
        remote = client.open_song(song_id, self.headers.get("Range"))
        self._relay(remote, head, fallback_type="audio/mpeg", cache_control="no-store")

    def _art(self, cover_id: str, query: dict[str, list[str]], head: bool) -> None:
        app = self.server_app
        try:
            size = int((query.get("size") or ["300"])[0])
        except (TypeError, ValueError):
            size = 300
        size = max(32, min(MAX_COVER_SIZE, size))
        client = app._client_factory()
        if client is None:
            self._send_json(503, {"error": "Navidrome is not configured"})
            return
        remote = client.open_cover(cover_id, size)
        self._relay(
            remote,
            head,
            fallback_type="image/jpeg",
            cache_control="public, max-age=86400",
        )

    def _send_file(self, path: str, suffix: str, head: bool) -> None:
        size = os.path.getsize(path)
        content_type = mimetypes.guess_type(path)[0] or _audio_type(suffix)
        range_header = self.headers.get("Range")
        byte_range = parse_range(range_header, size) if range_header else None

        if range_header and byte_range is None:
            self.send_response(416)
            self._common_headers()
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if byte_range:
            start, end = byte_range
            length = end - start + 1
            self.send_response(206)
            self._common_headers()
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            start, length = 0, size
            self.send_response(200)
            self._common_headers()

        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", "inline")
        self.end_headers()

        if head:
            return
        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _relay(
        self,
        remote: Any,
        head: bool,
        fallback_type: str,
        cache_control: str,
    ) -> None:
        try:
            status = int(getattr(remote, "status", 200))
            headers = remote.headers
            if status not in (200, 206):
                self._send_json(502, {"error": f"Upstream returned HTTP {status}"})
                return

            content_type = headers.get("Content-Type") or fallback_type
            content_length = headers.get("Content-Length")
            content_range = headers.get("Content-Range")
            accept_ranges = headers.get("Accept-Ranges") or "bytes"

            self.send_response(status)
            self._common_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", accept_ranges)
            self.send_header("Cache-Control", cache_control)
            self.send_header("Content-Disposition", "inline")
            if content_range:
                self.send_header("Content-Range", content_range)
            if content_length:
                self.send_header("Content-Length", content_length)
            else:
                # Unknown length: HTTP/1.1 needs chunking or a connection close.
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()

            if head:
                return
            while True:
                chunk = remote.read(CHUNK_SIZE)
                if not chunk:
                    break
                self.wfile.write(chunk)
        finally:
            try:
                remote.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------- helpers
    def _common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
        self.send_header(
            "Access-Control-Expose-Headers",
            "Content-Range, Accept-Ranges, Content-Length",
        )

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._common_headers()
        if status == 204:
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _audio_type(suffix: str) -> str:
    suffix = (suffix or "").lower()
    return {
        "flac": "audio/flac",
        "ogg": "audio/ogg",
        "oga": "audio/ogg",
        "opus": "audio/ogg",
        "m4a": "audio/mp4",
        "aac": "audio/aac",
        "wav": "audio/wav",
        "wma": "audio/x-ms-wma",
        "mp3": "audio/mpeg",
    }.get(suffix, "audio/mpeg")
