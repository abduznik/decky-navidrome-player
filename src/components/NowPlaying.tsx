import { useState } from "react";
import { PanelSection, PanelSectionRow, SliderField } from "@decky/ui";
import { toaster } from "@decky/api";
import {
  FaDownload,
  FaPause,
  FaPlay,
  FaRandom,
  FaRedo,
  FaStepBackward,
  FaStepForward,
  FaVolumeMute,
  FaVolumeUp,
} from "react-icons/fa";
import { api, errorMessage } from "../api";
import { formatTime } from "../format";
import { player, usePlayer } from "../state/player";
import type { Song } from "../types";
import { ActionButton, Cover, EmptyState, IconButton, SongRow, SubTitle } from "./Common";

export function NowPlaying() {
  const state = usePlayer();
  const [busy, setBusy] = useState(false);

  const download = async (songs: Song[]) => {
    if (!songs.length) {
      toaster.toast({ title: "Downloads", body: "Nothing to download." });
      return;
    }
    setBusy(true);
    try {
      const result = await api.downloadSongs(songs);
      toaster.toast({
        title: "Download queued",
        body:
          result.queued > 0
            ? `${result.queued} song${result.queued === 1 ? "" : "s"} added to the queue.`
            : "Everything was already cached.",
      });
    } catch (error) {
      toaster.toast({ title: "Download failed", body: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  };

  if (!state.current) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <div style={{ textAlign: "center", padding: "12px 0 6px" }}>
            <FaPlay size={26} color="#8f98a0" />
            <div style={{ fontSize: 14, fontWeight: 600, marginTop: 8 }}>Nothing playing</div>
            <div style={{ fontSize: 11, color: "#8f98a0", marginTop: 3 }}>
              Start an endless random mix from your Navidrome library.
            </div>
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ActionButton primary onClick={() => void player.playRandom()}>
            <FaRandom size={12} /> Play random mix
          </ActionButton>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ fontSize: 11, color: "#8f98a0", textAlign: "center" }}>
            Browse playlists, albums and search in the Library tab.
          </div>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const current = state.current;
  const duration = state.duration || current.duration || 0;
  const upcoming = state.queue.slice(state.index + 1, state.index + 5);

  return (
    <PanelSection>
      <PanelSectionRow>
        <div style={{ display: "flex", justifyContent: "center", paddingTop: 4 }}>
          <Cover coverArt={current.coverArt} size={132} radius={10} />
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ textAlign: "center", padding: "2px 4px 0" }}>
          <div
            style={{
              fontSize: 15,
              fontWeight: 700,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {current.title}
          </div>
          <div style={{ fontSize: 12, color: "#cfd3d6" }}>{current.artist || "Unknown artist"}</div>
          {current.album && <div style={{ fontSize: 11, color: "#8f98a0" }}>{current.album}</div>}
        </div>
      </PanelSectionRow>

      {state.error && (
        <PanelSectionRow>
          <div style={{ fontSize: 11, color: "#ff8a80", textAlign: "center" }}>{state.error}</div>
        </PanelSectionRow>
      )}

      <PanelSectionRow>
        <SliderField
          label={`${formatTime(state.currentTime)} / ${formatTime(duration)}`}
          value={Math.min(state.currentTime, Math.max(0.1, duration))}
          min={0}
          max={Math.max(0.1, duration)}
          step={1}
          showValue={false}
          disabled={duration <= 0}
          onChange={(value) => player.seek(value)}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            padding: "2px 0 4px",
          }}
        >
          <IconButton
            icon={<FaRandom size={15} />}
            label={state.shuffle ? "Shuffle on" : "Shuffle off"}
            active={state.shuffle}
            onClick={() => player.toggleShuffle()}
          />
          <IconButton
            icon={<FaStepBackward size={16} />}
            label="Previous"
            onClick={() => void player.previous()}
          />
          <IconButton
            icon={state.playing ? <FaPause size={18} /> : <FaPlay size={18} />}
            label={state.playing ? "Pause" : "Play"}
            size={48}
            active
            onClick={() => void player.toggle()}
          />
          <IconButton
            icon={<FaStepForward size={16} />}
            label="Next"
            onClick={() => void player.next()}
          />
          <IconButton
            icon={<FaRedo size={15} />}
            label={`Repeat: ${state.repeat}`}
            active={state.repeat !== "off"}
            onClick={() => player.cycleRepeat()}
          />
        </div>
      </PanelSectionRow>

      <PanelSectionRow>
        <SliderField
          label={state.volume === 0 ? "Volume (muted)" : "Volume"}
          value={Math.round(state.volume * 100)}
          min={0}
          max={100}
          step={1}
          showValue
          valueSuffix="%"
          onChange={(value) => player.setVolume(value / 100)}
        />
      </PanelSectionRow>

      <PanelSectionRow>
        <div style={{ display: "flex", gap: 6, alignItems: "center", justifyContent: "center" }}>
          {state.volume === 0 ? (
            <FaVolumeMute size={13} color="#8f98a0" />
          ) : (
            <FaVolumeUp size={13} color="#8f98a0" />
          )}
          <span style={{ fontSize: 11, color: "#8f98a0" }}>
            {state.playing ? "Playing" : state.loading ? "Buffering…" : "Paused"}
            {state.repeat === "one" ? " · repeat one" : state.repeat === "all" ? " · repeat all" : ""}
          </span>
        </div>
      </PanelSectionRow>

      <PanelSectionRow>
        <div style={{ display: "flex", gap: 6 }}>
          <ActionButton disabled={busy} onClick={() => void download([current])} style={{ flex: 1 }}>
            <FaDownload size={11} /> Save song
          </ActionButton>
          <ActionButton
            disabled={busy || !state.queue.length}
            onClick={() => void download(state.queue)}
            style={{ flex: 1 }}
          >
            Save queue ({state.queue.length})
          </ActionButton>
        </div>
      </PanelSectionRow>

      {upcoming.length > 0 ? (
        <>
          <SubTitle text="Up next" />
          {upcoming.map((song, offset) => (
            <SongRow
              key={`${song.id}-${offset}`}
              song={song}
              onPlay={() => void player.playQueue(state.queue, state.index + 1 + offset)}
            />
          ))}
        </>
      ) : (
        <EmptyState text="End of queue — next starts a fresh random mix." />
      )}
    </PanelSection>
  );
}
