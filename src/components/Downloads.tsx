import { useState } from "react";
import {
  PanelSection,
  PanelSectionRow,
  ProgressBar,
  ToggleField,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { FaDownload, FaRandom, FaTrash } from "react-icons/fa";
import { api, errorMessage } from "../api";
import { formatBytes, formatCount } from "../format";
import { player, usePlayer } from "../state/player";
import type { CacheStats, Settings, Song } from "../types";
import { ActionButton, ButtonRow, EmptyState, SongRow, SubTitle } from "./Common";

export function Downloads({
  stats,
  downloads,
  settings,
  onRefresh,
  onSettingsChange,
}: {
  stats: CacheStats | null;
  downloads: Song[];
  settings: Settings | null;
  onRefresh: () => void;
  onSettingsChange: (settings: Settings) => void;
}) {
  const state = usePlayer();
  const [busy, setBusy] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  const used = stats?.totalBytes ?? 0;
  const limit = stats?.limitBytes ?? settings?.cache_limit_bytes ?? 0;
  const percent = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;

  const toggleAutoCache = async (checked: boolean) => {
    if (!settings) return;
    try {
      const saved = await api.saveSettings({ ...settings, cache_played_songs: checked });
      onSettingsChange(saved);
    } catch (error) {
      toaster.toast({ title: "Could not save setting", body: errorMessage(error) });
    }
  };

  const downloadQueue = async () => {
    if (!state.queue.length) {
      toaster.toast({ title: "Downloads", body: "The play queue is empty." });
      return;
    }
    setBusy(true);
    try {
      const result = await api.downloadSongs(state.queue);
      toaster.toast({
        title: "Downloads",
        body:
          result.queued > 0
            ? `Queued ${formatCount(result.queued, "song")} for offline use.`
            : "The whole queue is already cached.",
      });
    } catch (error) {
      toaster.toast({ title: "Download failed", body: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (song: Song) => {
    try {
      await api.deleteDownload(song.id);
      toaster.toast({ title: "Download removed", body: song.title });
      onRefresh();
    } catch (error) {
      toaster.toast({ title: "Could not remove download", body: errorMessage(error) });
    }
  };

  const clearAuto = async () => {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    setBusy(true);
    try {
      await api.clearCache(false);
      setConfirmClear(false);
      toaster.toast({
        title: "Cache cleared",
        body: `Removed ${formatBytes(stats?.autoBytes ?? 0)} of automatic cache.`,
      });
      onRefresh();
    } catch (error) {
      toaster.toast({ title: "Could not clear cache", body: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <PanelSection>
      <PanelSectionRow>
        <div style={{ padding: "2px 2px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
            <span style={{ fontWeight: 700 }}>
              {formatBytes(used)} <span style={{ color: "#8f98a0", fontWeight: 400 }}>of {formatBytes(limit)}</span>
            </span>
            <span style={{ color: stats?.overLimit ? "#ff8a80" : "#8f98a0" }}>
              {stats ? formatCount(stats.trackCount, "track") : "—"}
            </span>
          </div>
          <div style={{ marginTop: 6 }}>
            <ProgressBar nProgress={percent / 100} />
          </div>
          <div style={{ fontSize: 10, color: "#8f98a0", marginTop: 5 }}>
            {stats
              ? `${formatBytes(stats.pinnedBytes)} downloads · ${formatBytes(stats.autoBytes)} auto-cache`
              : "Cache statistics unavailable"}
            {stats?.overLimit ? " · over limit: pinned downloads are never deleted automatically" : ""}
          </div>
        </div>
      </PanelSectionRow>

      {settings && (
        <ToggleField
          label="Cache songs while playing"
          description="Keeps recent tracks offline. Old tracks are removed when the cache is full."
          checked={settings.cache_played_songs}
          onChange={(checked) => void toggleAutoCache(checked)}
        />
      )}

      <PanelSectionRow>
        <ButtonRow>
          <ActionButton
            primary
            disabled={!downloads.length}
            onClick={() => void player.playQueue(downloads, 0)}
            style={{ flex: 1 }}
          >
            Play downloads
          </ActionButton>
          <ActionButton
            disabled={!downloads.length}
            onClick={() => void player.playShuffled(downloads)}
            style={{ flex: 1 }}
          >
            <FaRandom size={10} /> Shuffle
          </ActionButton>
        </ButtonRow>
      </PanelSectionRow>
      <PanelSectionRow>
        <ActionButton disabled={busy} onClick={() => void downloadQueue()}>
          <FaDownload size={11} /> Download current queue ({state.queue.length})
        </ActionButton>
      </PanelSectionRow>

      <SubTitle text={`Downloads (${downloads.length})`} />
      {downloads.map((song) => (
        <SongRow
          key={song.id}
          song={{ ...song, isDownloaded: true, isCached: true }}
          onPlay={() => {
            const index = downloads.findIndex((item) => item.id === song.id);
            void player.playQueue(downloads, Math.max(0, index));
          }}
          action={{
            icon: <FaTrash size={11} />,
            label: `Delete download ${song.title}`,
            onClick: () => void remove(song),
          }}
        />
      ))}
      {!downloads.length && (
        <EmptyState text="No manual downloads yet. Use the download buttons while browsing, or save the queue." />
      )}

      <PanelSectionRow>
        <ActionButton danger={confirmClear} disabled={busy} onClick={() => void clearAuto()}>
          {confirmClear ? "Tap again to clear automatic cache" : "Clear automatic cache"}
        </ActionButton>
      </PanelSectionRow>
    </PanelSection>
  );
}
