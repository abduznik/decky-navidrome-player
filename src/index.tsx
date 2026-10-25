import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  PanelSection,
  PanelSectionRow,
  ProgressBar,
  staticClasses,
} from "@decky/ui";
import {
  addEventListener,
  definePlugin,
  removeEventListener,
  toaster,
  useQuickAccessVisible,
} from "@decky/api";
import { FaCog, FaDownload, FaListUl, FaMusic, FaPlay } from "react-icons/fa";
import { api, errorMessage, mediaBaseReady, primeMediaBase } from "./api";
import { player } from "./state/player";
import type {
  CacheStats,
  DownloadProgress,
  Settings,
  Song,
  Tab,
} from "./types";
import { Downloads } from "./components/Downloads";
import { Library } from "./components/Library";
import { NowPlaying } from "./components/NowPlaying";
import { SettingsView } from "./components/SettingsView";
import { ActionButton, ButtonRow, IconButton } from "./components/Common";

function Content() {
  const [tab, setTab] = useState<Tab>("now");
  const [ready, setReady] = useState(mediaBaseReady());
  const [settings, setSettings] = useState<Settings | null>(null);
  const [stats, setStats] = useState<CacheStats | null>(null);
  const [downloads, setDownloads] = useState<Song[]>([]);
  const [progress, setProgress] = useState<DownloadProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const visible = useQuickAccessVisible();
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoTabbed = useRef(false);

  const refreshAll = useCallback(async () => {
    try {
      const [nextSettings, nextStats, nextDownloads] = await Promise.all([
        api.getSettings(),
        api.getCacheStats(),
        api.getDownloads(),
      ]);
      setSettings(nextSettings);
      setStats(nextStats);
      setDownloads(nextDownloads);
      setError(null);
      if (!nextSettings.configured && !autoTabbed.current) {
        autoTabbed.current = true;
        setTab("settings");
      }
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  const refreshSoon = useCallback(() => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(() => {
      void refreshAll();
    }, 350);
  }, [refreshAll]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        await primeMediaBase();
        if (!alive) return;
        setReady(true);
      } catch (err) {
        if (alive) setError(errorMessage(err));
        return;
      }
      await refreshAll();
    })();
    return () => {
      alive = false;
    };
  }, [refreshAll]);

  useEffect(() => {
    if (visible) void refreshAll();
  }, [visible, refreshAll]);

  useEffect(() => {
    const onProgress = addEventListener<[DownloadProgress]>("download_progress", (event) => {
      if (event.pinned) setProgress(event);
    });
    const onComplete = addEventListener<[{ id: string; title: string; pinned: boolean }]>(
      "download_complete",
      (event) => {
        if (event.pinned) {
          setProgress(null);
          toaster.toast({ title: "Download complete", body: event.title });
        }
        refreshSoon();
      },
    );
    const onFailed = addEventListener<
      [{ id: string; title: string; error: string; pinned: boolean }]
    >("download_failed", (event) => {
      setProgress(null);
      if (event.pinned) {
        toaster.toast({ title: "Download failed", body: `${event.title}: ${event.error}` });
      }
      refreshSoon();
    });
    const onUpdated = addEventListener<[unknown]>("downloads_updated", () => refreshSoon());
    return () => {
      removeEventListener("download_progress", onProgress);
      removeEventListener("download_complete", onComplete);
      removeEventListener("download_failed", onFailed);
      removeEventListener("downloads_updated", onUpdated);
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, [refreshSoon]);

  const tabs: { id: Tab; label: string; icon: ReactNode }[] = [
    { id: "now", label: "Player", icon: <FaPlay size={11} /> },
    { id: "library", label: "Library", icon: <FaListUl size={11} /> },
    { id: "downloads", label: "Offline", icon: <FaDownload size={11} /> },
    { id: "settings", label: "Settings", icon: <FaCog size={11} /> },
  ];

  return (
    <>
      <PanelSection>
        <ButtonRow style={{ gap: 5, padding: "0 2px" }}>
          {tabs.map((item) => (
            <TabButton
              key={item.id}
              active={tab === item.id}
              label={item.label}
              icon={item.icon}
              onClick={() => setTab(item.id)}
            />
          ))}
        </ButtonRow>
      </PanelSection>

      {error && (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ fontSize: 11, color: "#ff8a80", textAlign: "center" }}>{error}</div>
          </PanelSectionRow>
        </PanelSection>
      )}

      {!ready && (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ fontSize: 12, color: "#8f98a0", textAlign: "center" }}>
              Starting local media server…
            </div>
          </PanelSectionRow>
        </PanelSection>
      )}

      {ready && !settings?.configured && tab !== "settings" && (
        <PanelSection>
          <PanelSectionRow>
            <ActionButton primary onClick={() => setTab("settings")}>
              Set up your Navidrome server
            </ActionButton>
          </PanelSectionRow>
        </PanelSection>
      )}

      {progress && progress.pinned && progress.percent < 100 && (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ fontSize: 11, color: "#cfd3d6" }}>
              Downloading {progress.title || "song"}… {progress.percent}%
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ProgressBar nProgress={progress.percent / 100} />
          </PanelSectionRow>
        </PanelSection>
      )}

      {ready && tab === "now" && <NowPlaying />}
      {ready && tab === "library" && <Library />}
      {ready && tab === "downloads" && (
        <Downloads
          stats={stats}
          downloads={downloads}
          settings={settings}
          onRefresh={() => void refreshAll()}
          onSettingsChange={setSettings}
        />
      )}
      {ready && tab === "settings" && (
        <SettingsView
          settings={settings}
          stats={stats}
          onSaved={(saved) => {
            const wasConfigured = settings?.configured ?? false;
            setSettings(saved);
            if (!wasConfigured && saved.configured) {
              setTab("now");
            }
            void refreshAll();
          }}
          onStats={() => void refreshAll()}
        />
      )}
    </>
  );
}

function TabButton({
  active,
  label,
  icon,
  onClick,
}: {
  active: boolean;
  label: string;
  icon: ReactNode;
  onClick: () => void;
}) {
  return (
    <IconButton
      icon={
        <span style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, fontSize: 9 }}>
          {icon}
          <span>{label}</span>
        </span>
      }
      label={label}
      active={active}
      onClick={onClick}
      size={62}
    />
  );
}

export default definePlugin(() => {
  console.log("Navidrome Player initializing");
  void primeMediaBase().catch((error) => {
    console.error("Could not start the local media server", error);
  });

  return {
    name: "Navidrome Player",
    titleView: (
      <div className={staticClasses.Title} style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <FaMusic size={16} /> Navidrome Player
      </div>
    ),
    content: <Content />,
    icon: <FaMusic />,
    onDismount() {
      player.destroy();
    },
  };
});
