"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useMusic } from "@/context/MusicContext";
import { DashboardView } from "@/components/views/DashboardView";

export default function DashboardPage() {
  const router = useRouter();
  const {
    activeGuildId,
    session,
    queue,
    currentUser,
    playbackSeconds,
    dispatchControl,
    setIsPlaylistModalOpen,
  } = useMusic();

  return (
    <DashboardView
      guildId={activeGuildId}
      session={session}
      queue={queue}
      user={currentUser}
      playbackSeconds={playbackSeconds}
      onNavigate={(route) => router.push(route)}
      onControl={dispatchControl}
      onOpenPlaylistModal={() => setIsPlaylistModalOpen(true)}
    />
  );
}
