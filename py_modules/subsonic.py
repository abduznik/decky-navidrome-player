"""A dependency-free Subsonic / Navidrome API client.

Only the endpoints needed by the player are implemented. Authentication uses
the Subsonic token scheme (md5(password + salt)), so the raw password never
travels over the network.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable

API_VERSION = "1.16.1"
CLIENT_NAME = "DeckyNavidromePlayer"
USER_AGENT = "DeckyNavidromePlayer/0.1 (+https://github.com/)"


class SubsonicError(RuntimeError):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class SubsonicClient:
    def __init__(
        self,
        server_url: str,
        username: str,
        password: str,
        max_bitrate: int = 0,
        timeout: float = 20.0,
    ):
        self.base_url = server_url.rstrip("/")
        self.username = username
        self.password = password
        self.max_bitrate = max_bitrate
        self.timeout = timeout

    # ------------------------------------------------------------------ HTTP
    def _auth_params(self) -> dict[str, str]:
        salt = secrets.token_hex(8)
        token = hashlib.md5((self.password + salt).encode("utf-8")).hexdigest()
        return {
            "u": self.username,
            "t": token,
            "s": salt,
            "v": API_VERSION,
            "c": CLIENT_NAME,
            "f": "json",
        }

    def _signed_url(self, endpoint: str, **params: Any) -> str:
        query = self._auth_params()
        query.update({k: v for k, v in params.items() if v is not None})
        encoded = urllib.parse.urlencode(query, quote_via=urllib.parse.quote)
        return f"{self.base_url}/rest/{endpoint}.view?{encoded}"

    def _request(self, endpoint: str, **params: Any) -> dict[str, Any]:
        url = self._signed_url(endpoint, **params)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            raise SubsonicError(
                f"Navidrome returned HTTP {exc.code} for {endpoint}"
            ) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise SubsonicError(f"Cannot reach Navidrome: {reason}") from exc
        except TimeoutError as exc:
            raise SubsonicError("Navidrome request timed out") from exc

        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SubsonicError(
                "Navidrome returned a non-JSON response. Is the URL pointing at a "
                "Navidrome/Subsonic server?"
            ) from exc

        body = data.get("subsonic-response") or data.get("subsonicResponse")
        if not isinstance(body, dict):
            raise SubsonicError("Unexpected response from the server")
        if body.get("status") == "failed" or "error" in body:
            error = body.get("error") or {}
            raise SubsonicError(
                str(error.get("message") or "Navidrome request failed"),
                error.get("code"),
            )
        return body

    # -------------------------------------------------------------- playback
    def open_song(self, song_id: str, range_header: str | None = None):
        """Open a stream response. Caller is responsible for closing it."""
        params: dict[str, Any] = {"id": song_id}
        if self.max_bitrate:
            params["maxBitRate"] = self.max_bitrate
        url = self._signed_url("stream", **params)
        headers = {"User-Agent": USER_AGENT}
        if range_header:
            headers["Range"] = range_header
        request = urllib.request.Request(url, headers=headers)
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise SubsonicError("Navidrome rejected the credentials") from exc
            raise SubsonicError(f"Stream request failed (HTTP {exc.code})") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise SubsonicError(f"Cannot reach Navidrome: {reason}") from exc

    def open_cover(self, cover_id: str, size: int = 300):
        url = self._signed_url("getCoverArt", id=cover_id, size=size)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raise SubsonicError(f"Cover art request failed (HTTP {exc.code})") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise SubsonicError(f"Cannot reach Navidrome: {reason}") from exc

    def ping(self) -> dict[str, Any]:
        return self._request("ping")

    def scrobble(self, song_id: str, submission: bool = True) -> None:
        self._request(
            "scrobble",
            id=song_id,
            submission="true" if submission else "false",
        )

    # ------------------------------------------------------------------ data
    def get_random_songs(self, size: int = 30) -> list[dict[str, Any]]:
        body = self._request("getRandomSongs", size=max(1, min(500, int(size))))
        songs = _dig(body, "randomSongs", "song")
        return [map_song(item) for item in _as_list(songs)]

    def get_playlists(self) -> list[dict[str, Any]]:
        body = self._request("getPlaylists")
        playlists = _as_list(_dig(body, "playlists", "playlist"))
        return [map_playlist(item) for item in playlists if item.get("id")]

    def get_playlist_songs(self, playlist_id: str) -> list[dict[str, Any]]:
        body = self._request("getPlaylist", id=playlist_id)
        entries = _as_list(_dig(body, "playlist", "entry"))
        return [map_song(item) for item in entries]

    def get_albums(
        self, kind: str = "random", size: int = 30, offset: int = 0
    ) -> list[dict[str, Any]]:
        allowed = {
            "newest",
            "recent",
            "frequent",
            "random",
            "alphabeticalByName",
            "alphabeticalByArtist",
            "starred",
        }
        if kind not in allowed:
            kind = "random"
        body = self._request(
            "getAlbumList2",
            type=kind,
            size=max(1, min(500, int(size))),
            offset=max(0, int(offset)),
        )
        albums = _as_list(_dig(body, "albumList2", "album"))
        return [map_album(item) for item in albums]

    def get_album_songs(self, album_id: str) -> list[dict[str, Any]]:
        body = self._request("getAlbum", id=album_id)
        album = body.get("album") or {}
        songs = _as_list(album.get("song"))
        return [map_song(item) for item in songs]

    def search(self, query: str) -> dict[str, list[dict[str, Any]]]:
        body = self._request(
            "search3",
            query=query,
            songCount=30,
            albumCount=20,
            artistCount=0,
        )
        result = body.get("searchResult3") or {}
        return {
            "songs": [map_song(item) for item in _as_list(result.get("song"))],
            "albums": [map_album(item) for item in _as_list(result.get("album"))],
        }


# ------------------------------------------------------------------ mapping
def _dig(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _clean(value: Any) -> str:
    return "" if value is None else str(value)


def map_song(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _clean(item.get("id")),
        "title": _clean(item.get("title")) or "Unknown title",
        "artist": _clean(item.get("artist")),
        "album": _clean(item.get("album")),
        "albumId": _clean(item.get("albumId")),
        "coverArt": _clean(item.get("coverArt")),
        "duration": int(item.get("duration") or 0),
        "suffix": _clean(item.get("suffix")).lower(),
        "track": int(item.get("track") or 0),
        "year": int(item.get("year") or 0),
        "size": int(item.get("size") or 0),
        "starred": bool(item.get("starred")),
    }


def map_album(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _clean(item.get("id")),
        "name": _clean(item.get("name")) or "Unknown album",
        "artist": _clean(item.get("artist")),
        "coverArt": _clean(item.get("coverArt")),
        "songCount": int(item.get("songCount") or 0),
        "duration": int(item.get("duration") or 0),
        "year": int(item.get("year") or 0),
    }


def map_playlist(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _clean(item.get("id")),
        "name": _clean(item.get("name")) or "Untitled playlist",
        "comment": _clean(item.get("comment")),
        "songCount": int(item.get("songCount") or 0),
        "duration": int(item.get("duration") or 0),
        "coverArt": _clean(item.get("coverArt")),
        "owner": _clean(item.get("owner")),
    }


def flatten(iterables: Iterable[Iterable[Any]]) -> list[Any]:
    out: list[Any] = []
    for items in iterables:
        out.extend(items)
    return out
