"use client";

import React, { useState } from "react";
import { Play, Pause, Square, SkipForward, Shuffle, Search, Bookmark, Radio, Sliders } from "lucide-react";
import { formatDuration } from "@/lib/utils";
import type { MusicSession, Track } from "@/types/music";
import type { DiscordUser } from "@/types/auth";

interface DashboardViewProps {
  guildId: string;
  session: MusicSession | null;
  queue: Track[];
  user: DiscordUser | null;
  playbackSeconds: number;
  onNavigate: (route: string) => void;
  onControl: (action: string, payload?: any) => Promise<void>;
  onOpenPlaylistModal: () => void;
}

export function DashboardView({
  guildId,
  session,
  queue,
  user,
  playbackSeconds,
  onNavigate,
  onControl,
  onOpenPlaylistModal,
}: DashboardViewProps) {
  const currentTrack = session?.current_track;
  const isPlaying = session?.state === "PLAYING" && !session?.is_paused;
  const totalDuration = currentTrack?.duration || 0;
  const progressPercent = totalDuration > 0 ? Math.min(100, (playbackSeconds / totalDuration) * 100) : 0;

  return (
    <div className="flex flex-col gap-6">
      {/* HERO NOW PLAYING VINYL CARD */}
      <div className="glass-card relative overflow-hidden rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-6 backdrop-blur-xl">
        <div className="flex flex-col md:flex-row items-center md:items-start gap-6">
          {/* Vinyl Disc Container */}
          <div className="relative group shrink-0">
            <div className="w-36 h-36 md:w-44 md:h-44 rounded-full p-2 bg-gradient-to-tr from-purple-900/60 via-black to-cyan-900/60 shadow-[0_0_25px_rgba(147,51,234,0.35)] flex items-center justify-center">
              <img
                src={currentTrack?.thumbnail || "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=350"}
                alt="Vinyl Art"
                className={`w-32 h-32 md:w-40 md:h-40 rounded-full object-cover border-4 border-[#07090e] ${
                  isPlaying ? "animate-[spin_12s_linear_infinite]" : ""
                }`}
              />
              {/* Spindle hole */}
              <div className="absolute w-6 h-6 rounded-full bg-[#07090e] border-2 border-purple-500/50 shadow-inner" />
            </div>
          </div>

          {/* Track Details & Controls */}
          <div className="flex flex-col gap-3 min-w-0 flex-1 text-center md:text-left">
            <div className="flex items-center justify-center md:justify-start gap-2 flex-wrap">
              <span className="chip-pill text-emerald-400 bg-emerald-500/10 border border-emerald-500/30">
                ● 320kbps Lossless Opus
              </span>
              <span className="chip-pill bg-purple-500/20 text-purple-300 border border-purple-500/40">
                {session?.state || "IDLE"}
              </span>
              <span className="chip-pill bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                🔊 {session?.voice_channel_name || "No Voice Room"}
              </span>
            </div>

            <h2 className="text-2xl md:text-3xl font-extrabold text-white leading-tight break-words">
              {currentTrack ? currentTrack.title : "Ready for Music — The Queue is Empty"}
            </h2>
            <p className="text-base text-[var(--cyan)] font-semibold">
              {currentTrack ? currentTrack.artist || "Unknown Artist" : "Use /play <song> in Discord or search songs below"}
            </p>

            {/* Scrubber Slider */}
            <div className="flex flex-col gap-1.5 w-full max-w-xl mt-2">
              <div className="w-full bg-white/10 rounded-full h-2 overflow-hidden relative">
                <div
                  className="bg-gradient-to-r from-[var(--primary)] to-[var(--cyan)] h-full transition-all duration-300 rounded-full"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <div className="flex justify-between font-mono text-xs text-[var(--text-muted)]">
                <span>{formatDuration(playbackSeconds)}</span>
                <span>{formatDuration(totalDuration)}</span>
              </div>
            </div>

            {/* Quick Actions Cluster */}
            <div className="flex items-center justify-center md:justify-start gap-2.5 flex-wrap mt-2">
              <button
                onClick={() => onControl(isPlaying ? "PAUSE" : "RESUME")}
                className="btn btn-primary btn-sm flex items-center gap-1.5"
              >
                {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                <span>{isPlaying ? "Pause" : "Play"}</span>
              </button>

              <button
                onClick={() => onControl("STOP")}
                className="btn btn-secondary btn-sm flex items-center gap-1.5"
              >
                <Square className="w-4 h-4 text-rose-400" />
                <span>Stop</span>
              </button>

              <button
                onClick={() => onControl("SKIP")}
                className="btn btn-secondary btn-sm flex items-center gap-1.5"
              >
                <SkipForward className="w-4 h-4 text-cyan-400" />
                <span>Skip</span>
              </button>

              <button
                onClick={() => onControl("SHUFFLE")}
                className="btn btn-secondary btn-sm flex items-center gap-1.5"
              >
                <Shuffle className="w-4 h-4 text-purple-400" />
                <span>Shuffle</span>
              </button>

              <button
                onClick={() => onNavigate("/search")}
                className="btn btn-secondary btn-sm flex items-center gap-1.5"
              >
                <Search className="w-4 h-4 text-cyan-400" />
                <span>Add Song</span>
              </button>

              <button
                onClick={onOpenPlaylistModal}
                className="btn btn-secondary btn-sm flex items-center gap-1.5"
              >
                <Bookmark className="w-4 h-4 text-amber-400" />
                <span>Save Playlist</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* METRICS & QUEUE PREVIEW ROW */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* QUEUE PREVIEW CARD */}
        <div className="lg:col-span-2 glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-5 backdrop-blur-xl">
          <div className="section-header flex items-center justify-between pb-3 mb-3 border-b border-white/5">
            <span className="section-title text-base font-bold text-white flex items-center gap-2">
              <span>📜</span> Upcoming Queue ({queue.length})
            </span>
            <button
              onClick={() => onNavigate("/queue")}
              className="btn btn-secondary btn-sm text-xs py-1 px-3"
            >
              Full Queue ↗
            </button>
          </div>

          <div className="space-y-2">
            {queue.length === 0 ? (
              <div className="text-center py-10 text-[var(--text-muted)] text-sm">
                🐾 The upcoming queue is currently empty.
                <br />
                <span className="text-xs text-[var(--text-dim)]">Search for songs or enable Smart Auto-DJ!</span>
              </div>
            ) : (
              queue.slice(0, 5).map((track, idx) => (
                <div
                  key={track.id || idx}
                  className="flex items-center justify-between p-2.5 rounded-xl hover:bg-white/5 border border-white/5 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-mono text-xs text-[var(--text-dim)] w-4 text-right">
                      {idx + 1}
                    </span>
                    <img
                      src={track.thumbnail || "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=120"}
                      alt={track.title}
                      className="w-10 h-10 rounded-lg object-cover shrink-0"
                    />
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-white truncate">{track.title}</p>
                      <p className="text-xs text-[var(--text-muted)] truncate">{track.artist || "Unknown"}</p>
                    </div>
                  </div>
                  <span className="font-mono text-xs text-[var(--text-dim)] shrink-0 ml-2">
                    {formatDuration(track.duration)}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* SMART AUTO-DJ & EQUALIZER QUICK WIDGETS */}
        <div className="flex flex-col gap-6">
          {/* Smart Auto-DJ */}
          <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-5 backdrop-blur-xl">
            <div className="flex items-center justify-between mb-2">
              <span className="text-base font-bold text-white flex items-center gap-2">
                <Radio className="w-5 h-5 text-purple-400" /> Smart Auto-DJ
              </span>
              <button
                onClick={() => onControl("AUTODJ_TOGGLE")}
                className={`btn btn-sm text-xs py-1 px-2.5 font-bold ${
                  session?.auto_dj ? "btn-primary" : "btn-secondary"
                }`}
              >
                {session?.auto_dj ? "ACTIVE ✅" : "ENABLE"}
              </button>
            </div>
            <p className="text-xs text-[var(--text-muted)] leading-relaxed">
              Continuous non-stop playback. When queue is empty, MusicMaid intelligently selects tracks matching your mood.
            </p>
            <div className="flex gap-2 flex-wrap mt-3">
              {(["balanced", "energetic", "chill"] as const).map((mood) => (
                <button
                  key={mood}
                  onClick={() => onControl("AUTODJ_MOOD", { mood })}
                  className={`chip-pill capitalize text-xs cursor-pointer ${
                    session?.dj_mood === mood ? "active border-[var(--primary)] text-white" : ""
                  }`}
                >
                  {mood}
                </button>
              ))}
            </div>
          </div>

          {/* Equalizer Presets Card */}
          <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-5 backdrop-blur-xl">
            <div className="flex items-center justify-between mb-3">
              <span className="text-base font-bold text-white flex items-center gap-2">
                <Sliders className="w-5 h-5 text-cyan-400" /> DSP Audio Preset
              </span>
              <span className="chip-pill active text-xs font-semibold">
                {session?.eq_preset || "Flat"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 mt-2">
              {[
                { id: "bassboost", label: "🔥 Bass Boost" },
                { id: "nightcore", label: "⚡ Nightcore" },
                { id: "8d", label: "🎧 8D Spatial" },
                { id: "flat", label: "🎵 Flat Pure" },
              ].map((eq) => (
                <button
                  key={eq.id}
                  onClick={() => onControl("FILTER", { preset: eq.id, name: eq.label })}
                  className="text-xs p-2 rounded-xl bg-white/5 hover:bg-purple-600/20 hover:border-purple-500/40 border border-white/5 text-left font-medium text-white transition-all"
                >
                  {eq.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
