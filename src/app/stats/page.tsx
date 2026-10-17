"use client";

import React from "react";
import { useMusic } from "@/context/MusicContext";
import { StatsView } from "@/components/views/StatsView";

export default function StatsPage() {
  const { showToast } = useMusic();

  return <StatsView onShowToast={showToast} />;
}
