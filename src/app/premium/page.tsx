"use client";

import React from "react";
import { useMusic } from "@/context/MusicContext";
import { PremiumView } from "@/components/views/PremiumView";

export default function PremiumPage() {
  const { currentUser, showToast, refreshAll } = useMusic();

  return (
    <PremiumView
      user={currentUser}
      onShowToast={showToast}
      onRefreshUser={refreshAll}
    />
  );
}
