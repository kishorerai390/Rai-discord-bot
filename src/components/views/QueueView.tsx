"use client";

import React from "react";
import { ListMusic, Trash2, Shuffle, Bookmark, ArrowUp, ArrowDown, Search, X } from "lucide-react";
import { formatDuration, DEFAULT_TRACK_ARTWORK } from "@/lib/utils";
import type { Track } from "@/types/music";

interface QueueViewProps {
  guildId: string;
  queue: Track[];
  onControl: (action: string, payload?: any) => Promise<void>;
  onNavigate: (route: string) => void;
  onOpenPlaylistModal: () => void;
  onShowToast: (msg: string, type?: "success" | "danger" | "info") => void;
}

export function QueueView({
  guildId,
  queue,
  onControl,
  onNavigate,
  onOpenPlaylistModal,
  onShowToast,
}: QueueViewProps) {
  const totalQueueDuration = queue.reduce((acc, t) => acc + (t.duration || 0), 0);

  const handleClear = async () => {
    if (confirm("Are you sure you want to clear the entire queue?")) {
      await onControl("CLEAR");
      onShowToast("Cleared upcoming queue", "info");
    }
  };

  const handleRemove = async (position: number, title: string) => {
    await onControl("REMOVE", { index: position, position });
    onShowToast(`Removed track: ${title}`, "info");
  };

  const handleMove = async (fromIndex: number, toIndex: number, title: string) => {
    if (toIndex < 0 || toIndex >= queue.length) return;
    await onControl("MOVE", { from_index: fromIndex, to_index: toIndex });
    onShowToast(`Moved track: ${title}`, "info");
  };

  return (
    <div className="flex flex-col gap-6">
      {/* QUEUE HEADER CARD */}
      <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-6 backdrop-blur-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <ListMusic className="w-6 h-6 text-[var(--cyan)]" />
              <span>Guild Playback Queue</span>
            </h2>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              Synchronized 24/7 lossless playback. Reorder, purge, or save queue to personal playlists.
            </p>
            <div className="flex items-center gap-3 mt-3">
              <span className="chip-pill bg-purple-500/20 text-purple-300 border border-purple-500/40 text-xs">
                {queue.length} Tracks
              </span>
              <span className="chip-pill bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 text-xs">
                ⏱ {formatDuration(totalQueueDuration)} Total Time
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => onControl("SHUFFLE")}
              className="btn btn-secondary btn-sm flex items-center gap-1.5"
            >
              <Shuffle className="w-4 h-4 text-purple-400" />
              <span>Shuffle</span>
            </button>
            <button
              onClick={onOpenPlaylistModal}
              className="btn btn-secondary btn-sm flex items-center gap-1.5"
            >
              <Bookmark className="w-4 h-4 text-amber-400" />
              <span>Save Playlist</span>
            </button>
            <button
              onClick={handleClear}
              disabled={queue.length === 0}
              className="btn btn-secondary btn-sm flex items-center gap-1.5 hover:border-rose-500/40 hover:text-rose-400"
            >
              <Trash2 className="w-4 h-4 text-rose-400" />
              <span>Clear Queue</span>
            </button>
          </div>
        </div>
      </div>

      {/* QUEUE TABLE */}
      <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-6 backdrop-blur-xl">
        {queue.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-3xl">
              🎵
            </div>
            <div>
              <h3 className="text-base font-bold text-white">The queue is currently empty</h3>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                Search for songs, paste links, or let Smart Auto-DJ take the stage!
              </p>
            </div>
            <button
              onClick={() => onNavigate("/search")}
              className="btn btn-primary btn-sm flex items-center gap-2 mt-2"
            >
              <Search className="w-4 h-4" />
              <span>Find Music</span>
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs text-[var(--text-dim)] uppercase">
                  <th className="pb-3 w-12 text-center">#</th>
                  <th className="pb-3">Title & Artist</th>
                  <th className="pb-3 hidden md:table-cell">Requester</th>
                  <th className="pb-3 text-right">Duration</th>
                  <th className="pb-3 w-16 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {queue.map((track, idx) => (
                  <tr key={track.id || idx} className="hover:bg-white/5 group transition-colors">
                    <td className="py-3 text-center font-mono text-xs text-[var(--text-dim)]">
                      {idx + 1}
                    </td>
                    <td className="py-3">
                      <div className="flex items-center gap-3">
                        <img
                          src={track.thumbnail || DEFAULT_TRACK_ARTWORK}
                          alt={track.title}
                          onError={(e) => {
                            (e.target as HTMLImageElement).src = DEFAULT_TRACK_ARTWORK;
                          }}
                          className="w-11 h-11 rounded-lg object-cover shrink-0"
                        />
                        <div className="min-w-0 max-w-sm md:max-w-md">
                          <div className="flex items-center gap-2">
                            <p className="font-semibold text-white truncate text-sm" title={track.title}>
                              {track.title}
                            </p>
                            {queue.some((t, i) => i !== idx && ((t.url && t.url === track.url) || (t.title.toLowerCase() === track.title.toLowerCase() && (t.artist || "").toLowerCase() === (track.artist || "").toLowerCase()))) && (
                              <span className="chip-pill text-[10px] py-0 px-1.5 bg-amber-500/10 text-amber-300 border border-amber-500/30 shrink-0">
                                Duplicate
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-[var(--text-muted)] truncate" title={track.artist}>
                            {track.artist || "Unknown Artist"}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="py-3 hidden md:table-cell text-xs text-[var(--text-muted)]">
                      {track.requester_name || "Web Client"}
                    </td>
                    <td className="py-3 text-right font-mono text-xs text-[var(--text-dim)]">
                      {formatDuration(track.duration)}
                    </td>
                    <td className="py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleMove(idx, idx - 1, track.title)}
                          disabled={idx === 0}
                          className="p-1 rounded text-slate-400 hover:text-white disabled:opacity-20 disabled:hover:text-slate-400 transition-colors"
                          title="Move Up"
                        >
                          <ArrowUp className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleMove(idx, idx + 1, track.title)}
                          disabled={idx === queue.length - 1}
                          className="p-1 rounded text-slate-400 hover:text-white disabled:opacity-20 disabled:hover:text-slate-400 transition-colors"
                          title="Move Down"
                        >
                          <ArrowDown className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleRemove(idx, track.title)}
                          className="p-1.5 rounded-lg text-rose-400 hover:bg-rose-500/20 transition-all opacity-70 group-hover:opacity-100 ml-1"
                          title="Remove from queue"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
