"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useMusic } from "@/context/MusicContext";
import { QueueView } from "@/components/views/QueueView";

export default function QueuePage() {
  const router = useRouter();
  const {
    activeGuildId,
    queue,
    dispatchControl,
    setIsPlaylistModalOpen,
    showToast,
  } = useMusic();

  return (
    <QueueView
      guildId={activeGuildId}
      queue={queue}
      onControl={dispatchControl}
      onNavigate={(r) => router.push(r)}
      onOpenPlaylistModal={() => setIsPlaylistModalOpen(true)}
      onShowToast={showToast}
    />
  );
}
