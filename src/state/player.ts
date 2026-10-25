import { useSyncExternalStore } from "react";
import { toaster } from "@decky/api";
import { api, errorMessage, streamUrl } from "../api";
import { clamp, shuffleArray } from "../format";
import type { RepeatMode, Song } from "../types";

export interface PlayerState {
  queue: Song[];
  index: number;
  current: Song | null;
  playing: boolean;
  loading: boolean;
  currentTime: number;
  duration: number;
  volume: number;
  shuffle: boolean;
  repeat: RepeatMode;
  error: string | null;
}

const VOLUME_KEY = "navidrome-player.volume";
const SHUFFLE_KEY = "navidrome-player.shuffle";
const REPEAT_KEY = "navidrome-player.repeat";

function readVolume(): number {
  try {
    const raw = Number(localStorage.getItem(VOLUME_KEY));
    return Number.isFinite(raw) ? clamp(raw, 0, 1) : 0.8;
  } catch {
    return 0.8;
  }
}

function readBool(key: string): boolean {
  try {
    return localStorage.getItem(key) === "true";
  } catch {
    return false;
  }
}

function readRepeat(): RepeatMode {
  try {
    const raw = localStorage.getItem(REPEAT_KEY);
    return raw === "all" || raw === "one" ? raw : "off";
  } catch {
    return "off";
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Local storage can be unavailable in unusual CEF contexts.
  }
}

class PlayerStore {
  private state: PlayerState = {
    queue: [],
    index: -1,
    current: null,
    playing: false,
    loading: false,
    currentTime: 0,
    duration: 0,
    volume: readVolume(),
    shuffle: readBool(SHUFFLE_KEY),
    repeat: readRepeat(),
    error: null,
  };

  private subscribers = new Set<() => void>();
  private audio: HTMLAudioElement | null = null;
  private scrobbleTimer: ReturnType<typeof setTimeout> | null = null;
  private lastTick = 0;
  private transitioning = false;

  subscribe = (callback: () => void): (() => void) => {
    this.subscribers.add(callback);
    return () => {
      this.subscribers.delete(callback);
    };
  };

  getSnapshot = (): PlayerState => this.state;

  private emit(patch: Partial<PlayerState>): void {
    this.state = { ...this.state, ...patch };
    this.subscribers.forEach((callback) => callback());
  }

  private getAudio(): HTMLAudioElement {
    if (this.audio) return this.audio;
    const audio = new Audio();
    audio.preload = "auto";
    audio.volume = this.state.volume;

    audio.addEventListener("play", () => this.emit({ playing: true, loading: false }));
    audio.addEventListener("pause", () => this.emit({ playing: false }));
    audio.addEventListener("waiting", () => this.emit({ loading: true }));
    audio.addEventListener("canplay", () => this.emit({ loading: false }));
    audio.addEventListener("durationchange", () => {
      if (Number.isFinite(audio.duration) && audio.duration > 0) {
        this.emit({ duration: audio.duration });
      }
    });
    audio.addEventListener("timeupdate", () => {
      const now = Date.now();
      if (now - this.lastTick < 250) return;
      this.lastTick = now;
      this.emit({ currentTime: audio.currentTime });
    });
    audio.addEventListener("ended", () => {
      void this.next(true);
    });
    audio.addEventListener("error", () => {
      if (!this.state.current) return;
      const unavailable = audio.error?.code === 4;
      const message = unavailable
        ? "Track unavailable. Download it before going offline."
        : "Cannot play this track. Check your connection.";
      this.emit({ playing: false, loading: false, error: message });
      toaster.toast({ title: "Playback failed", body: message });
    });

    this.audio = audio;
    return audio;
  }

  private scheduleScrobble(song: Song): void {
    if (this.scrobbleTimer) clearTimeout(this.scrobbleTimer);
    this.scrobbleTimer = setTimeout(() => {
      if (!this.audio || this.audio.paused) return;
      void api.reportPlay(song.id).catch(() => undefined);
    }, 10000);
  }

  private async start(song: Song, index: number): Promise<void> {
    const url = streamUrl(song.id);
    if (!url) {
      const message = "Media server is not ready yet. Reopen the plugin.";
      this.emit({ error: message });
      toaster.toast({ title: "Navidrome Player", body: message });
      return;
    }
    const audio = this.getAudio();
    this.emit({
      index,
      current: song,
      currentTime: 0,
      duration: song.duration || 0,
      error: null,
      loading: true,
    });
    audio.src = url;
    try {
      await audio.play();
    } catch (error) {
      const message = errorMessage(error);
      this.emit({ playing: false, loading: false, error: message });
      toaster.toast({ title: "Playback failed", body: message });
      return;
    }
    void api.prefetchSong(song).catch(() => undefined);
    this.scheduleScrobble(song);
  }

  async playQueue(songs: Song[], startIndex = 0): Promise<void> {
    const queue = songs.filter((song) => Boolean(song?.id));
    if (!queue.length) return;
    const index = clamp(Math.floor(startIndex), 0, queue.length - 1);
    this.emit({ queue });
    await this.start(queue[index], index);
  }

  async playShuffled(songs: Song[]): Promise<void> {
    if (!songs.length) return;
    if (!this.state.shuffle) this.setShuffle(true);
    await this.playQueue(shuffleArray(songs), 0);
  }

  async playRandom(size = 30): Promise<void> {
    try {
      const songs = await api.getRandomSongs(size);
      if (!songs.length) {
        toaster.toast({ title: "Navidrome Player", body: "No songs found on the server." });
        return;
      }
      await this.playShuffled(songs);
    } catch (error) {
      toaster.toast({ title: "Navidrome Player", body: errorMessage(error) });
    }
  }

  async toggle(): Promise<void> {
    if (this.state.playing) {
      this.audio?.pause();
      return;
    }
    if (this.state.current && this.audio) {
      try {
        await this.audio.play();
      } catch (error) {
        const message = errorMessage(error);
        this.emit({ error: message });
        toaster.toast({ title: "Playback failed", body: message });
      }
      return;
    }
    await this.playRandom();
  }

  async next(fromEnded = false): Promise<void> {
    if (this.transitioning) return;
    const { queue, index, repeat, shuffle } = this.state;
    if (!queue.length) return;
    if (fromEnded && repeat === "one") {
      if (this.audio) {
        this.audio.currentTime = 0;
        void this.audio.play();
      }
      return;
    }

    this.transitioning = true;
    try {
      let nextIndex = index + 1;
      let nextQueue = queue;
      if (nextIndex >= queue.length) {
        if (shuffle) {
          try {
            const more = await api.getRandomSongs(30);
            const seen = new Set(queue.map((song) => song.id));
            const fresh = more.filter((song) => !seen.has(song.id));
            if (fresh.length) {
              nextQueue = [...queue, ...fresh].slice(-200);
              nextIndex = queue.length;
            } else if (repeat === "all" || !fromEnded) {
              nextIndex = 0;
            }
          } catch {
            if (repeat === "all" || !fromEnded) {
              nextIndex = 0;
            }
          }
        } else if (repeat === "all" || !fromEnded) {
          nextIndex = 0;
        }
        if (nextIndex >= nextQueue.length) {
          this.stopAtEnd();
          return;
        }
      }
      if (nextQueue !== queue) this.emit({ queue: nextQueue });
      const song = this.state.queue[nextIndex];
      if (!song) {
        this.stopAtEnd();
        return;
      }
      await this.start(song, nextIndex);
    } finally {
      this.transitioning = false;
    }
  }

  private stopAtEnd(): void {
    this.audio?.pause();
    this.emit({ playing: false, currentTime: this.state.duration });
  }

  async previous(): Promise<void> {
    if (!this.state.queue.length) return;
    if (this.audio && this.audio.currentTime > 3) {
      this.seek(0);
      return;
    }
    const nextIndex = this.state.index - 1 < 0 ? this.state.queue.length - 1 : this.state.index - 1;
    await this.start(this.state.queue[nextIndex], nextIndex);
  }

  seek(seconds: number): void {
    if (!this.audio) return;
    const duration = this.audio.duration;
    const value = Number.isFinite(duration) && duration > 0 ? clamp(seconds, 0, duration) : Math.max(0, seconds);
    try {
      this.audio.currentTime = value;
      this.emit({ currentTime: value });
    } catch {
      // Seeking before metadata is loaded can throw; ignore.
    }
  }

  setVolume(volume: number): void {
    const value = clamp(volume, 0, 1);
    if (this.audio) this.audio.volume = value;
    write(VOLUME_KEY, String(value));
    this.emit({ volume: value });
  }

  setShuffle(shuffle: boolean): void {
    write(SHUFFLE_KEY, String(shuffle));
    this.emit({ shuffle });
  }

  toggleShuffle(): void {
    this.setShuffle(!this.state.shuffle);
  }

  cycleRepeat(): void {
    const next: RepeatMode =
      this.state.repeat === "off" ? "all" : this.state.repeat === "all" ? "one" : "off";
    write(REPEAT_KEY, next);
    this.emit({ repeat: next });
  }

  destroy(): void {
    if (this.scrobbleTimer) clearTimeout(this.scrobbleTimer);
    if (this.audio) {
      this.audio.pause();
      this.audio.removeAttribute("src");
      this.audio.load();
      this.audio = null;
    }
  }
}

export const player = new PlayerStore();

export function usePlayer(): PlayerState {
  return useSyncExternalStore(player.subscribe, player.getSnapshot, player.getSnapshot);
}
