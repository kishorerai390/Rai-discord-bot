"use client";

import React, { useState } from "react";
import { Play, Pause, Square, SkipForward, Shuffle, Search, Bookmark, Radio, Sliders, Heart, ChevronLeft, ChevronRight, Settings, Bell } from "lucide-react";
import { formatDuration, DEFAULT_TRACK_ARTWORK } from "@/lib/utils";
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
  const [searchQuery, setSearchQuery] = useState("");
  const [recPageIndex, setRecPageIndex] = useState(0);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const query = searchQuery.trim();
    if (!query) return;
    onNavigate(`/search?q=${encodeURIComponent(query)}`);
    setSearchQuery("");
  };

  const recCardPages = [
    [
      {
        title: "Lofi Chill Beats",
        artist: "Chilled Cow • Study Session",
        image: "https://images.unsplash.com/photo-1518609878373-06d740f60d8b?w=400",
        query: "Lofi Chill Hip Hop Study Beats",
      },
      {
        title: "Synthwave Night",
        artist: "Neon Horizon • Retro 80s",
        image: "https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?w=400",
        query: "Synthwave Retro 80s Cyberpunk Night Drive",
      },
      {
        title: "Anime J-Rock Hits",
        artist: "Tokyo Sound • Shonen Anthem",
        image: "https://images.unsplash.com/photo-1578632767115-351597cf2477?w=400",
        query: "Top Anime Openings J-Rock Hits",
      },
      {
        title: "Electronic Bass",
        artist: "Noctyra Studio • High Voltage",
        image: "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=400",
        query: "Electronic High Energy Gaming Bass Boost",
      },
    ],
    [
      {
        title: "Desi Chill & Bollywood",
        artist: "Arijit Singh • Midnight Acoustic",
        image: "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=400",
        query: "Best of Bollywood Acoustic Lo-Fi Hindi Hits",
      },
      {
        title: "Cyberpunk Drift Phonk",
        artist: "KSLV • High Octane",
        image: "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400",
        query: "Aggressive Drift Phonk Bass Gaming 2026",
      },
      {
        title: "Coffeehouse Acoustic",
        artist: "Indie Warmth • Rainy Day",
        image: "https://images.unsplash.com/photo-1501386761578-eac5c94b800a?w=400",
        query: "Acoustic Fingerstyle Guitar Relaxing Coffeehouse",
      },
      {
        title: "Tamil & Telugu Vibes",
        artist: "Anirudh Ravichander • Hype Anthems",
        image: "https://images.unsplash.com/photo-1465847899084-d164df4dedc6?w=400",
        query: "Anirudh Ravichander viral soundtrack hits",
      },
    ],
  ];

  const currentRecCards = recCardPages[recPageIndex] || recCardPages[0];

  return (
    <div className="flex flex-col gap-6 w-full">
      {/* 1. TOP HEADER ROW (REFERENCE IMAGE 2) */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <form onSubmit={handleSearchSubmit} className="flex-1 max-w-xl">
          <div className="flex items-center gap-3 px-4 py-2.5 rounded-full bg-white/5 border border-white/10 focus-within:border-purple-500/60 focus-within:bg-white/8 transition-all">
            <Search className="w-4 h-4 text-white/50 shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search songs, artists, playlists, or paste audio link..."
              className="bg-transparent border-none outline-none text-sm text-white placeholder:text-white/40 w-full"
            />
            <button type="submit" className="btn btn-primary btn-sm py-1 px-3 text-xs rounded-full">
              Search
            </button>
          </div>
        </form>

        <div className="flex items-center gap-3">
          {user ? (
            <div
              onClick={() => onNavigate("/settings")}
              className="flex items-center gap-2.5 py-1 px-3 rounded-full bg-white/5 border border-white/10 hover:bg-white/10 transition-colors cursor-pointer"
              title="Settings & Profile"
            >
              <img
                src={user.avatar_url || "https://cdn.discordapp.com/embed/avatars/0.png"}
                alt="Avatar"
                className="w-7 h-7 rounded-full object-cover"
              />
              <span className="text-xs font-bold text-white truncate max-w-30">
                {user.display_name || user.username}
              </span>
            </div>
          ) : (
            <button
              onClick={() => onNavigate("/login")}
              className="btn btn-secondary btn-sm rounded-full text-xs py-1.5 px-4 font-bold"
            >
              Sign In
            </button>
          )}

          <button
            onClick={() => onNavigate("/settings")}
            className="w-9 h-9 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-colors"
            title="Settings"
          >
            <Settings className="w-4 h-4" />
          </button>
          <button
            onClick={() => onNavigate("/queue")}
            className="w-9 h-9 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-colors"
            title="Queue"
          >
            <Bell className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 2. MAIN 2-COLUMN LAYOUT (LEFT: 2.2fr, RIGHT: 1fr) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LEFT COLUMN: RECOMMENDED FOR YOU & TOP 50 TRACKS TABLE */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          {/* RECOMMENDED FOR YOU CARDS */}
          <div>
            <div className="flex items-center justify-between mb-3.5">
              <h3 className="text-xl font-black text-white tracking-tight">Recommended For You</h3>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setRecPageIndex((prev) => (prev > 0 ? prev - 1 : recCardPages.length - 1))}
                  className="w-7 h-7 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-colors"
                  title="Previous recommendations"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setRecPageIndex((prev) => (prev < recCardPages.length - 1 ? prev + 1 : 0))}
                  className="w-7 h-7 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-white/70 hover:text-white hover:bg-white/10 transition-colors"
                  title="Next recommendations"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 animate-in fade-in duration-200" key={recPageIndex}>
              {currentRecCards.map((rec, i) => (
                <div
                  key={i}
                  onClick={() => onControl("PLAY", { query: rec.query })}
                  className="group relative p-3 rounded-2xl bg-white/3 border border-white/5 hover:border-purple-500/40 hover:bg-white/6 transition-all cursor-pointer flex flex-col"
                >
                  <div className="relative aspect-square w-full rounded-xl overflow-hidden mb-2.5 shadow-md">
                    <img
                      src={rec.image}
                      alt={rec.title}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onControl("PLAY", { query: rec.query });
                      }}
                      className="absolute bottom-2 right-2 w-9 h-9 rounded-full bg-white text-black flex items-center justify-center shadow-xl opacity-0 translate-y-2 group-hover:opacity-100 group-hover:translate-y-0 hover:bg-purple-500 hover:text-white transition-all"
                      title="Play"
                    >
                      <Play className="w-4 h-4 fill-current ml-0.5" />
                    </button>
                  </div>
                  <h4 className="text-xs font-bold text-white truncate">{rec.title}</h4>
                  <p className="text-[11px] text-(--text-muted) truncate">{rec.artist}</p>
                </div>
              ))}
            </div>
          </div>

          {/* TOP 50 / QUEUE TRACKS TABLE */}
          <div className="rounded-2xl border border-white/10 bg-[#0d0b18]/80 backdrop-blur-xl p-5">
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-white/5">
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-400">Live Audio</span>
                <h3 className="text-base font-black text-white">TOP 50 / QUEUE</h3>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-(--text-muted)">{queue.length} Tracks</span>
                <button onClick={() => onNavigate("/queue")} className="btn btn-secondary btn-sm text-xs py-1 px-3">
                  Full View ↗
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              {currentTrack && (
                <div className="flex items-center justify-between p-2.5 rounded-xl bg-purple-600/15 border-l-4 border-l-purple-500 border border-purple-500/30">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="w-6 text-center text-purple-400 font-black text-sm">
                      {isPlaying ? "🔊" : "▶"}
                    </span>
                    <img
                      src={currentTrack.thumbnail || DEFAULT_TRACK_ARTWORK}
                      alt={currentTrack.title}
                      className="w-10 h-10 rounded-lg object-cover shrink-0"
                    />
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-white truncate">{currentTrack.title}</p>
                      <p className="text-[11px] text-cyan-400 font-semibold truncate">Playing Now</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0 ml-2">
                    <span className="font-mono text-xs text-(--text-muted)">
                      {formatDuration(totalDuration)}
                    </span>
                    <button
                      onClick={() => onControl("FAVORITE_TOGGLE", currentTrack)}
                      className="text-pink-400 hover:scale-110 transition-transform"
                    >
                      <Heart className="w-4 h-4 fill-current" />
                    </button>
                  </div>
                </div>
              )}

              {queue.length === 0 && !currentTrack ? (
                <div className="text-center py-12 text-(--text-muted) text-sm">
                  <div className="text-2xl mb-1">🎵</div>
                  <p className="font-bold text-white">No tracks currently in queue</p>
                  <p className="text-xs text-(--text-dim) mt-1">Search above to choose a result, or click a recommendation to start playing.</p>
                </div>
              ) : (
                queue.slice(0, 10).map((track, idx) => (
                  <div
                    key={track.id || idx}
                    className="flex items-center justify-between p-2 rounded-xl hover:bg-white/4 transition-colors"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="font-mono text-xs text-(--text-dim) w-6 text-center">
                        {(idx + 1).toString().padStart(2, "0")}
                      </span>
                      <img
                        src={track.thumbnail || DEFAULT_TRACK_ARTWORK}
                        alt={track.title}
                        className="w-9 h-9 rounded-lg object-cover shrink-0"
                      />
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-white truncate">{track.title}</p>
                        <p className="text-[11px] text-(--text-muted) truncate">{track.artist || "Unknown"}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 shrink-0 ml-2">
                      <span className="font-mono text-xs text-(--text-dim)">
                        {formatDuration(track.duration)}
                      </span>
                      <button
                        onClick={() => onControl("REMOVE", { index: idx })}
                        className="text-(--text-dim) hover:text-white text-xs px-1.5"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: LIKED SONGS & TURNTABLE DECK WITH VU METERS */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          {/* LIKED SONGS MINI CARD */}
          <div className="glass-card rounded-2xl border border-white/10 bg-[#0d0b18]/80 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-bold text-white flex items-center gap-1.5">
                <Heart className="w-4 h-4 text-pink-400" /> Liked Songs
              </span>
              <button onClick={() => onNavigate("/library")} className="text-[11px] text-purple-400 hover:underline">
                View All
              </button>
            </div>
            <p className="text-xs text-(--text-muted)">
              Quick access to your saved songs library. Click ♡ on any song to save it!
            </p>
          </div>

          {/* NOW PLAYING VINYL DECK */}
          <div className="glass-card relative overflow-hidden rounded-2xl border border-purple-500/30 bg-(--bg-card) p-5 backdrop-blur-xl flex flex-col items-center text-center">
            <div className="flex items-center justify-between w-full mb-3">
              <span className="chip-pill text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 text-[10px]">
                ● 320kbps Lossless
              </span>
              <span className="chip-pill bg-purple-500/20 text-purple-300 border border-purple-500/40 text-[10px]">
                {session?.state || "IDLE"}
              </span>
            </div>

            {/* Vinyl Disc */}
            <div className="relative group shrink-0 my-2">
              <div className="w-32 h-32 rounded-full p-2 bg-linear-to-tr from-purple-900/60 via-black to-cyan-900/60 shadow-[0_0_25px_rgba(147,51,234,0.35)] flex items-center justify-center">
                <img
                  src={currentTrack?.thumbnail || DEFAULT_TRACK_ARTWORK}
                  alt="Vinyl Art"
                  className={`w-28 h-28 rounded-full object-cover border-2 border-[#07090e] ${
                    isPlaying ? "animate-[spin_12s_linear_infinite]" : ""
                  }`}
                />
                <div className="absolute w-5 h-5 rounded-full bg-[#07090e] border border-purple-500/50" />
              </div>
            </div>

            <h4 className="text-sm font-bold text-white truncate max-w-full mt-2">
              {currentTrack ? currentTrack.title : "No Track Playing"}
            </h4>
            <p className="text-xs text-cyan-400 truncate max-w-full mb-3">
              {currentTrack ? currentTrack.artist || "Unknown Artist" : "Join a voice channel and play a song"}
            </p>

            {/* Scrubber */}
            <div className="w-full bg-white/10 rounded-full h-1.5 overflow-hidden relative mb-1.5">
              <div
                className="bg-linear-to-r from-(--primary) to-(--cyan) h-full transition-all duration-300 rounded-full"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <div className="flex justify-between w-full font-mono text-[10px] text-(--text-muted) mb-3">
              <span>{formatDuration(playbackSeconds)}</span>
              <span>{formatDuration(totalDuration)}</span>
            </div>

            {/* Playback Controls */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => onControl("PREVIOUS")}
                className="w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center text-white"
                title="Previous"
              >
                ⏮
              </button>
              <button
                onClick={() => onControl(isPlaying ? "PAUSE" : "RESUME")}
                className="btn btn-primary btn-sm py-1.5 px-4 font-bold flex items-center gap-1.5 rounded-full"
              >
                {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                <span>{isPlaying ? "Pause" : "Play"}</span>
              </button>
              <button
                onClick={() => onControl("SKIP")}
                className="w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center text-white"
                title="Skip"
              >
                <SkipForward className="w-4 h-4" />
              </button>
              <button
                onClick={() => onControl("SHUFFLE")}
                className="w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center text-white"
                title="Shuffle"
              >
                <Shuffle className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
