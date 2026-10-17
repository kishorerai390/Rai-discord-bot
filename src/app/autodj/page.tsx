"use client";

import React from "react";
import { useMusic } from "@/context/MusicContext";
import { AutoDJView } from "@/components/views/AutoDJView";

export default function AutoDJPage() {
  const { activeGuildId, session, dispatchControl, enqueueTrack, showToast } = useMusic();

  return (
    <AutoDJView
      guildId={activeGuildId}
      session={session}
      onControl={dispatchControl}
      onEnqueue={enqueueTrack}
      onShowToast={showToast}
    />
  );
}
