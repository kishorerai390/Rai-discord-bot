"use client";

import React, { useState } from "react";
import { Sliders, Volume2, RotateCcw } from "lucide-react";
import type { MusicSession } from "@/types/music";

interface AudioViewProps {
  guildId: string;
  session: MusicSession | null;
  onControl: (action: string, payload?: any) => Promise<void>;
  onShowToast: (msg: string, type?: "success" | "danger" | "info") => void;
}

const DSP_PRESETS = [
  {
    id: "bassboost",
    name: "Bass Boost",
    badge: "🔥 +12dB Sub",
    desc: "Heavy low-end subwoofer enhancement engineered for hip-hop, phonk, and EDM.",
  },
  {
    id: "nightcore",
    name: "Nightcore",
    badge: "⚡ 1.25x Pitch",
    desc: "Sped-up tempo, elevated vocal pitch, high-energy anime aesthetic.",
  },
  {
    id: "8d",
    name: "8D Spatial",
    badge: "🎧 360° Rotating",
    desc: "Continuous binaural pan rotation for immersive headphone listening.",
  },
  {
    id: "vaporwave",
    name: "Slowed + Reverb",
    badge: "🌊 0.85x Depth",
    desc: "Nostalgic pitch-shifted slow tempo with expansive atmospheric hall reverberation.",
  },
  {
    id: "vocal",
    name: "Vocal Clarity",
    badge: "🎙️ Mid Boost",
    desc: "Attenuates mud while brightening dialogue and singing frequencies.",
  },
  {
    id: "flat",
    name: "Flat Studio",
    badge: "🎵 0dB Pure",
    desc: "Lossless uncolored reference response for authentic studio reproduction.",
  },
];

const BANDS = [
  { freq: "32Hz", defaultGain: 0 },
  { freq: "64Hz", defaultGain: 2 },
  { freq: "125Hz", defaultGain: 3 },
  { freq: "250Hz", defaultGain: 0 },
  { freq: "500Hz", defaultGain: -1 },
  { freq: "1kHz", defaultGain: 0 },
  { freq: "2kHz", defaultGain: 1 },
  { freq: "4kHz", defaultGain: 2 },
  { freq: "8kHz", defaultGain: 3 },
  { freq: "16kHz", defaultGain: 2 },
];

export function AudioView({
  guildId,
  session,
  onControl,
  onShowToast,
}: AudioViewProps) {
  const [bandGains, setBandGains] = useState<number[]>(BANDS.map((b) => b.defaultGain));
  const activePreset = session?.eq_preset || "Flat";

  const handleApplyPreset = async (preset: { id: string; name: string }) => {
    await onControl("FILTER", { preset: preset.id, name: preset.name });
    onShowToast(`Activated preset: ${preset.name} 🎛️`, "success");
  };

  const handleBandChange = (idx: number, val: number) => {
    const updated = [...bandGains];
    updated[idx] = val;
    setBandGains(updated);
  };

  const handleResetEQ = async () => {
    setBandGains(BANDS.map(() => 0));
    await onControl("FILTER", { preset: "flat", name: "Flat Studio" });
    onShowToast("Reset equalizer to Flat Studio", "info");
  };

  return (
    <div className="flex flex-col gap-6">
      {/* HEADER CARD */}
      <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-6 backdrop-blur-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400">
              <Sliders className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">Digital Signal Processor (DSP)</h2>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                Real-time FFmpeg audio filter matrix and 10-band master studio equalizer.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="chip-pill active text-xs font-semibold">
              Preset: {activePreset}
            </span>
            <button
              onClick={handleResetEQ}
              className="btn btn-secondary btn-sm flex items-center gap-1.5"
            >
              <RotateCcw className="w-4 h-4" />
              <span>Reset EQ</span>
            </button>
          </div>
        </div>
      </div>

      {/* DSP PRESET CARDS */}
      <div>
        <h3 className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Hardware Audio Filter Presets
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {DSP_PRESETS.map((p) => {
            const isSelected = activePreset.toLowerCase().includes(p.id.toLowerCase());

            return (
              <div
                key={p.id}
                onClick={() => handleApplyPreset(p)}
                className={`cursor-pointer rounded-2xl p-5 border bg-white/5 backdrop-blur-xl transition-all flex flex-col justify-between ${
                  isSelected
                    ? "border-[var(--primary)] ring-2 ring-[var(--primary-glow)] bg-purple-900/10 shadow-lg shadow-purple-900/30"
                    : "border-white/5 hover:border-white/20 hover:bg-white/10"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-bold text-white text-base">{p.name}</h4>
                    <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-white/10 text-[var(--cyan)] border border-cyan-500/30">
                      {p.badge}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--text-muted)] leading-relaxed">{p.desc}</p>
                </div>
                <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between text-xs font-semibold text-[var(--cyan)]">
                  <span>{isSelected ? "Active Filter" : "Click to activate"}</span>
                  <span>→</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 10-BAND GRAPHIC EQUALIZER */}
      <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-6 backdrop-blur-xl">
        <div className="flex items-center justify-between mb-6 pb-3 border-b border-white/5">
          <div className="flex items-center gap-2">
            <Volume2 className="w-5 h-5 text-[var(--cyan)]" />
            <h3 className="font-bold text-white text-base">10-Band Precision Parametric Slider Rack</h3>
          </div>
          <span className="text-xs text-[var(--text-muted)]">Gain: -12dB to +12dB</span>
        </div>

        <div className="grid grid-cols-5 md:grid-cols-10 gap-3">
          {BANDS.map((band, idx) => (
            <div key={band.freq} className="flex flex-col items-center gap-3">
              <span className="text-xs font-mono text-cyan-300 font-semibold">
                {bandGains[idx] > 0 ? `+${bandGains[idx]}` : bandGains[idx]}dB
              </span>

              <div className="h-44 flex items-center justify-center">
                <input
                  type="range"
                  min="-12"
                  max="12"
                  value={bandGains[idx]}
                  onChange={(e) => handleBandChange(idx, Number(e.target.value))}
                  className="slider-track -rotate-90 w-36 h-2 cursor-pointer"
                />
              </div>

              <span className="text-xs font-mono text-[var(--text-muted)] font-medium">
                {band.freq}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
