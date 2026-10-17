"use client";

import React from "react";
import { useMusic } from "@/context/MusicContext";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { PlayerBar } from "@/components/PlayerBar";
import { PlaylistModal } from "@/components/PlaylistModal";
import { ToastContainer } from "@/components/Toast";

export function AppShell({ children }: { children: React.ReactNode }) {
  const {
    currentUser,
    guilds,
    activeGuildId,
    setActiveGuildId,
    session,
    queue,
    toasts,
    dismissToast,
    dispatchControl,
    showToast,
    isPlaylistModalOpen,
    setIsPlaylistModalOpen,
    mobileOpen,
    setMobileOpen,
  } = useMusic();

  return (
    <div className="flex min-h-screen bg-[var(--bg-dark)] text-white relative">
      {/* MOBILE BACKDROP */}
      {mobileOpen && (
        <div
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 bg-black/70 backdrop-blur-sm z-40 md:hidden"
        />
      )}

      {/* SIDEBAR NAVIGATION */}
      <Sidebar
        currentUser={currentUser}
        guilds={guilds}
        activeGuildId={activeGuildId}
        onSelectGuild={(id) => setActiveGuildId(id)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        voiceStatusText={session?.voice_channel_name ? `🔊 ${session.voice_channel_name}` : "320kbps Online"}
      />

      {/* MAIN VIEWPORT */}
      <div className="flex-1 flex flex-col md:pl-[var(--sidebar-width)] pb-[var(--player-height)] min-h-screen min-w-0">
        <TopBar
          onToggleMobile={() => setMobileOpen(!mobileOpen)}
          voiceStatusText={session?.voice_channel_name ? `🔊 ${session.voice_channel_name}` : "320kbps Online"}
        />

        <main className="flex-1 p-4 md:p-8 max-w-7xl w-full mx-auto animate-in fade-in duration-300">
          {children}
        </main>
      </div>

      {/* BOTTOM PERSISTENT PLAYER */}
      <PlayerBar
        session={session}
        onDispatchControl={dispatchControl}
      />

      {/* SAVE PLAYLIST MODAL */}
      <PlaylistModal
        isOpen={isPlaylistModalOpen}
        onClose={() => setIsPlaylistModalOpen(false)}
        guildId={activeGuildId}
        queue={queue}
        onShowToast={showToast}
      />

      {/* TOAST SYSTEM */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
