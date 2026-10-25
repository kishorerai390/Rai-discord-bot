"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import type { DiscordUser } from "@/types/auth";
import type { MusicSession, Track, GuildOption } from "@/types/music";
import type { ToastMessage } from "@/components/Toast";

interface MusicContextType {
  currentUser: DiscordUser | null;
  guilds: GuildOption[];
  activeGuildId: string;
  setActiveGuildId: (id: string) => void;
  session: MusicSession | null;
  queue: Track[];
  playbackSeconds: number;
  toasts: ToastMessage[];
  showToast: (text: string, type?: "success" | "danger" | "info") => void;
  dismissToast: (id: string) => void;
  dispatchControl: (action: string, payload?: any) => Promise<void>;
  enqueueTrack: (query: string) => Promise<boolean>;
  toggleFavorite: () => Promise<void>;
  refreshAll: () => Promise<void>;
  isPlaylistModalOpen: boolean;
  setIsPlaylistModalOpen: (open: boolean) => void;
  mobileOpen: boolean;
  setMobileOpen: (open: boolean) => void;
}

const MusicContext = createContext<MusicContextType | null>(null);

export function useMusic() {
  const context = useContext(MusicContext);
  if (!context) {
    throw new Error("useMusic must be used within a MusicProvider");
  }
  return context;
}

export function MusicProvider({ children }: { children: React.ReactNode }) {
  const [currentUser, setCurrentUser] = useState<DiscordUser | null>(null);
  const [guilds, setGuilds] = useState<GuildOption[]>([]);
  const [activeGuildId, setActiveGuildId] = useState<string>("1525030316845301781");
  const [session, setSession] = useState<MusicSession | null>(null);
  const [queue, setQueue] = useState<Track[]>([]);
  const [playbackSeconds, setPlaybackSeconds] = useState<number>(0);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [isPlaylistModalOpen, setIsPlaylistModalOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const progressTimerRef = useRef<NodeJS.Timeout | null>(null);

  const showToast = useCallback((text: string, type: "success" | "danger" | "info" = "info") => {
    const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    setToasts((prev) => [...prev, { id, text, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Fetch current user and guilds
  const fetchAuthAndGuilds = useCallback(async () => {
    try {
      const [uRes, gRes] = await Promise.all([
        fetch("/api/auth/me"),
        fetch("/api/music/guilds"),
      ]);
      const uData = await uRes.json();
      const gData = await gRes.json();

      const user = uData.data?.user ?? uData.user ?? null;
      if (user) {
        setCurrentUser(user);
      }

      const rawGuilds = gData.data?.guilds ?? gData.guilds ?? [];
      if (Array.isArray(rawGuilds) && rawGuilds.length > 0) {
        setGuilds(rawGuilds);
        setActiveGuildId((prev) => {
          if (!prev || prev === "1525030316845301781" || !rawGuilds.some((g: any) => g.id === prev)) {
            return rawGuilds[0].id;
          }
          return prev;
        });
      }
    } catch (e) {
      console.warn("Auth & Guilds fetch notice:", e);
    }
  }, []);

  // Synchronize playback session and queue
  const syncPlayback = useCallback(async () => {
    if (!activeGuildId) return;
    try {
      const [sRes, qRes] = await Promise.all([
        fetch(`/api/music/session?guild_id=${encodeURIComponent(activeGuildId)}`),
        fetch(`/api/music/queue?guild_id=${encodeURIComponent(activeGuildId)}`),
      ]);
      const sData = await sRes.json();
      const qData = await qRes.json();

      const sess = sData.data?.session ?? sData.session ?? null;
      if (sess) {
        setSession(sess);
        const pos = typeof sess.elapsed_seconds === "number" ? sess.elapsed_seconds : sess.position_seconds;
        if (typeof pos === "number") {
          setPlaybackSeconds(pos);
        }
      }

      const q = qData.data?.queue ?? qData.queue ?? [];
      if (Array.isArray(q)) {
        setQueue(q);
      }
    } catch (e) {
      console.warn("Playback sync notice:", e);
    }
  }, [activeGuildId]);

  useEffect(() => {
    fetchAuthAndGuilds();
  }, [fetchAuthAndGuilds]);

  useEffect(() => {
    syncPlayback();
    const interval = setInterval(syncPlayback, 4000);
    return () => clearInterval(interval);
  }, [syncPlayback]);

  // Handle local seconds progression when playing
  useEffect(() => {
    if (progressTimerRef.current) clearInterval(progressTimerRef.current);

    if (session?.state === "PLAYING" && !session?.is_paused) {
      progressTimerRef.current = setInterval(() => {
        setPlaybackSeconds((prev) => {
          const total = session.current_track?.duration || 0;
          if (total > 0 && prev >= total) return prev;
          return prev + 1;
        });
      }, 1000);
    }

    return () => {
      if (progressTimerRef.current) clearInterval(progressTimerRef.current);
    };
  }, [session?.state, session?.is_paused, session?.current_track?.duration]);

  // Check URL query parameters for auth notifications
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("auth") === "success") {
        showToast("Signed in with Discord successfully! ✦", "success");
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (params.get("logout") === "success") {
        showToast("Logged out successfully", "info");
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (params.get("error")) {
        const msg = params.get("message") || params.get("error");
        showToast(`Auth notice: ${decodeURIComponent(msg || "")}`, "danger");
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }
  }, [showToast]);

  const toggleFavorite = useCallback(async (trackOverride?: any) => {
    const t = trackOverride || session?.current_track;
    if (!t) return;
    try {
      const res = await fetch("/api/music/favorites/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: t.title,
          url: t.url,
          duration: t.duration,
          artist: t.artist || t.author,
          thumbnail: t.thumbnail,
        }),
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.message || (data.favorited ? "Added to favorites ❤️" : "Removed from favorites"), "success");
      }
    } catch (e: any) {
      showToast(`Favorite error: ${e.message}`, "danger");
    }
  }, [session?.current_track, showToast]);

  const dispatchControl = useCallback(
    async (action: string, payload: any = {}) => {
      if (action === "FAVORITE_TOGGLE") {
        await toggleFavorite(payload);
        return;
      }
      try {
        const res = await fetch("/api/music/control", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            guild_id: activeGuildId,
            action,
            payload,
          }),
        });
        const data = await res.json();
        if (data.success) {
          // Optimistic updates for responsive UI
          if (action === "PAUSE") {
            setSession((prev) => (prev ? { ...prev, is_paused: true, state: "PAUSED" } : null));
          } else if (action === "RESUME") {
            setSession((prev) => (prev ? { ...prev, is_paused: false, state: "PLAYING" } : null));
          } else if (action === "VOLUME" && typeof payload.volume === "number") {
            setSession((prev) => (prev ? { ...prev, volume: payload.volume } : null));
          } else if (action === "247_TOGGLE") {
            setSession((prev) => (prev ? { ...prev, is_247: !prev.is_247 } : null));
          }
          await syncPlayback();
        } else {
          showToast(data.error || "Action failed", "danger");
        }
      } catch (e: any) {
        showToast(`Action failed: ${e.message}`, "danger");
      }
    },
    [activeGuildId, showToast, syncPlayback, toggleFavorite]
  );

  const enqueueTrack = useCallback(
    async (query: string): Promise<boolean> => {
      try {
        const res = await fetch("/api/music/enqueue", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            guild_id: activeGuildId,
            query,
          }),
        });
        const data = await res.json();
        if (data.success) {
          await syncPlayback();
          return true;
        }
        return false;
      } catch {
        return false;
      }
    },
    [activeGuildId, syncPlayback]
  );

  return (
    <MusicContext.Provider
      value={{
        currentUser,
        guilds,
        activeGuildId,
        setActiveGuildId,
        session,
        queue,
        playbackSeconds,
        toasts,
        showToast,
        dismissToast,
        dispatchControl,
        enqueueTrack,
        toggleFavorite,
        refreshAll: syncPlayback,
        isPlaylistModalOpen,
        setIsPlaylistModalOpen,
        mobileOpen,
        setMobileOpen,
      }}
    >
      {children}
    </MusicContext.Provider>
  );
}
