import { useCallback, useEffect, useRef, useState } from "react";
import {
  ButtonItem,
  Focusable,
  PanelSection,
  PanelSectionRow,
  TextField,
} from "@decky/ui";
import { toaster } from "@decky/api";
import {
  FaChevronLeft,
  FaDownload,
  FaListUl,
  FaRandom,
  FaSearch,
} from "react-icons/fa";
import { api, errorMessage } from "../api";
import { formatCount } from "../format";
import { player } from "../state/player";
import type { Album, Playlist, SearchResult, Song } from "../types";
import {
  ActionButton,
  AlbumRow,
  ButtonRow,
  Cover,
  EmptyState,
  SongRow,
  SubTitle,
} from "./Common";

interface Detail {
  kind: "album" | "playlist";
  title: string;
  subtitle: string;
  coverArt: string;
  songs: Song[];
}

const ALBUM_KINDS = [
  { data: "newest", label: "Recently added" },
  { data: "recent", label: "Recently played" },
  { data: "frequent", label: "Most played" },
  { data: "random", label: "Random" },
  { data: "alphabeticalByArtist", label: "By artist" },
  { data: "alphabeticalByName", label: "Alphabetical" },
];

export function Library({
  showPlaylists,
  onTogglePlaylists,
}: {
  showPlaylists: boolean;
  onTogglePlaylists: (show: boolean) => Promise<void>;
}) {
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [albums, setAlbums] = useState<Album[]>([]);
  const [albumKind, setAlbumKind] = useState("newest");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const albumRequest = useRef(0);

  const loadAlbums = useCallback(
    async (kind: string, append = false) => {
      const request = ++albumRequest.current;
      setLoading(true);
      try {
        const offset = append ? albums.length : 0;
        const next = await api.getAlbums(kind, 30, offset);
        if (request !== albumRequest.current) return;
        setAlbums((previous) => (append ? [...previous, ...next] : next));
        setError(null);
      } catch (err) {
        if (request === albumRequest.current) setError(errorMessage(err));
      } finally {
        if (request === albumRequest.current) setLoading(false);
      }
    },
    [albums.length],
  );

  const changeAlbumKind = (kind: string) => {
    if (kind === albumKind) return;
    setAlbumKind(kind);
    setAlbums([]);
    void loadAlbums(kind);
  };

  useEffect(() => {
    let alive = true;
    const request = ++albumRequest.current;
    void (async () => {
      try {
        const nextAlbums = await api.getAlbums("newest", 30, 0);
        if (!alive || request !== albumRequest.current) return;
        setAlbums(nextAlbums);
        setError(null);
      } catch (err) {
        if (alive && request === albumRequest.current) setError(errorMessage(err));
      } finally {
        if (alive && request === albumRequest.current) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!showPlaylists) return;
    let alive = true;
    void api
      .getPlaylists()
      .then((next) => {
        if (alive) setPlaylists(next);
      })
      .catch((err) => {
        if (alive) setError(errorMessage(err));
      });
    return () => {
      alive = false;
    };
  }, [showPlaylists]);

  const togglePlaylists = async () => {
    try {
      await onTogglePlaylists(!showPlaylists);
    } catch (err) {
      toaster.toast({ title: "Could not save playlist setting", body: errorMessage(err) });
    }
  };

  const download = async (songs: Song[]) => {
    if (!songs.length) return;
    setBusy(true);
    try {
      const result = await api.downloadSongs(songs);
      toaster.toast({
        title: "Downloads",
        body:
          result.queued > 0
            ? `Queued ${formatCount(result.queued, "song")} for offline use.`
            : "Already cached.",
      });
    } catch (err) {
      toaster.toast({ title: "Download failed", body: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  const openAlbum = async (album: Album) => {
    setBusy(true);
    try {
      const songs = await api.getAlbumSongs(album.id);
      setDetail({
        kind: "album",
        title: album.name,
        subtitle: album.artist,
        coverArt: album.coverArt,
        songs,
      });
    } catch (err) {
      toaster.toast({ title: "Could not open album", body: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  const openPlaylist = async (playlist: Playlist) => {
    setBusy(true);
    try {
      const songs = await api.getPlaylistSongs(playlist.id);
      setDetail({
        kind: "playlist",
        title: playlist.name,
        subtitle: formatCount(playlist.songCount, "song"),
        coverArt: playlist.coverArt,
        songs,
      });
    } catch (err) {
      toaster.toast({ title: "Could not open playlist", body: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  const search = async () => {
    const trimmed = query.trim();
    if (!trimmed) {
      setResults(null);
      return;
    }
    setBusy(true);
    try {
      const response = await api.search(trimmed);
      setResults(response);
    } catch (err) {
      toaster.toast({ title: "Search failed", body: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  if (detail) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => setDetail(null)}>
            <FaChevronLeft size={11} /> Back to library
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <Cover coverArt={detail.coverArt} size={72} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>{detail.title}</div>
              <div style={{ fontSize: 11, color: "#8f98a0" }}>{detail.subtitle}</div>
              <div style={{ fontSize: 11, color: "#8f98a0" }}>
                {formatCount(detail.songs.length, "song")}
              </div>
            </div>
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonRow>
            <ActionButton
              primary
              disabled={!detail.songs.length}
              onClick={() => void player.playQueue(detail.songs, 0)}
              style={{ flex: 1 }}
            >
              Play all
            </ActionButton>
            <ActionButton
              disabled={!detail.songs.length}
              onClick={() => void player.playShuffled(detail.songs)}
              style={{ flex: 1 }}
            >
              <FaRandom size={10} /> Shuffle
            </ActionButton>
            <ActionButton
              disabled={busy || !detail.songs.length}
              onClick={() => void download(detail.songs)}
              style={{ flex: 1 }}
            >
              <FaDownload size={10} /> All
            </ActionButton>
          </ButtonRow>
        </PanelSectionRow>
        {detail.songs.map((song, index) => (
          <SongRow
            key={song.id}
            song={song}
            onPlay={() => void player.playQueue(detail.songs, index)}
            action={{
              icon: <FaDownload size={11} />,
              label: `Download ${song.title}`,
              onClick: () => void download([song]),
            }}
          />
        ))}
        {!detail.songs.length && <EmptyState text="This list is empty." />}
      </PanelSection>
    );
  }

  if (results) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => setResults(null)}>
            <FaChevronLeft size={11} /> Clear search
          </ButtonItem>
        </PanelSectionRow>
        {results.albums.length > 0 && (
          <>
            <SubTitle text="Albums" />
            {results.albums.map((album) => (
              <AlbumRow key={album.id} album={album} onOpen={() => void openAlbum(album)} />
            ))}
          </>
        )}
        {results.songs.length > 0 && (
          <>
            <SubTitle text="Songs" />
            {results.songs.map((song, index) => (
              <SongRow
                key={song.id}
                song={song}
                onPlay={() => void player.playQueue(results.songs, index)}
                action={{
                  icon: <FaDownload size={11} />,
                  label: `Download ${song.title}`,
                  onClick: () => void download([song]),
                }}
              />
            ))}
          </>
        )}
        {!results.albums.length && !results.songs.length && (
          <EmptyState text="No results. Try a different search." />
        )}
      </PanelSection>
    );
  }

  return (
    <PanelSection>
      <PanelSectionRow>
        <TextField
          label="Search library"
          value={query}
          placeholder="Song, album or artist"
          onChange={(event) => setQuery(event.target.value)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ActionButton primary disabled={busy} onClick={() => void search()}>
          <FaSearch size={11} /> Search
        </ActionButton>
      </PanelSectionRow>

      <PanelSectionRow>
        <ButtonRow>
          <ActionButton onClick={() => void player.playRandom(40)} style={{ flex: 1 }}>
            <FaRandom size={11} /> Random mix
          </ActionButton>
          <ActionButton onClick={() => void togglePlaylists()} style={{ flex: 1 }}>
            <FaListUl size={10} /> {showPlaylists ? "Hide playlists" : "Show playlists"}
          </ActionButton>
        </ButtonRow>
      </PanelSectionRow>

      {error && (
        <PanelSectionRow>
          <div style={{ fontSize: 11, color: "#ff8a80", textAlign: "center" }}>{error}</div>
        </PanelSectionRow>
      )}

      {showPlaylists && (
        <>
          <SubTitle text="Playlists" />
          {playlists.map((playlist) => (
            <PlaylistRow
              key={playlist.id}
              playlist={playlist}
              onOpen={() => void openPlaylist(playlist)}
            />
          ))}
          {!playlists.length && !loading && <EmptyState text="No playlists on the server." />}
        </>
      )}

      <SubTitle text="Albums" />
      <AlbumFilter value={albumKind} onChange={changeAlbumKind} />
      {albums.map((album) => (
        <AlbumRow key={`${album.id}-${album.name}`} album={album} onOpen={() => void openAlbum(album)} />
      ))}
      {loading && <EmptyState text="Loading library…" />}
      {!loading && !albums.length && <EmptyState text="No albums returned by the server." />}
      {albums.length > 0 && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => void loadAlbums(albumKind, true)}>
            Load more albums
          </ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

function AlbumFilter({
  value,
  onChange,
}: {
  value: string;
  onChange: (kind: string) => void;
}) {
  return (
    <Focusable
      flow-children="grid"
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 4,
        padding: "0 2px 5px",
      }}
    >
      {ALBUM_KINDS.map((kind) => (
        <ActionButton
          key={kind.data}
          primary={value === kind.data}
          onClick={() => onChange(kind.data)}
          style={{ padding: "6px 2px", fontSize: 10 }}
        >
          {kind.label}
        </ActionButton>
      ))}
    </Focusable>
  );
}

function PlaylistRow({ playlist, onOpen }: { playlist: Playlist; onOpen: () => void }) {
  return (
    <PanelSectionRow>
      <ButtonItem layout="below" onClick={onOpen}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <FaListUl size={12} color="#8f98a0" />
          <div style={{ flex: 1, textAlign: "left", minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{playlist.name}</div>
            <div style={{ fontSize: 11, color: "#8f98a0" }}>
              {formatCount(playlist.songCount, "song")}
            </div>
          </div>
        </div>
      </ButtonItem>
    </PanelSectionRow>
  );
}
