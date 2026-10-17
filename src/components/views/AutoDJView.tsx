"use client";

import React from "react";
import { Radio, Zap, Coffee, PartyPopper, Check, Plus } from "lucide-react";
import type { MusicSession } from "@/types/music";

interface AutoDJViewProps {
  guildId: string;
  session: MusicSession | null;
  onControl: (action: string, payload?: any) => Promise<void>;
  onEnqueue: (query: string) => Promise<boolean>;
  onShowToast: (msg: string, type?: "success" | "danger" | "info") => void;
}

const MOODS = [
  {
    id: "balanced",
    title: "Balanced Flow",
    icon: Radio,
    color: "from-purple-500/20 to-indigo-500/20 border-purple-500/30",
    desc: "Harmonious blend of trending hits, familiar favorites, and diverse genres.",
  },
  {
    id: "energetic",
    title: "High Energy",
    icon: Zap,
    color: "from-amber-500/20 to-rose-500/20 border-amber-500/30",
    desc: "Upbeat EDM, hip-hop, workout anthems, and fast BPM power tracks.",
  },
  {
    id: "chill",
    title: "Lo-Fi & Acoustic",
    icon: Coffee,
    color: "from-cyan-500/20 to-blue-500/20 border-cyan-500/30",
    desc: "Mellow vibes, ambient soundscapes, coffee shop lo-fi, and acoustic guitars.",
  },
  {
    id: "party",
    title: "Party & Club",
    icon: PartyPopper,
    color: "from-pink-500/20 to-purple-500/20 border-pink-500/30",
    desc: "Club remixes, bass-heavy dance floor hits, and festival bangers.",
  },
];

const CURATED_SEEDS = [
  { title: "Vaathi Coming", artist: "Anirudh Ravichander", mood: "energetic" },
  { title: "Arabic Kuthu", artist: "Anirudh Ravichander", mood: "party" },
  { title: "Kesariya", artist: "Arijit Singh", mood: "balanced" },
  { title: "Sunflower", artist: "Post Malone & Swae Lee", mood: "chill" },
  { title: "Starboy", artist: "The Weeknd", mood: "energetic" },
  { title: "Night Changes", artist: "One Direction", mood: "chill" },
];

export function AutoDJView({
  guildId,
  session,
  onControl,
  onEnqueue,
  onShowToast,
}: AutoDJViewProps) {
  const isEnabled = Boolean(session?.auto_dj);
  const activeMood = session?.dj_mood || "balanced";

  const handleToggle = async () => {
    await onControl("AUTODJ_TOGGLE");
    onShowToast(`Smart Auto-DJ ${!isEnabled ? "enabled" : "disabled"}`, "info");
  };

  const handleSetMood = async (mood: string) => {
    await onControl("AUTODJ_MOOD", { mood });
    onShowToast(`Auto-DJ mood set to ${mood.toUpperCase()} ✨`, "success");
  };

  const handleAddSeed = async (item: { title: string; artist: string }) => {
    const ok = await onEnqueue(`${item.title} ${item.artist}`);
    if (ok) {
      onShowToast(`Enqueued ${item.title} into Auto-DJ queue 🎵`, "success");
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* HEADER CARD */}
      <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-6 backdrop-blur-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400">
                <Radio className="w-6 h-6" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">Smart Auto-DJ Engine</h2>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">
                  AI-assisted non-stop music streaming. Automatically resolves seamless tracks when the queue ends.
                </p>
              </div>
            </div>
          </div>

          <button
            onClick={handleToggle}
            className={`btn btn-sm text-sm px-5 py-2 font-bold ${
              isEnabled ? "btn-primary shadow-lg shadow-purple-900/50" : "btn-secondary"
            }`}
          >
            {isEnabled ? "AUTO-DJ ACTIVE ✅" : "ENABLE AUTO-DJ"}
          </button>
        </div>
      </div>

      {/* MOOD SELECTION GRID */}
      <div>
        <h3 className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Select Active Vibe & Mood
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {MOODS.map((m) => {
            const Icon = m.icon;
            const isSelected = activeMood === m.id;

            return (
              <div
                key={m.id}
                onClick={() => handleSetMood(m.id)}
                className={`cursor-pointer rounded-2xl p-5 border bg-gradient-to-br transition-all flex flex-col justify-between ${
                  m.color
                } ${
                  isSelected
                    ? "ring-2 ring-[var(--cyan)] shadow-lg shadow-cyan-900/30 scale-[1.02]"
                    : "hover:border-white/20 opacity-80 hover:opacity-100"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <Icon className="w-6 h-6 text-white" />
                    {isSelected && (
                      <span className="flex items-center gap-1 text-[11px] font-bold text-[var(--cyan)] bg-cyan-900/40 px-2 py-0.5 rounded-full border border-cyan-500/40">
                        <Check className="w-3 h-3" /> Selected
                      </span>
                    )}
                  </div>
                  <h4 className="text-base font-bold text-white mb-1">{m.title}</h4>
                  <p className="text-xs text-[var(--text-muted)] leading-relaxed">{m.desc}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* CURATED SEEDS & INSPIRATIONS */}
      <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-6 backdrop-blur-xl">
        <h3 className="text-base font-bold text-white mb-1">Recommended Vibe Starters</h3>
        <p className="text-xs text-[var(--text-muted)] mb-4">
          Click any seed track to kick off the Auto-DJ recommendation generator:
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {CURATED_SEEDS.map((s, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5 hover:bg-white/10 transition-colors"
            >
              <div className="min-w-0">
                <p className="text-sm font-semibold text-white truncate">{s.title}</p>
                <p className="text-xs text-[var(--text-muted)] truncate">{s.artist}</p>
              </div>
              <button
                onClick={() => handleAddSeed(s)}
                className="p-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/40 text-purple-300 border border-purple-500/30 transition-all shrink-0 ml-2"
                title="Add to queue"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
