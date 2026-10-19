"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Play,
  Pause,
  SkipForward,
  SkipBack,
  Shuffle,
  Repeat,
  Volume2,
  VolumeX,
  ListMusic,
  Heart,
  Maximize2,
  Moon,
} from "lucide-react";
import { formatDuration, DEFAULT_TRACK_ARTWORK } from "@/lib/utils";
import { MusicSession } from "@/types/music";

interface PlayerBarProps {
  session: MusicSession | null;
  onDispatchControl: (action: string, payload?: any) => Promise<void>;
}

export function PlayerBar({ session, onDispatchControl }: PlayerBarProps) {
  const [volume, setVolume] = useState<number>(session?.volume ?? 80);
  const [isMuted, setIsMuted] = useState(false);
  const [isFavorited, setIsFavorited] = useState(false);
  const [localSeconds, setLocalSeconds] = useState(session?.elapsed_seconds ?? 0);
  const [isBusy, setIsBusy] = useState(false);

  const isPlaying = session?.is_playing && !session?.is_paused;
  const track = session?.current_track;
  const duration = session?.duration_seconds || track?.duration || 0;

  const handleSafeControl = async (action: string, payload?: any) => {
    if (isBusy) return;
    setIsBusy(true);
    try {
      await onDispatchControl(action, payload);
    } finally {
      setTimeout(() => setIsBusy(false), 350);
    }
  };

  // Local tick timer while playing
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(() => {
      setLocalSeconds((prev) => (duration > 0 && prev < duration ? prev + 1 : prev));
    }, 1000);
    return () => clearInterval(interval);
  }, [isPlaying, duration]);

  // Sync with incoming session updates
  useEffect(() => {
    if (session) {
      setLocalSeconds(session.elapsed_seconds || 0);
      setVolume(session.volume ?? 80);
    }
  }, [session?.elapsed_seconds, session?.volume]);

  const handleVolumeChange = (newVol: number) => {
    setVolume(newVol);
    setIsMuted(false);
    onDispatchControl("VOLUME", { volume: newVol });
  };

  const handleToggleMute = () => {
    if (isMuted) {
      setIsMuted(false);
      onDispatchControl("VOLUME", { volume: volume || 80 });
    } else {
      setIsMuted(true);
      onDispatchControl("VOLUME", { volume: 0 });
    }
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  };

  const progressPercent = duration > 0 ? Math.min(100, (localSeconds / duration) * 100) : 0;
  const voiceName = session?.voice_channel_name;
  const queueCount = session?.queue_length ?? 0;

  return (
    <footer className="fixed bottom-0 left-0 right-0 min-h-[var(--player-height)] bg-[#0b0914]/95 border-t border-purple-500/25 backdrop-blur-2xl px-4 py-2.5 z-50 shadow-[-12px_0_40px_rgba(0,0,0,0.85)]">
      <div className="max-w-6xl mx-auto flex flex-col gap-1.5">
        {/* TIER 1: TRACK METADATA & FAVORITE HEART */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <img
              src={track?.thumbnail || DEFAULT_TRACK_ARTWORK}
              alt={track?.title || "No track"}
              onError={(e) => {
                (e.target as HTMLImageElement).src = DEFAULT_TRACK_ARTWORK;
              }}
              className="w-11 h-11 rounded-lg object-cover bg-purple-950/50 border border-purple-500/35 shrink-0 shadow-md"
            />
            <div className="truncate min-w-0">
              <Link
                href="/queue"
                className="text-sm font-bold text-white hover:text-purple-300 truncate block transition-colors tracking-tight"
              >
                {track?.title || "No Track Playing"}
              </Link>
              <p className="text-xs text-purple-200/80 truncate">
                {track?.author || track?.artist || "MusicMaid"} · {voiceName ? `#${voiceName}` : "Current server"}
              </p>
              <p className="text-[11px] text-slate-400 truncate hidden sm:block">
                {track ? (session?.is_paused ? "Paused · Press play to resume" : "Lossless Audio · 320kbps Studio Output") : "Idle state: Search for music to get started"}
              </p>
            </div>
          </div>

          <button
            onClick={() => setIsFavorited(!isFavorited)}
            className={`p-2 rounded-full transition-transform hover:scale-110 ${
              isFavorited ? "text-pink-500" : "text-slate-400 hover:text-pink-400"
            }`}
            title="Save to Favorites"
          >
            <Heart className={`w-5 h-5 ${isFavorited ? "fill-pink-500" : ""}`} />
          </button>
        </div>

        <div className="h-[1px] bg-white/[0.06] w-full" />

        {/* TIER 2: CENTERED PLAYBACK CONTROLS */}
        <div className="flex items-center justify-center gap-5">
          <button
            onClick={() => handleSafeControl("SHUFFLE")}
            disabled={isBusy}
            className={`p-1.5 rounded-full transition-all active:scale-90 ${
              session?.shuffle ? "text-purple-400 bg-purple-500/15" : "text-slate-400 hover:text-white"
            } disabled:opacity-50`}
            title="Toggle Shuffle"
          >
            <Shuffle className="w-4 h-4" />
          </button>

          <button
            onClick={() => handleSafeControl("PREVIOUS")}
            disabled={isBusy}
            className="text-slate-300 hover:text-white p-1 rounded-full hover:bg-white/5 active:scale-90 transition-all disabled:opacity-50"
            title="Previous Track"
          >
            <SkipBack className="w-4 h-4" />
          </button>

          <button
            onClick={() => handleSafeControl(isPlaying ? "PAUSE" : "RESUME")}
            disabled={isBusy}
            className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-purple-700 text-white flex items-center justify-center shadow-lg shadow-purple-500/40 hover:scale-105 active:scale-95 transition-all disabled:opacity-70"
            title={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? (
              <Pause className="w-4 h-4 fill-white" />
            ) : (
              <Play className="w-4 h-4 fill-white ml-0.5" />
            )}
          </button>

          <button
            onClick={() => handleSafeControl("SKIP")}
            disabled={isBusy}
            className="text-slate-300 hover:text-white p-1 rounded-full hover:bg-white/5 active:scale-90 transition-all disabled:opacity-50"
            title="Skip Track"
          >
            <SkipForward className="w-4 h-4" />
          </button>

          <button
            onClick={() => handleSafeControl("LOOP")}
            disabled={isBusy}
            className={`p-1.5 rounded-full transition-all active:scale-90 ${
              session?.loop_mode && session.loop_mode !== "off"
                ? "text-purple-400 bg-purple-500/15"
                : "text-slate-400 hover:text-white"
            } disabled:opacity-50`}
            title={`Loop Mode: ${session?.loop_mode || "off"}`}
          >
            <Repeat className="w-4 h-4" />
          </button>
        </div>

        {/* TIER 3: FULL-WIDTH SCRUBBER */}
        <div className="w-full flex items-center gap-2">
          <span className="text-[10px] text-slate-400 font-mono w-9 text-right">
            {formatDuration(localSeconds)}
          </span>
          <div
            className="relative flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden cursor-pointer group"
            onClick={(e) => {
              if (duration <= 0) return;
              const rect = e.currentTarget.getBoundingClientRect();
              const clickPercent = (e.clientX - rect.left) / rect.width;
              const targetSeconds = Math.floor(clickPercent * duration);
              setLocalSeconds(targetSeconds);
              onDispatchControl("SEEK", { seconds: targetSeconds });
            }}
          >
            <div
              className="h-full bg-gradient-to-r from-purple-500 to-cyan-400 rounded-full transition-all duration-150"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className="text-[10px] text-slate-400 font-mono w-9">
            {formatDuration(duration)}
          </span>
        </div>

        {/* TIER 4: STATUS & UTILITIES */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-3">
            <Link
              href="/queue"
              className="text-slate-400 hover:text-white font-medium transition-colors"
            >
              Queue: {queueCount} {queueCount === 1 ? "track" : "tracks"}
            </Link>
            <button
              onClick={() => onDispatchControl("247_TOGGLE")}
              className={`px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wider transition-all border ${
                session?.twenty_four_seven
                  ? "bg-purple-600/25 border-purple-500 text-purple-300"
                  : "bg-white/5 border-white/10 text-slate-400 hover:text-white"
              }`}
              title="Toggle 24/7 Voice Channel Mode"
            >
              {session?.twenty_four_seven ? "24/7 ON" : "24/7 OFF"}
            </button>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/queue"
              className="p-1 text-slate-400 hover:text-purple-300 transition-colors"
              title="Open Queue Drawer"
            >
              <ListMusic className="w-4 h-4" />
            </Link>

            <div className="hidden sm:flex items-center gap-1.5">
              <button
                onClick={handleToggleMute}
                className="text-slate-400 hover:text-white p-1"
              >
                {isMuted || volume === 0 ? (
                  <VolumeX className="w-4 h-4 text-rose-400" />
                ) : (
                  <Volume2 className="w-4 h-4" />
                )}
              </button>
              <input
                type="range"
                min="0"
                max="150"
                value={isMuted ? 0 : volume}
                onChange={(e) => handleVolumeChange(Number(e.target.value))}
                className="w-16 h-1 bg-white/20 rounded-lg appearance-none cursor-pointer accent-purple-500"
                title={`Volume: ${volume}%`}
              />
            </div>

            <button
              onClick={toggleFullscreen}
              className="p-1 text-slate-400 hover:text-white transition-colors"
              title="Toggle Fullscreen"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </footer>
  );
}
