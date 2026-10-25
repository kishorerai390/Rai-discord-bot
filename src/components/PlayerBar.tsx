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
  MessageSquare,
  Sparkles,
  Radio,
} from "lucide-react";
import { formatDuration, DEFAULT_TRACK_ARTWORK } from "@/lib/utils";
import { MusicSession } from "@/types/music";

interface PlayerBarProps {
  session: MusicSession | null;
  onDispatchControl: (action: string, payload?: any) => Promise<void>;
  onToggleFavorite?: () => void;
}

export function PlayerBar({ session, onDispatchControl, onToggleFavorite }: PlayerBarProps) {
  const [volume, setVolume] = useState<number>(session?.volume ?? 80);
  const [isMuted, setIsMuted] = useState(false);
  const [isFavorited, setIsFavorited] = useState(false);
  const [localSeconds, setLocalSeconds] = useState(session?.elapsed_seconds ?? 0);
  const [isBusy, setIsBusy] = useState(false);
  const [showDiscordPreview, setShowDiscordPreview] = useState(false);

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
    <footer className="fixed bottom-0 left-0 right-0 min-h-(--player-height) bg-[#0b0914]/95 border-t border-purple-500/25 backdrop-blur-2xl px-4 py-2.5 z-50 shadow-[-12px_0_40px_rgba(0,0,0,0.85)]">
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
                {track?.author || track?.artist || "Rem 🎧💜"} · {voiceName ? `#${voiceName}` : "Current server"}
              </p>
              <p className="text-[11px] text-slate-400 truncate hidden sm:block">
                {track ? (session?.is_paused ? "Paused · Press play to resume" : "Lossless Audio · 320kbps Studio Output") : "Idle state: Search for music to get started"}
              </p>
            </div>
          </div>

          <button
            onClick={() => {
              setIsFavorited(!isFavorited);
              onToggleFavorite?.();
            }}
            className={`p-2 rounded-full transition-transform hover:scale-110 ${
              isFavorited ? "text-pink-500" : "text-slate-400 hover:text-pink-400"
            }`}
            title="Save to Favorites"
          >
            <Heart className={`w-5 h-5 ${isFavorited ? "fill-pink-500" : ""}`} />
          </button>
        </div>

        <div className="h-px bg-white/6 w-full" />

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
            className="w-10 h-10 rounded-full bg-linear-to-br from-purple-500 to-purple-700 text-white flex items-center justify-center shadow-lg shadow-purple-500/40 hover:scale-105 active:scale-95 transition-all disabled:opacity-70"
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
              className="h-full bg-linear-to-r from-purple-500 to-cyan-400 rounded-full transition-all duration-150"
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
              onClick={() => setShowDiscordPreview(true)}
              className="p-1 text-slate-400 hover:text-[#5865f2] transition-colors"
              title="Preview Discord Embed Card"
            >
              <MessageSquare className="w-3.5 h-3.5" />
            </button>

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

      {/* DISCORD NOW PLAYING INTERACTIVE EMBED MODAL */}
      {showDiscordPreview && (
        <div className="fixed inset-0 z-100 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
          <div
            className="fixed inset-0"
            onClick={() => setShowDiscordPreview(false)}
          />
          <div className="relative z-10 w-full max-w-lg bg-[#313338] text-[#dbdee1] rounded-2xl shadow-2xl border border-white/5 p-5 font-sans overflow-hidden">
            {/* Discord Message Header */}
            <div className="flex items-start justify-between gap-3 mb-4">
              <div className="flex items-center gap-3">
                <div className="relative">
                  <div className="w-10 h-10 rounded-full bg-linear-to-tr from-pink-500 to-purple-600 flex items-center justify-center text-white font-bold text-sm shadow-md overflow-hidden">
                    🌸
                  </div>
                  <span className="absolute bottom-0 right-0 w-3 h-3 rounded-full bg-[#23a55a] border-2 border-[#313338]" />
                </div>
                <div>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-bold text-white text-sm hover:underline cursor-pointer">
                      Zynrax
                    </span>
                    <span className="bg-[#5865f2] text-white text-[10px] font-bold px-1 rounded-sm uppercase tracking-wider flex items-center gap-0.5">
                      ✓ APP
                    </span>
                    <span className="text-[11px] text-[#949ba4] ml-1">
                      Today at 04:15 PM
                    </span>
                  </div>
                  <p className="text-xs text-[#949ba4] font-mono">
                    ?PLAY {track?.title || "ENNA SONA"}
                  </p>
                </div>
              </div>

              <button
                onClick={() => setShowDiscordPreview(false)}
                className="text-[#949ba4] hover:text-white p-1 rounded-lg hover:bg-white/5 transition-colors text-xs font-bold"
              >
                ✕ ESC
              </button>
            </div>

            {/* Discord Embed Container */}
            <div className="rounded-lg bg-[#2b2d31] border-l-4 border-l-[#f47b67] p-4 flex flex-col gap-3 shadow-md">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <span className="text-[#00a8fc] font-bold text-sm underline cursor-pointer hover:brightness-110 block mb-2">
                    Now Playing
                  </span>

                  <h3 className="text-[#00a8fc] font-bold text-sm underline cursor-pointer hover:brightness-110 leading-snug">
                    {track?.title || "Enna Sona (From \"OK Jaanu\")"} - {track?.artist || "A.R. Rahman"}
                  </h3>

                  <div className="flex items-center gap-1.5 text-xs text-[#dbdee1] mt-2">
                    <span className="font-bold text-[#b5bac1]">Duration:</span>
                    <span className="bg-[#1e1f22] text-[#f2f3f5] font-mono px-1.5 py-0.5 rounded text-[11px]">
                      {duration > 0 ? `${Math.floor(duration / 60)}m ${duration % 60}s` : "3m 34s"}
                    </span>
                  </div>

                  <div className="text-xs text-[#b5bac1] mt-1.5 flex items-center gap-1">
                    <span>Requested by (</span>
                    <span className="bg-[#5865f2]/20 text-[#c9cdfb] px-1 py-0.5 rounded font-semibold text-[11px]">
                      @TheRealThor
                    </span>
                    <span>)</span>
                  </div>
                </div>

                <img
                  src={track?.thumbnail || DEFAULT_TRACK_ARTWORK}
                  alt="Track Art"
                  onError={(e) => {
                    (e.target as HTMLImageElement).src = DEFAULT_TRACK_ARTWORK;
                  }}
                  className="w-20 h-20 rounded-md object-cover bg-[#1e1f22] shrink-0 border border-white/5 shadow-md"
                />
              </div>

              {/* Discord Interactive Button Matrix (Row 1) */}
              <div className="grid grid-cols-5 gap-2 mt-2">
                <button
                  onClick={() => handleSafeControl("PREVIOUS")}
                  className="h-8 rounded bg-[#4e5058] hover:bg-[#6d6f78] active:bg-[#474950] text-[#f2f3f5] flex items-center justify-center text-xs font-bold transition-colors"
                  title="Previous"
                >
                  ⏮
                </button>
                <button
                  onClick={() => handleSafeControl(isPlaying ? "PAUSE" : "RESUME")}
                  className="h-8 rounded bg-[#4e5058] hover:bg-[#6d6f78] active:bg-[#474950] text-[#f2f3f5] flex items-center justify-center text-xs font-bold transition-colors"
                  title={isPlaying ? "Pause" : "Play"}
                >
                  {isPlaying ? "⏸" : "▶"}
                </button>
                <button
                  onClick={() => handleSafeControl("SKIP")}
                  className="h-8 rounded bg-[#4e5058] hover:bg-[#6d6f78] active:bg-[#474950] text-[#f2f3f5] flex items-center justify-center text-xs font-bold transition-colors"
                  title="Skip"
                >
                  ⏭
                </button>
                <button
                  onClick={handleToggleMute}
                  className="h-8 rounded bg-[#4e5058] hover:bg-[#6d6f78] active:bg-[#474950] text-[#f2f3f5] flex items-center justify-center text-xs font-bold transition-colors"
                  title="Volume Toggle"
                >
                  🔊
                </button>
                <button
                  onClick={() => handleSafeControl("STOP")}
                  className="h-8 rounded bg-[#da373c] hover:bg-[#a1282c] active:bg-[#852024] text-white flex items-center justify-center text-xs font-bold transition-colors shadow-sm"
                  title="Stop"
                >
                  ■
                </button>
              </div>

              {/* Discord Interactive Button Matrix (Row 2) */}
              <div className="grid grid-cols-3 gap-2">
                <button
                  onClick={() => handleSafeControl("LOOP")}
                  className={`h-8 rounded flex items-center justify-center gap-1.5 text-xs font-bold transition-colors ${
                    session?.loop_mode && session.loop_mode !== "off"
                      ? "bg-[#5865f2] text-white"
                      : "bg-[#4e5058] hover:bg-[#6d6f78] text-[#f2f3f5]"
                  }`}
                  title="Loop Mode"
                >
                  <span>∞</span> Loop
                </button>
                <button
                  onClick={() => handleSafeControl("SHUFFLE")}
                  className={`h-8 rounded flex items-center justify-center gap-1.5 text-xs font-bold transition-colors ${
                    session?.shuffle
                      ? "bg-[#5865f2] text-white"
                      : "bg-[#4e5058] hover:bg-[#6d6f78] text-[#f2f3f5]"
                  }`}
                  title="Shuffle Queue"
                >
                  <span>🔀</span> Shuffle
                </button>
                <button
                  onClick={() => onDispatchControl("AUTODJ_TOGGLE")}
                  className="h-8 rounded bg-[#4e5058] hover:bg-[#6d6f78] text-[#f2f3f5] flex items-center justify-center gap-1.5 text-xs font-bold transition-colors"
                  title="Toggle Auto-DJ Autoplay"
                >
                  <span>🔄</span> Autoplay
                </button>
              </div>
            </div>

            <p className="text-[10px] text-[#949ba4] mt-3 text-right">
              (edited) • Realtime Discord Gateway Sync
            </p>
          </div>
        </div>
      )}
    </footer>
  );
}
