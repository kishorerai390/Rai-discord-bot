"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useMusic } from "@/context/MusicContext";
import { Radio, ArrowRight, ShieldCheck, CheckCircle2, Headphones } from "lucide-react";

export default function ServersPage() {
  const router = useRouter();
  const { guilds, activeGuildId, setActiveGuildId, showToast } = useMusic();

  const handleSelect = (guildId: string, guildName: string) => {
    setActiveGuildId(guildId);
    showToast(`Switched active session to: ${guildName}`, "success");
    router.push("/dashboard");
  };

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto w-full py-6">
      <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-6 backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-white flex items-center gap-2.5">
            <Radio className="w-6 h-6 text-purple-400" />
            <span>Select Active Discord Server</span>
          </h2>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            Pick which server voice channel to listen to, control live queues for, or manage 24/7 settings.
          </p>
        </div>
        <button
          onClick={() => router.push("/dashboard")}
          className="btn btn-secondary btn-sm flex items-center gap-1.5 self-start md:self-auto"
        >
          <Headphones className="w-4 h-4 text-cyan-400" />
          <span>Back to Dashboard</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {guilds.map((g) => {
          const isSelected = g.id === activeGuildId;

          return (
            <div
              key={g.id}
              onClick={() => handleSelect(g.id, g.name)}
              className={`cursor-pointer rounded-2xl p-5 border transition-all flex items-center justify-between group ${
                isSelected
                  ? "bg-purple-900/20 border-purple-500 ring-2 ring-purple-500/30 shadow-lg shadow-purple-900/20"
                  : "bg-white/[0.03] border-white/10 hover:border-purple-500/40 hover:bg-white/[0.06]"
              }`}
            >
              <div className="flex items-center gap-3.5 min-w-0">
                <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center text-lg font-black text-white shrink-0 shadow-md">
                  {g.icon ? (
                    <img src={g.icon} alt={g.name} className="w-full h-full rounded-2xl object-cover" />
                  ) : (
                    g.name.slice(0, 2).toUpperCase()
                  )}
                </div>
                <div className="min-w-0">
                  <h4 className="text-sm font-bold text-white truncate group-hover:text-purple-300 transition-colors">
                    {g.name}
                  </h4>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] text-[var(--text-dim)] font-mono">ID: {g.id}</span>
                    {isSelected && (
                      <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/25">
                        <CheckCircle2 className="w-3 h-3" /> Active Now
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <div className="shrink-0 ml-3">
                <div
                  className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${
                    isSelected
                      ? "bg-purple-600 text-white"
                      : "bg-white/5 text-white/50 group-hover:bg-purple-600 group-hover:text-white"
                  }`}
                >
                  <ArrowRight className="w-4 h-4" />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
