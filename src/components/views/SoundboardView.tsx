"use client";

import React, { useState, useEffect } from "react";
import { Volume2, Sparkles, Radio, Zap } from "lucide-react";
import type { SoundboardSound } from "@/types/settings";

interface SoundboardViewProps {
  guildId: string;
  onShowToast: (msg: string, type?: "success" | "danger" | "info") => void;
}

export function SoundboardView({ guildId, onShowToast }: SoundboardViewProps) {
  const [sounds, setSounds] = useState<SoundboardSound[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("All");
  const [cooldownRemaining, setCooldownRemaining] = useState<number>(0);
  const [activeSoundId, setActiveSoundId] = useState<string | null>(null);

  useEffect(() => {
    async function loadSounds() {
      try {
        const res = await fetch("/api/music/soundboard");
        const json = await res.json();
        if (json.success && json.data?.sounds) {
          setSounds(json.data.sounds);
        }
      } catch (e: any) {
        console.warn("Failed to load soundboard sounds:", e);
      }
    }
    loadSounds();
  }, []);

  // Cooldown countdown timer
  useEffect(() => {
    if (cooldownRemaining <= 0) return;
    const interval = setInterval(() => {
      setCooldownRemaining((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [cooldownRemaining]);

  const handleTrigger = async (sound: SoundboardSound) => {
    if (cooldownRemaining > 0) {
      onShowToast(`Soundboard cooldown: wait ${cooldownRemaining}s`, "info");
      return;
    }

    setActiveSoundId(sound.id);
    try {
      const res = await fetch("/api/music/soundboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ guild_id: guildId, sound_id: sound.id }),
      });
      const json = await res.json();
      if (json.success) {
        onShowToast(`Triggered '${sound.name}' ${sound.emoji} into voice channel!`, "success");
        setCooldownRemaining(3);
      } else if (res.status === 429) {
        const waitTime = json.error?.retry_after ? Math.ceil(json.error.retry_after) : 3;
        setCooldownRemaining(waitTime);
        onShowToast(json.error?.message || "Cooldown active", "info");
      } else {
        onShowToast(json.error?.message || json.error || "Failed to trigger sound", "danger");
      }
    } catch (e: any) {
      onShowToast(`Soundboard error: ${e.message}`, "danger");
    } finally {
      setTimeout(() => setActiveSoundId(null), 600);
    }
  };

  const categories = ["All", "Classic", "Reaction", "Comedy", "Anime", "Meme", "Gaming"];

  const filteredSounds =
    selectedCategory === "All"
      ? sounds
      : sounds.filter((s) => s.category === selectedCategory);

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto">
      {/* HEADER CARD */}
      <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-6 backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-white flex items-center gap-2">
            <Volume2 className="w-6 h-6 text-pink-400" />
            <span>Instant Voice Soundboard</span>
          </h2>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            Trigger studio SFX clips into your connected voice channel in real time. Rate-limited to 3s to prevent audio clutter.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {cooldownRemaining > 0 ? (
            <span className="chip-pill bg-amber-500/20 text-amber-300 border border-amber-500/40 text-xs font-mono">
              ⏳ Cooldown: {cooldownRemaining}s
            </span>
          ) : (
            <span className="chip-pill bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-xs">
              ⚡ Soundboard Ready
            </span>
          )}
        </div>
      </div>

      {/* CATEGORY FILTER BAR */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`chip-pill text-xs px-3.5 py-1.5 transition-all ${
              selectedCategory === cat
                ? "active border-pink-500 text-white shadow-sm shadow-pink-500/30"
                : "hover:text-white"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* SOUNDS GRID */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
        {filteredSounds.map((sound) => {
          const isActive = activeSoundId === sound.id;
          return (
            <button
              key={sound.id}
              onClick={() => handleTrigger(sound)}
              disabled={cooldownRemaining > 0}
              className={`glass-card rounded-2xl border p-4 flex flex-col items-center justify-center text-center gap-2.5 transition-all group ${
                isActive
                  ? "border-pink-400 bg-pink-500/20 scale-95 shadow-lg shadow-pink-500/30"
                  : "border-white/10 bg-white/[0.03] hover:bg-white/[0.08] hover:border-pink-500/40 hover:scale-[1.02]"
              } ${cooldownRemaining > 0 ? "opacity-60 cursor-not-allowed" : "cursor-pointer"}`}
            >
              <div className="w-14 h-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-3xl group-hover:scale-110 transition-transform">
                {sound.emoji}
              </div>
              <div>
                <div className="text-sm font-bold text-white group-hover:text-pink-300 transition-colors">
                  {sound.name}
                </div>
                <div className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider font-semibold mt-0.5">
                  {sound.category}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
