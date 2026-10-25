"use client";

import React from "react";
import Link from "next/link";
import { Menu, Sparkles } from "lucide-react";

interface TopBarProps {
  onToggleMobile: () => void;
  voiceStatusText?: string;
}

export function TopBar({
  onToggleMobile,
  voiceStatusText = "320kbps Lossless Online",
}: TopBarProps) {
  return (
    <header className="md:hidden flex items-center justify-between px-4 py-3 bg-(--bg-sidebar) border-b border-(--border-subtle) backdrop-blur-xl sticky top-0 z-40">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleMobile}
          className="p-1.5 rounded-lg bg-white/5 border border-white/10 text-white hover:bg-white/10"
        >
          <Menu className="w-5 h-5" />
        </button>
        <span className="font-extrabold text-sm text-white tracking-tight">MusicMaid</span>
      </div>

      <div className="flex items-center gap-2">
        <Link
          href="/premium"
          className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-linear-to-r from-pink-500 to-purple-600 text-white text-xs font-bold shadow-md shadow-pink-500/20"
        >
          <Sparkles className="w-3 h-3" />
          <span>💎 Premium</span>
        </Link>
        <span className="text-[11px] font-semibold text-emerald-400 hidden sm:inline">
          {voiceStatusText}
        </span>
      </div>
    </header>
  );
}
