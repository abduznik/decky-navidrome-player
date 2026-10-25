import { useState } from "react";
import {
  PanelSection,
  PanelSectionRow,
  ProgressBar,
  ToggleField,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { FaDownload, FaListUl, FaRandom, FaTrash } from "react-icons/fa";
import { api, errorMessage } from "../api";
import { formatBytes, formatCount } from "../format";
import { player, usePlayer } from "../state/player";
import type { CacheStats, DownloadQueue, DownloadState, Settings, Song } from "../types";
import { ActionButton, ButtonRow, EmptyState, SongRow, SubTitle } from "./Common";

export function Downloads({
  stats,
  downloads,
  settings,
  queue,
  onRefresh,
  onSettingsChange,
  onClearQueue,
}: {
  stats: CacheStats | null;
  downloads: Song[];
  settings: Settings | null;
  queue: DownloadQueue;
  onRefresh: () => void;
  onSettingsChange: (settings: Settings) => void;
  onClearQueue: () => void;
}) {
  const state = usePlayer();
  const [busy, setBusy] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [showQueue, setShowQueue] = useState(false);
  const activeCount = queue.downloading + queue.pending;
  const finishedCount = queue.done + queue.failed;

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

      <PanelSectionRow>
        <ButtonRow>
          <ActionButton onClick={() => setShowQueue((value) => !value)} style={{ flex: 1 }}>
            <FaListUl size={10} /> Queue
            {activeCount > 0 ? ` (${activeCount})` : ""}
            {queue.failed > 0 ? ` · ${queue.failed} failed` : ""}
          </ActionButton>
          <ActionButton
            disabled={finishedCount === 0}
            onClick={onClearQueue}
            style={{ flex: 1 }}
          >
            Clear finished
          </ActionButton>
        </ButtonRow>
      </PanelSectionRow>

      {showQueue && (
        <>
          {queue.items.length === 0 ? (
            <EmptyState text="The download queue is empty." />
          ) : (
            queue.items.map((item) => (
              <QueueRow key={item.id} item={item} />
            ))
          )}
        </>
      )}

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

const STATE_LABEL: Record<DownloadState, string> = {
  queued: "Queued",
  downloading: "Downloading",
  done: "Done",
  failed: "Failed",
};

function QueueRow({ item }: { item: DownloadQueue["items"][number] }) {
  const color =
    item.state === "failed"
      ? "#ff8a80"
      : item.state === "done"
        ? "#61c554"
        : item.state === "downloading"
          ? "#1a9fff"
          : "#8f98a0";
  return (
    <div
      style={{
        padding: "6px 8px",
        marginBottom: 4,
        borderRadius: 7,
        background: "rgba(255,255,255,0.05)",
      }}
    >
      <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 11 }}>
        <div
          style={{
            flex: 1,
            minWidth: 0,
            fontWeight: 600,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {item.title || item.id}
        </div>
        <div style={{ color, whiteSpace: "nowrap" }}>
          {STATE_LABEL[item.state]}
          {item.state === "downloading" ? ` ${item.percent}%` : ""}
        </div>
      </div>
      {item.state === "downloading" && (
        <div style={{ marginTop: 4 }}>
          <ProgressBar nProgress={item.percent / 100} />
        </div>
      )}
      {item.error && (
        <div style={{ marginTop: 3, fontSize: 10, color: "#ff8a80" }}>{item.error}</div>
      )}
      <div style={{ fontSize: 9, color: "#8f98a0", marginTop: 2 }}>
        {item.pinned ? "Saved download" : "Auto-cache"}
      </div>
    </div>
  );
}
