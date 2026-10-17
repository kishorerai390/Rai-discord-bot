"use client";

import React from "react";
import { useMusic } from "@/context/MusicContext";
import { CanvasView } from "@/components/views/CanvasView";

export default function CanvasPage() {
  const { session, playbackSeconds } = useMusic();

  return (
    <CanvasView session={session} playbackSeconds={playbackSeconds} />
  );
}
