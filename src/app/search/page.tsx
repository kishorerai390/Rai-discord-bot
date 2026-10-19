"use client";

import React from "react";
import { useMusic } from "@/context/MusicContext";
import { SearchView } from "@/components/views/SearchView";

export default function SearchPage() {
  const { activeGuildId, enqueueTrack, dispatchControl, showToast } = useMusic();

  return (
    <SearchView
      guildId={activeGuildId}
      onEnqueue={enqueueTrack}
      onControl={dispatchControl}
      onShowToast={showToast}
    />
  );
}
