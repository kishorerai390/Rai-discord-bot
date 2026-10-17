"use client";

import React from "react";
import { useMusic } from "@/context/MusicContext";
import { AudioView } from "@/components/views/AudioView";

export default function AudioPage() {
  const { activeGuildId, session, dispatchControl, showToast } = useMusic();

  return (
    <AudioView
      guildId={activeGuildId}
      session={session}
      onControl={dispatchControl}
      onShowToast={showToast}
    />
  );
}
