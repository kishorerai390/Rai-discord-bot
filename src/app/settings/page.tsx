"use client";

import React from "react";
import { useMusic } from "@/context/MusicContext";
import { SettingsView } from "@/components/views/SettingsView";

export default function SettingsPage() {
  const { activeGuildId, currentUser, showToast } = useMusic();

  return (
    <SettingsView
      guildId={activeGuildId}
      user={currentUser}
      onShowToast={showToast}
    />
  );
}
