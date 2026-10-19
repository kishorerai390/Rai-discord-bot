"use client";

import React, { useState } from "react";
import { Search, Plus, Music2, Check, Loader2, Play, SkipForward } from "lucide-react";
import { formatDuration, DEFAULT_TRACK_ARTWORK } from "@/lib/utils";

interface SearchViewProps {
  guildId: string;
  onEnqueue: (query: string) => Promise<boolean>;
  onControl?: (action: string, payload?: any) => Promise<void>;
  onShowToast: (msg: string, type?: "success" | "danger" | "info") => void;
}

interface SearchResultItem {
  id?: string;
  title: string;
  artist: string;
  url: string;
  duration: number;
  duration_fmt?: string;
  thumbnail?: string;
  provider?: string;
  source?: string;
}

const POPULAR_SUGGESTIONS = [
  { label: "🎵 Anirudh", query: "Anirudh Ravichander hits" },
  { label: "✨ A.R. Rahman", query: "A.R. Rahman Tamil classics" },
  { label: "⚡ Yuvan", query: "Yuvan Shankar Raja vibes" },
  { label: "🎻 Arijit Singh", query: "Arijit Singh Hindi melodies" },
  { label: "☕ Lo-Fi Chill", query: "Lofi Hip Hop Chill Beats" },
  { label: "🕹️ Synthwave", query: "Synthwave Gaming 2026" },
];

export function SearchView({ guildId, onEnqueue, onControl, onShowToast }: SearchViewProps) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [enqueuedMap, setEnqueuedMap] = useState<Record<string, boolean>>({});

  const handleSearch = async (overrideQuery?: string) => {
    const q = (overrideQuery ?? query).trim();
    if (!q) return;

    setLoading(true);
    try {
      const res = await fetch(`/api/music/search?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      if (data.success && Array.isArray(data.data)) {
        setResults(data.data);
      } else {
        setResults([]);
        onShowToast("No tracks found", "info");
      }
    } catch (e: any) {
      onShowToast(`Search error: ${e.message}`, "danger");
    } finally {
      setLoading(false);
    }
  };

  const handleAddTrack = async (item: SearchResultItem) => {
    const itemKey = item.url || item.title;
    setEnqueuedMap((prev) => ({ ...prev, [itemKey]: true }));
    const ok = await onEnqueue(item.url || `${item.title} ${item.artist}`);
    if (ok) {
      onShowToast(`Enqueued: ${item.title} 🎵`, "success");
    } else {
      onShowToast(`Failed to enqueue track`, "danger");
      setEnqueuedMap((prev) => ({ ...prev, [itemKey]: false }));
    }
  };

  const handlePlayNow = async (item: SearchResultItem) => {
    if (onControl) {
      await onControl("PLAY_NOW", { query: item.url || `${item.title} ${item.artist}`, title: item.title, artist: item.artist });
      onShowToast(`Streaming now: ${item.title} ⚡`, "success");
    } else {
      await handleAddTrack(item);
    }
  };

  const handlePlayNext = async (item: SearchResultItem) => {
    if (onControl) {
      await onControl("PLAY_NEXT", { query: item.url || `${item.title} ${item.artist}`, title: item.title, artist: item.artist });
      onShowToast(`Queued next: ${item.title} ⏭`, "info");
    } else {
      await handleAddTrack(item);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* SEARCH HEADER CARD */}
      <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6 backdrop-blur-xl">
        <div className="flex items-center gap-2 mb-2">
          <Search className="w-6 h-6 text-(--cyan)" />
          <h2 className="text-xl font-bold text-white">Search & Discover Music</h2>
        </div>
        <p className="text-sm text-(--text-muted) mb-5">
          High-speed YouTube & Spotify search with Tamil, Hindi, Telugu, and English multi-lingual recognition.
        </p>

        {/* INPUT BOX */}
        <div className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-2 focus-within:border-(--primary) focus-within:ring-2 focus-within:ring-(--primary-glow) transition-all">
          <Search className="w-5 h-5 text-(--cyan) ml-2 shrink-0" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Type song name, artist, YouTube URL, or Spotify link..."
            className="w-full bg-transparent text-white placeholder-(--text-dim) text-sm focus:outline-none"
          />
          <button
            onClick={() => handleSearch()}
            disabled={loading}
            className="btn btn-primary btn-sm shrink-0 flex items-center gap-1.5"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            <span>Search</span>
          </button>
        </div>

        {/* QUICK SUGGESTIONS */}
        <div className="flex items-center gap-2 flex-wrap mt-4">
          <span className="text-xs font-bold text-(--text-dim) uppercase">Popular:</span>
          {POPULAR_SUGGESTIONS.map((sug) => (
            <button
              key={sug.label}
              onClick={() => {
                setQuery(sug.query);
                handleSearch(sug.query);
              }}
              className="chip-pill text-xs hover:border-(--cyan) hover:text-white cursor-pointer transition-colors"
            >
              {sug.label}
            </button>
          ))}
        </div>
      </div>

      {/* RESULTS GRID */}
      <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6 backdrop-blur-xl">
        <div className="flex items-center justify-between pb-3 mb-5 border-b border-white/5">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Music2 className="w-5 h-5 text-purple-400" />
            <span>Search Results</span>
          </h3>
          <span className="text-xs text-(--text-muted)">
            {loading ? "Searching engine..." : results.length > 0 ? `Found ${results.length} matches` : "Ready to search"}
          </span>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-16 text-(--cyan) gap-3">
            <Loader2 className="w-8 h-8 animate-spin" />
            <p className="text-sm font-semibold">Resolving audio tracks from engine...</p>
          </div>
        ) : results.length === 0 ? (
          <div className="text-center py-16 text-(--text-muted) text-sm">
            Type a song or click any suggestion tag above to resolve tracks.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {results.map((item, idx) => {
              const itemKey = item.url || item.title;
              const stableKey = item.id || `search_res_${idx}_${itemKey}`;
              const isEnqueued = Boolean(enqueuedMap[itemKey]);

              return (
                <div
                  key={stableKey}
                  className="flex items-center justify-between gap-3 p-3 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 transition-all group"
                >
                  <img
                    src={item.thumbnail || DEFAULT_TRACK_ARTWORK}
                    alt={item.title}
                    onError={(e) => {
                      (e.target as HTMLImageElement).src = DEFAULT_TRACK_ARTWORK;
                    }}
                    className="w-14 h-14 rounded-lg object-cover shrink-0"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-white truncate" title={item.title}>
                      {item.title}
                    </p>
                    <p className="text-xs text-(--text-muted) truncate" title={item.artist}>
                      {item.artist}
                    </p>
                    <span className="text-[10px] font-mono text-(--text-dim)">
                      {item.duration_fmt || formatDuration(item.duration)}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      onClick={() => handlePlayNow(item)}
                      className="p-2 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 transition-all"
                      title="Play Immediately"
                    >
                      <Play className="w-3.5 h-3.5 fill-cyan-300" />
                    </button>
                    <button
                      onClick={() => handlePlayNext(item)}
                      className="p-2 rounded-xl bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/30 transition-all"
                      title="Play Next in Queue"
                    >
                      <SkipForward className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleAddTrack(item)}
                      disabled={isEnqueued}
                      className={`p-2 rounded-xl transition-all ${
                        isEnqueued
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : "bg-(--primary) hover:bg-(--primary-hover) text-white shadow-md shadow-purple-900/40"
                      }`}
                      title="Add to queue"
                    >
                      {isEnqueued ? <Check className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
