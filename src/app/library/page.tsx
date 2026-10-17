"use client";

import React from "react";
import { useMusic } from "@/context/MusicContext";
import { LibraryView } from "@/components/views/LibraryView";

export default function LibraryPage() {
  const { activeGuildId, enqueueTrack, setIsPlaylistModalOpen, showToast } = useMusic();

  return (
    <LibraryView
      guildId={activeGuildId}
      onEnqueue={enqueueTrack}
      onOpenPlaylistModal={() => setIsPlaylistModalOpen(true)}
      onShowToast={showToast}
    />
  );
}
