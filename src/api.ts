import { callable } from "@decky/api";
import type {
  Album,
  CacheStats,
  ConnectionResult,
  DownloadQueue,
  DownloadResult,
  Playlist,
  SearchResult,
  Settings,
  Song,
} from "./types";

export const api = {
  getSettings: callable<[], Settings>("get_settings"),
  saveSettings: callable<[Settings], Settings>("save_settings"),
  setShowPlaylists: callable<[boolean], Settings>("set_show_playlists"),
  testConnection: callable<[Settings], ConnectionResult>("test_connection"),
  getMediaBase: callable<[], string>("get_media_base"),

  getRandomSongs: callable<[number], Song[]>("get_random_songs"),
  getPlaylists: callable<[], Playlist[]>("get_playlists"),
  getPlaylistSongs: callable<[string], Song[]>("get_playlist_songs"),
  getAlbums: callable<[string, number, number], Album[]>("get_albums"),
  getAlbumSongs: callable<[string], Song[]>("get_album_songs"),
  search: callable<[string], SearchResult>("search"),

  downloadSongs: callable<[Song[]], DownloadResult>("download_songs"),
  prefetchSong: callable<[Song], boolean>("prefetch_song"),
  getDownloads: callable<[], Song[]>("get_downloads"),
  getDownloadQueue: callable<[], DownloadQueue>("get_download_queue"),
  clearDownloadQueue: callable<[], DownloadQueue>("clear_download_queue"),
  deleteDownload: callable<[string], boolean>("delete_download"),
  getCacheStats: callable<[], CacheStats>("get_cache_stats"),
  clearCache: callable<[boolean], CacheStats>("clear_cache"),
  reportPlay: callable<[string], void>("report_play"),
};

let mediaBase = "";
let mediaPromise: Promise<string> | null = null;

export function primeMediaBase(): Promise<string> {
  if (mediaBase) return Promise.resolve(mediaBase);
  if (!mediaPromise) {
    mediaPromise = api
      .getMediaBase()
      .then((base) => {
        mediaBase = base;
        return base;
      })
      .catch((error) => {
        mediaPromise = null;
        throw error;
      });
  }
  return mediaPromise;
}

export function mediaBaseReady(): boolean {
  return Boolean(mediaBase);
}

export function streamUrl(songId: string): string {
  return mediaBase ? `${mediaBase}/stream/${encodeURIComponent(songId)}` : "";
}

export function artUrl(coverArt: string, size = 300): string {
  if (!mediaBase || !coverArt) return "";
  return `${mediaBase}/art/${encodeURIComponent(coverArt)}?size=${size}`;
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error ?? "Unknown error").replace(/^Error:\s*/, "");
}
