import { useEffect, useState, type ReactNode } from "react";
import { Focusable } from "@decky/ui";
import { FaCheckCircle, FaDownload, FaMusic } from "react-icons/fa";
import { artUrl } from "../api";
import { formatCount } from "../format";
import type { Album, Song } from "../types";

const ACCENT = "#1a9fff";
const MUTED = "#8f98a0";

export function IconButton({
  icon,
  label,
  onClick,
  active = false,
  disabled = false,
  size = 38,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  size?: number;
}) {
  const [focused, setFocused] = useState(false);
  return (
    <Focusable
      aria-label={label}
      title={label}
      onActivate={disabled ? undefined : onClick}
      onClick={disabled ? undefined : onClick}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      style={{
        width: size,
        height: size,
        minWidth: size,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: 8,
        cursor: disabled ? "default" : "pointer",
        color: disabled ? "#5b6066" : active ? ACCENT : "#ffffff",
        background: active ? "rgba(26,159,255,0.18)" : "rgba(255,255,255,0.06)",
        boxShadow: focused ? `0 0 0 2px ${ACCENT}` : "none",
        opacity: disabled ? 0.6 : 1,
        transition: "background 120ms ease, box-shadow 120ms ease",
      }}
    >
      {icon}
    </Focusable>
  );
}

export function Cover({
  coverArt,
  size,
  radius = 8,
}: {
  coverArt: string;
  size: number;
  radius?: number;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [coverArt]);
  const src = artUrl(coverArt, size);

  if (!src || failed) {
    return (
      <div
        style={{
          width: size,
          height: size,
          minWidth: size,
          borderRadius: radius,
          background: "linear-gradient(135deg, #2a3a4a 0%, #16202a 100%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: MUTED,
        }}
      >
        <FaMusic size={Math.max(14, size * 0.34)} />
      </div>
    );
  }

  return (
    <img
      src={src}
      width={size}
      height={size}
      onError={() => setFailed(true)}
      style={{
        width: size,
        height: size,
        minWidth: size,
        objectFit: "cover",
        borderRadius: radius,
        background: "#16202a",
      }}
    />
  );
}

export function SongRow({
  song,
  onPlay,
  action,
  subtitle,
  showCover = true,
  showBadges = true,
}: {
  song: Song;
  onPlay: () => void;
  action?: { icon: ReactNode; label: string; onClick: () => void };
  subtitle?: string;
  showCover?: boolean;
  showBadges?: boolean;
}) {
  const [focused, setFocused] = useState(false);
  const label = subtitle ?? [song.artist, song.album].filter(Boolean).join(" · ");

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
      <Focusable
        onActivate={onPlay}
        onClick={onPlay}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: "5px 7px",
          borderRadius: 7,
          cursor: "pointer",
          background: focused ? "rgba(255,255,255,0.12)" : "transparent",
          boxShadow: focused ? `0 0 0 2px ${ACCENT}` : "none",
        }}
      >
        {showCover && <Cover coverArt={song.coverArt} size={38} radius={5} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {song.title}
          </div>
          <div
            style={{
              fontSize: 11,
              color: MUTED,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {label || "Unknown artist"}
          </div>
        </div>
        {showBadges && song.isDownloaded && (
          <FaDownload size={11} color={ACCENT} title="Downloaded" />
        )}
        {showBadges && !song.isDownloaded && song.isCached && (
          <FaCheckCircle size={11} color="#61c554" title="Cached" />
        )}
      </Focusable>
      {action && (
        <IconButton icon={action.icon} label={action.label} onClick={action.onClick} size={32} />
      )}
    </div>
  );
}

export function AlbumRow({ album, onOpen }: { album: Album; onOpen: () => void }) {
  const [focused, setFocused] = useState(false);
  return (
    <Focusable
      onActivate={onOpen}
      onClick={onOpen}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 9,
        padding: "5px 7px",
        borderRadius: 7,
        marginBottom: 4,
        cursor: "pointer",
        background: focused ? "rgba(255,255,255,0.12)" : "transparent",
        boxShadow: focused ? `0 0 0 2px ${ACCENT}` : "none",
      }}
    >
      <Cover coverArt={album.coverArt} size={44} radius={5} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {album.name}
        </div>
        <div
          style={{
            fontSize: 11,
            color: MUTED,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {[album.artist, formatCount(album.songCount, "song")].filter(Boolean).join(" · ")}
        </div>
      </div>
    </Focusable>
  );
}

export function EmptyState({ text }: { text: string }) {
  return (
    <div
      style={{
        padding: "10px 6px",
        color: MUTED,
        fontSize: 12,
        textAlign: "center",
      }}
    >
      {text}
    </div>
  );
}

export function SubTitle({ text }: { text: string }) {
  return (
    <div
      style={{
        fontSize: 10,
        letterSpacing: 0.8,
        textTransform: "uppercase",
        color: MUTED,
        margin: "10px 4px 5px",
        fontWeight: 700,
      }}
    >
      {text}
    </div>
  );
}
