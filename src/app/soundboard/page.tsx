"use client";

import React from "react";
import { useMusic } from "@/context/MusicContext";
import { SoundboardView } from "@/components/views/SoundboardView";

export default function SoundboardPage() {
  const { activeGuildId, showToast } = useMusic();

  return (
    <SoundboardView
      guildId={activeGuildId}
      onShowToast={showToast}
    />
  );
}
