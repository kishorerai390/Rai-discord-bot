"use client";

import React, { useState } from "react";
import { Bookmark, X, Loader2 } from "lucide-react";
import type { Track } from "@/types/music";

interface PlaylistModalProps {
  isOpen: boolean;
  onClose: () => void;
  guildId: string;
  queue: Track[];
  onShowToast: (msg: string, type?: "success" | "danger" | "info") => void;
}

export function PlaylistModal({
  isOpen,
  onClose,
  guildId,
  queue,
  onShowToast,
}: PlaylistModalProps) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  if (!isOpen) return null;

  const handleSave = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      onShowToast("Please enter a playlist name", "danger");
      return;
    }
    if (queue.length === 0) {
      onShowToast("Queue is empty — nothing to save!", "info");
      return;
    }

    setSaving(true);
    try {
      const res = await fetch("/api/music/playlists/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: trimmed,
          guild_id: guildId,
          tracks: queue,
        }),
      });
      const data = await res.json();
      if (data.success) {
        onShowToast(`Saved playlist "${trimmed}" with ${queue.length} songs! 💾`, "success");
        setName("");
        onClose();
      } else {
        onShowToast(data.error || "Failed to save playlist", "danger");
      }
    } catch (e: any) {
      onShowToast(`Error: ${e.message}`, "danger");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in">
      <div className="glass-card relative w-full max-w-md rounded-2xl border border-(--card-border) bg-(--bg-surface) p-6 shadow-2xl">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-(--text-muted) hover:text-white transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400">
            <Bookmark className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Save Current Queue</h3>
            <p className="text-xs text-(--text-muted)">Snapshot {queue.length} tracks to server library</p>
          </div>
        </div>

        <p className="text-xs text-(--text-muted) my-4 leading-relaxed">
          Enter a memorable name for this playlist. Anyone with access to this guild can reload it anytime.
        </p>

        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
          placeholder="e.g. Midnight Chill Vibes 2026"
          className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-(--text-dim) focus:outline-none focus:border-(--primary) mb-5"
          autoFocus
        />

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="btn btn-secondary btn-sm text-xs">
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="btn btn-primary btn-sm text-xs flex items-center gap-2"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bookmark className="w-4 h-4" />}
            <span>Save Playlist</span>
          </button>
        </div>
      </div>
    </div>
  );
}
