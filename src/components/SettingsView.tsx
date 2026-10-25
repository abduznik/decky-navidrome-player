import { useEffect, useState, type CSSProperties } from "react";
import {
  DropdownItem,
  PanelSection,
  PanelSectionRow,
  SliderField,
  TextField,
  ToggleField,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { FaPlug, FaSave, FaTrash } from "react-icons/fa";
import { api, errorMessage } from "../api";
import { formatBytes } from "../format";
import type { CacheStats, ConnectionResult, Settings } from "../types";
import { ActionButton, ButtonRow, SubTitle } from "./Common";

const GB = 1024 * 1024 * 1024;
const BITRATES = [
  { data: 0, label: "Original quality" },
  { data: 64, label: "64 kbps" },
  { data: 96, label: "96 kbps" },
  { data: 128, label: "128 kbps" },
  { data: 192, label: "192 kbps" },
  { data: 256, label: "256 kbps" },
  { data: 320, label: "320 kbps" },
];

export function SettingsView({
  settings,
  stats,
  onSaved,
  onStats,
}: {
  settings: Settings | null;
  stats: CacheStats | null;
  onSaved: (settings: Settings) => void;
  onStats: () => void;
}) {
  const [form, setForm] = useState<Settings | null>(settings);
  const [test, setTest] = useState<ConnectionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmClear, setConfirmClear] = useState<"auto" | "all" | null>(null);

  useEffect(() => {
    setForm(settings);
  }, [settings]);

  if (!form) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <div style={{ fontSize: 12, color: "#8f98a0", textAlign: "center" }}>Loading settings…</div>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const patch = (changes: Partial<Settings>) => setForm({ ...form, ...changes });

  const save = async () => {
    setBusy(true);
    try {
      const saved = await api.saveSettings(form);
      onSaved(saved);
      toaster.toast({ title: "Settings saved", body: "Navidrome Player is ready." });
    } catch (error) {
      toaster.toast({ title: "Could not save settings", body: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  };

  const testConnection = async () => {
    setBusy(true);
    setTest(null);
    try {
      const result = await api.testConnection(form);
      setTest(result);
      toaster.toast({
        title: result.ok ? "Connected" : "Connection failed",
        body: result.message,
      });
    } catch (error) {
      setTest({ ok: false, message: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  };

  const clear = async (includeDownloads: boolean) => {
    const expected = includeDownloads ? "all" : "auto";
    if (confirmClear !== expected) {
      setConfirmClear(expected);
      return;
    }
    setBusy(true);
    try {
      await api.clearCache(includeDownloads);
      setConfirmClear(null);
      onStats();
      toaster.toast({
        title: "Cache cleared",
        body: includeDownloads ? "All cached music was removed." : "Automatic cache was removed.",
      });
    } catch (error) {
      toaster.toast({ title: "Could not clear cache", body: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  };

  const gbValue = Math.round((form.cache_limit_bytes / GB) * 100) / 100;

  return (
    <PanelSection>
      <SubTitle text="Navidrome server" />
      <PanelSectionRow>
        <TextField
          label="Server URL"
          value={form.server_url}
          placeholder="http://192.168.1.10:4533"
          onChange={(event) => patch({ server_url: event.target.value })}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <TextField
          label="Username"
          value={form.username}
          onChange={(event) => patch({ username: event.target.value })}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <TextField
          label="Password"
          bIsPassword
          bShowCopyAction={false}
          bShowClearAction={false}
          value={form.password}
          style={{ WebkitTextSecurity: "disc" } as CSSProperties}
          onChange={(event) => patch({ password: event.target.value })}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <div
          style={{
            fontSize: 10,
            color: test ? (test.ok ? "#61c554" : "#ff8a80") : "#8f98a0",
            padding: "2px 4px",
          }}
        >
          {test ? test.message : "Credentials are stored locally in the Decky plugin settings folder."}
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonRow>
          <ActionButton disabled={busy} onClick={() => void testConnection()} style={{ flex: 1 }}>
            <FaPlug size={10} /> Test
          </ActionButton>
          <ActionButton primary disabled={busy} onClick={() => void save()} style={{ flex: 1 }}>
            <FaSave size={10} /> Save
          </ActionButton>
        </ButtonRow>
      </PanelSectionRow>

      <SubTitle text="Playback & cache" />
      <PanelSectionRow>
        <DropdownItem
          label="Streaming quality"
          description="Transcoding saves bandwidth and cache space."
          rgOptions={BITRATES}
          selectedOption={form.max_bitrate}
          onChange={(option) => patch({ max_bitrate: Number(option.data) })}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Cache songs while playing"
          description="Automatically keep recently played tracks for offline listening."
          checked={form.cache_played_songs}
          onChange={(checked) => patch({ cache_played_songs: checked })}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <SliderField
          label={`Cache limit (${formatBytes(form.cache_limit_bytes)})`}
          value={gbValue}
          min={0.25}
          max={32}
          step={0.25}
          showValue
          valueSuffix=" GB"
          onChange={(value) => patch({ cache_limit_bytes: Math.round(value * GB) })}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={{ fontSize: 10, color: "#8f98a0", padding: "0 4px 2px" }}>
          Manual downloads are never removed automatically, but they do count toward the limit.
          {stats?.cacheDir ? ` Files: ${stats.cacheDir}` : ""}
        </div>
      </PanelSectionRow>

      <SubTitle text="Storage" />
      <PanelSectionRow>
        <div style={{ fontSize: 11, color: "#8f98a0", padding: "0 4px 4px" }}>
          {stats
            ? `${formatBytes(stats.totalBytes)} used · ${formatBytes(stats.diskFreeBytes)} free on disk`
            : "Cache statistics unavailable"}
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ActionButton danger={confirmClear === "auto"} disabled={busy} onClick={() => void clear(false)}>
          <FaTrash size={10} />{" "}
          {confirmClear === "auto" ? "Tap again: clear auto cache" : "Clear automatic cache"}
        </ActionButton>
      </PanelSectionRow>
      <PanelSectionRow>
        <ActionButton danger={confirmClear === "all"} disabled={busy} onClick={() => void clear(true)}>
          <FaTrash size={10} />{" "}
          {confirmClear === "all" ? "Tap again: delete all music" : "Delete all downloads & cache"}
        </ActionButton>
      </PanelSectionRow>
    </PanelSection>
  );
}
