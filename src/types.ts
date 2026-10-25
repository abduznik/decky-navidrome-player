export interface Song {
  id: string;
  title: string;
  artist: string;
  album: string;
  albumId: string;
  coverArt: string;
  duration: number;
  suffix: string;
  track: number;
  year: number;
  size?: number;
  starred?: boolean;
  isCached?: boolean;
  isDownloaded?: boolean;
  sizeBytes?: number;
  pinned?: boolean;
  added?: number;
}

export interface Album {
  id: string;
  name: string;
  artist: string;
  coverArt: string;
  songCount: number;
  duration: number;
  year: number;
}

export interface Playlist {
  id: string;
  name: string;
  comment: string;
  songCount: number;
  duration: number;
  coverArt: string;
  owner: string;
}

export interface Settings {
  server_url: string;
  username: string;
  password: string;
  cache_limit_bytes: number;
  cache_played_songs: boolean;
  max_bitrate: number;
  configured?: boolean;
}

export interface CacheStats {
  totalBytes: number;
  limitBytes: number;
  autoBytes: number;
  pinnedBytes: number;
  autoCount: number;
  pinnedCount: number;
  trackCount: number;
  overLimit: boolean;
  diskFreeBytes: number;
  cacheDir?: string;
}

export interface ConnectionResult {
  ok: boolean;
  message: string;
  serverVersion?: string;
}

export interface SearchResult {
  songs: Song[];
  albums: Album[];
}

export interface DownloadResult {
  queued: number;
  skipped: number;
}

export interface DownloadProgress {
  id: string;
  title: string;
  percent: number;
  pinned: boolean;
}

export interface DownloadSummary {
  active: boolean;
  downloading: string[];
  pending: number;
  completed: number;
  failed: number;
}

export type RepeatMode = "off" | "all" | "one";

export type Tab = "now" | "library" | "downloads" | "settings";
