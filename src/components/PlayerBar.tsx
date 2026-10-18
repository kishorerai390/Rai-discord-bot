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
  Radio,
  ListMusic,
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
  const [localSeconds, setLocalSeconds] = useState(session?.elapsed_seconds ?? 0);

  const isPlaying = session?.is_playing && !session?.is_paused;
  const track = session?.current_track;
  const duration = session?.duration_seconds || track?.duration || 0;

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

  const progressPercent = duration > 0 ? Math.min(100, (localSeconds / duration) * 100) : 0;

  return (
    <footer className="fixed bottom-0 left-0 right-0 h-[var(--player-height)] bg-[var(--player-bg)] border-t border-[var(--border-subtle)] backdrop-blur-2xl px-4 flex items-center justify-between z-50">
      {/* LEFT: TRACK METADATA */}
      <div className="flex items-center gap-3 w-1/4 min-w-[180px]">
        <img
          src={track?.thumbnail || DEFAULT_TRACK_ARTWORK}
          alt={track?.title || "No track"}
          onError={(e) => {
            (e.target as HTMLImageElement).src = DEFAULT_TRACK_ARTWORK;
          }}
          className="w-12 h-12 rounded-lg object-cover bg-purple-950/50 border border-white/10 shrink-0 shadow"
        />
        <div className="truncate">
          <Link
            href="/queue"
            className="text-xs font-bold text-white hover:text-cyan-400 truncate block transition-colors"
          >
            {track?.title || "Ready for Music"}
          </Link>
          <p className="text-[11px] text-[var(--text-dim)] truncate">
            {track?.author || "Use /play in Discord or search below"}
          </p>
        </div>
      </div>

      {/* CENTER: PLAYBACK CONTROLS & TIMELINE */}
      <div className="flex flex-col items-center gap-1.5 w-2/4 max-w-xl">
        <div className="flex items-center gap-4">
          <button
            onClick={() => onDispatchControl("SHUFFLE")}
            className={`p-1.5 rounded-lg transition-colors ${
              session?.shuffle
                ? "text-cyan-400 bg-cyan-500/15"
                : "text-slate-400 hover:text-white"
            }`}
            title="Toggle Shuffle"
          >
            <Shuffle className="w-4 h-4" />
          </button>

          <button
            onClick={() => onDispatchControl("PREVIOUS")}
            className="text-slate-300 hover:text-white p-1 rounded-lg hover:bg-white/5 transition-colors"
            title="Previous Track"
          >
            <SkipBack className="w-4 h-4" />
          </button>

          <button
            onClick={() => onDispatchControl(isPlaying ? "PAUSE" : "RESUME")}
            className="w-9 h-9 rounded-full bg-gradient-to-r from-purple-500 to-cyan-400 text-white flex items-center justify-center shadow-lg shadow-purple-500/30 hover:scale-105 active:scale-95 transition-all"
            title={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? (
              <Pause className="w-4 h-4 fill-white" />
            ) : (
              <Play className="w-4 h-4 fill-white ml-0.5" />
            )}
          </button>

          <button
            onClick={() => onDispatchControl("SKIP")}
            className="text-slate-300 hover:text-white p-1 rounded-lg hover:bg-white/5 transition-colors"
            title="Skip Track"
          >
            <SkipForward className="w-4 h-4" />
          </button>

          <button
            onClick={() => onDispatchControl("LOOP")}
            className={`p-1.5 rounded-lg transition-colors ${
              session?.loop_mode && session.loop_mode !== "off"
                ? "text-purple-400 bg-purple-500/15"
                : "text-slate-400 hover:text-white"
            }`}
            title={`Loop Mode: ${session?.loop_mode || "off"}`}
          >
            <Repeat className="w-4 h-4" />
          </button>
        </div>

        {/* PROGRESS BAR & TIMESTAMPS */}
        <div className="w-full flex items-center gap-2">
          <span className="text-[10px] text-[var(--text-dim)] font-mono w-9 text-right">
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
          <span className="text-[10px] text-[var(--text-dim)] font-mono w-9">
            {formatDuration(duration)}
          </span>
        </div>
      </div>

      {/* RIGHT: 24/7 PILL, VOLUME & SHORTCUTS */}
      <div className="flex items-center justify-end gap-3 w-1/4">
        {/* 24/7 STAYING TOGGLE */}
        <button
          onClick={() => onDispatchControl("247_TOGGLE")}
          className={`px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-wider transition-all border ${
            session?.twenty_four_seven
              ? "bg-purple-600/25 border-purple-500 text-purple-300 shadow-sm shadow-purple-500/30"
              : "bg-white/5 border-white/10 text-slate-400 hover:text-white"
          }`}
          title="Toggle 24/7 Voice Channel Staying Mode"
        >
          {session?.twenty_four_seven ? "24/7 ON" : "24/7 OFF"}
        </button>

        {/* VOLUME CONTROL (0-150%) */}
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
            className="w-16 h-1 bg-white/20 rounded-lg appearance-none cursor-pointer accent-cyan-400"
            title={`Volume: ${volume}% (100% standard, up to 150% with Premium)`}
          />
        </div>

        {/* STAGE VISUALIZER SHORTCUT */}
        <Link
          href="/canvas"
          className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-white/5 transition-colors"
          title="Open Stage Visualizer"
        >
          <Radio className="w-4 h-4" />
        </Link>

        {/* QUEUE DRAWER SHORTCUT */}
        <Link
          href="/queue"
          className="p-1.5 rounded-lg text-slate-400 hover:text-purple-400 hover:bg-white/5 transition-colors"
          title="Open Queue"
        >
          <ListMusic className="w-4 h-4" />
        </Link>
      </div>
    </footer>
  );
}
