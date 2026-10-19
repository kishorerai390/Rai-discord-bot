"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { LogIn, Headphones, Crown, Sparkles, Shield, Disc3, Radio, Plus, MessageCircle, ExternalLink, Activity, BookOpen } from "lucide-react";
import type { DiscordUser } from "@/types/auth";

interface LoginViewProps {
  currentUser: DiscordUser | null;
  onNavigate: (route: string) => void;
}

export function LoginView({ currentUser, onNavigate }: LoginViewProps) {
  const isAuth = Boolean(currentUser);
  const isOwner = Boolean(currentUser && currentUser.is_owner);
  const [gatewayPing, setGatewayPing] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/music/stats")
      .then((res) => res.json())
      .then((json) => {
        if (json?.data?.gateway_latency_ms != null) {
          setGatewayPing(json.data.gateway_latency_ms);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto w-full py-4 px-2">
      {/* 3-TIER WORKSPACE SWITCHER BAR */}
      <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-white/[0.04] border border-[var(--border-subtle)] backdrop-blur-xl flex-wrap">
        <Link
          href="/login"
          className="flex items-center gap-2 py-2 px-4 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-purple-600/40 to-cyan-500/20 border border-purple-500/50 shadow-md shadow-purple-600/20 transition-all"
        >
          <span>🔑</span>
          <span>1. Login & Welcome</span>
        </Link>
        <Link
          href="/dashboard"
          className="flex items-center gap-2 py-2 px-4 rounded-xl text-xs font-bold text-[var(--text-muted)] hover:text-white hover:bg-white/5 border border-transparent transition-all"
        >
          <span>🎧</span>
          <span>2. User Dashboard (Turntable & Deck)</span>
        </Link>
        <Link
          href="/owner"
          className="flex items-center gap-2 py-2 px-4 rounded-xl text-xs font-bold text-amber-400/80 hover:text-amber-300 hover:bg-amber-500/10 border border-transparent transition-all ml-auto"
        >
          <span>👑</span>
          <span>3. Owner Dashboard (Creator Room)</span>
        </Link>
      </div>

      {/* MODERN SPLIT-SCREEN LOGIN CARD (REFERENCE IMAGE 1) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 rounded-3xl border border-purple-500/25 bg-[#0c0a14]/90 backdrop-blur-2xl overflow-hidden shadow-2xl shadow-purple-950/40 min-h-[580px]">
        {/* LEFT PANE: BRAND, GREETING, CTAs, AND FOOTER */}
        <div className="lg:col-span-7 p-6 sm:p-10 flex flex-col justify-between z-10 bg-gradient-to-br from-[#100d1c]/95 to-[#090710]/98">
          <div>
            {/* BRAND HEADER CHIP */}
            <div className="flex items-center gap-2.5 mb-5">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-purple-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-purple-600/30 text-white font-black text-sm">
                🎧
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="text-sm font-black text-white tracking-wide">MusicMaid</span>
                <span className="text-[10px] font-bold text-purple-400 uppercase tracking-wider">Lossless</span>
              </div>
            </div>

            {/* STATUS BADGES */}
            <div className="flex items-center gap-2 mb-4 flex-wrap">
              <span className="chip-pill text-emerald-400 bg-emerald-500/15 border border-emerald-500/30 text-xs">
                ● 24/7 Voice Ready
              </span>
              <span className="chip-pill text-cyan-300 bg-cyan-500/15 border border-cyan-500/30 text-xs">
                {gatewayPing !== null ? `⚡ ${gatewayPing}ms Gateway Ping` : "⚡ Realtime Gateway Sync"}
              </span>
            </div>

            {/* HEADING & SUBTITLE */}
            <h1 className="text-4xl sm:text-5xl font-black text-white tracking-tight leading-tight mb-2">
              Hello there.
            </h1>
            <div className="text-xs sm:text-sm text-[var(--text-muted)] leading-relaxed mb-6">
              <span className="font-bold text-white">Welcome to MusicMaid Studio</span>
              <br />
              Dedicated 24/7 Lossless 320kbps Discord audio streaming with cyber-analog controls and social Aux sharing.
            </div>

            {/* ACTION CONTROLS */}
            {isAuth ? (
              <div className="flex flex-col gap-3 w-full max-w-md">
                <div className="w-full flex items-center gap-3 p-3.5 rounded-2xl bg-white/[0.04] border border-white/10 text-left">
                  <img
                    src={currentUser?.avatar_url || "https://cdn.discordapp.com/embed/avatars/0.png"}
                    alt="Avatar"
                    className="w-11 h-11 rounded-full object-cover border border-purple-500/40"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-bold text-white truncate">
                      Signed in as {currentUser?.display_name || currentUser?.username}
                    </div>
                    <div className="text-xs font-semibold text-cyan-400">
                      {isOwner ? "👑 Bot Creator / Owner" : "🎧 Listener / Server Member"}
                    </div>
                  </div>
                </div>

                <div className="flex flex-col gap-2.5 w-full">
                  <Link
                    href="/dashboard"
                    className="btn btn-primary py-3.5 px-6 font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-purple-600/30"
                  >
                    <Headphones className="w-4 h-4" />
                    <span>Enter User Dashboard ↗</span>
                  </Link>
                  <div className="flex items-center gap-2 w-full">
                    <Link
                      href="/servers"
                      className="btn btn-secondary flex-1 py-2.5 px-4 text-xs font-bold flex items-center justify-center gap-1.5"
                    >
                      <span>🌐 Select Server</span>
                    </Link>
                    {isOwner && (
                      <Link
                        href="/owner"
                        className="btn btn-secondary flex-1 py-2.5 px-4 text-xs font-bold text-amber-400 border-amber-500/40 hover:bg-amber-500/10 flex items-center justify-center gap-1.5"
                      >
                        <Crown className="w-3.5 h-3.5" />
                        <span>Owner Room</span>
                      </Link>
                    )}
                    <a
                      href="/api/auth/logout"
                      className="btn btn-secondary py-2.5 px-3 text-xs text-[var(--text-muted)] hover:text-white"
                    >
                      Logout
                    </a>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-3 w-full max-w-sm">
                <a
                  href="/api/auth/login"
                  className="w-full flex items-center justify-center gap-2.5 py-3.5 px-6 rounded-2xl font-black text-base text-white bg-gradient-to-r from-[#5865F2] to-[#4752C4] hover:opacity-95 shadow-xl shadow-[#5865F2]/30 transition-all hover:scale-[1.01] active:scale-[0.99]"
                >
                  <LogIn className="w-5 h-5" />
                  <span>Sign in with Discord</span>
                </a>
                <Link
                  href="/dashboard"
                  className="btn btn-secondary w-full py-3 px-4 text-xs font-bold flex items-center justify-center gap-2 rounded-2xl bg-white/[0.05] border border-white/10 hover:border-purple-500/30 text-white"
                >
                  <Headphones className="w-4 h-4 text-cyan-400" />
                  <span>Preview User Dashboard as Listener</span>
                </Link>
              </div>
            )}

            {/* QUICK PILLS */}
            <div className="flex items-center gap-2 mt-5 flex-wrap">
              <a
                href="https://discord.com/oauth2/authorize?client_id=1418299882950623253&permissions=3165184&scope=bot%20applications.commands"
                target="_blank"
                rel="noopener noreferrer"
                className="chip-pill text-xs font-bold text-white bg-[#5865F2]/20 border border-[#5865F2]/40 hover:bg-[#5865F2]/30 transition-colors inline-flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5 text-indigo-400" />
                <span>Add to Discord</span>
              </a>
              <a
                href="https://discord.gg/d7T8cJK3XF"
                target="_blank"
                rel="noopener noreferrer"
                className="chip-pill text-xs font-bold text-[var(--text-muted)] bg-white/5 border border-white/10 hover:text-white transition-colors inline-flex items-center gap-1.5"
              >
                <MessageCircle className="w-3.5 h-3.5 text-cyan-400" />
                <span>Join Community</span>
              </a>
              <Link
                href="/terms"
                className="chip-pill text-xs font-bold text-[var(--text-muted)] bg-white/5 border border-white/10 hover:text-white transition-colors inline-flex items-center gap-1.5"
              >
                <BookOpen className="w-3.5 h-3.5 text-purple-400" />
                <span>Documentation</span>
              </Link>
            </div>
          </div>

          {/* LEGAL & COMPLIANCE FOOTER */}
          <div className="mt-8 pt-4 border-t border-white/10 flex flex-wrap items-center justify-between gap-3 text-[11px] text-[var(--text-muted)]">
            <div>© 2026 MusicMaid. All Rights Reserved.</div>
            <div className="flex items-center gap-2">
              <Link href="/terms" className="hover:text-purple-300 transition-colors">Terms</Link>
              <span>•</span>
              <Link href="/privacy" className="hover:text-purple-300 transition-colors">Privacy</Link>
              <span>•</span>
              <Link href="/refund" className="hover:text-purple-300 transition-colors">Refund</Link>
              <span>•</span>
              <Link href="/contact" className="hover:text-purple-300 transition-colors">Contact</Link>
            </div>
          </div>
        </div>

        {/* RIGHT PANE: ATMOSPHERIC HEADPHONE VISUAL & FLOATING BADGE (REFERENCE IMAGE 1) */}
        <div className="lg:col-span-5 relative bg-black min-h-[300px] lg:min-h-full overflow-hidden flex items-center justify-center">
          <img
            src="/musicmaid_headphone_hero.jpg"
            alt="MusicMaid Lossless Audio Experience"
            className="w-full h-full object-cover object-center scale-[1.01] hover:scale-105 transition-transform duration-700 ease-out"
          />

          {/* FLOATING TOP-RIGHT BADGE */}
          <div
            className="absolute top-5 right-5 w-12 h-12 rounded-2xl bg-white/95 shadow-2xl shadow-black flex items-center justify-center z-10 text-[#0b0914]"
            title="MusicMaid Lossless Audio Engine"
          >
            <Headphones className="w-6 h-6 stroke-[2.2]" />
          </div>

          {/* BOTTOM GRADIENT OVERLAY */}
          <div className="absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-[#07060d]/90 to-transparent pointer-events-none" />

          {/* BOTTOM-LEFT LOSSLESS CHIP */}
          <div className="absolute bottom-5 left-5 flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/70 border border-white/15 backdrop-blur-md text-[11px] font-bold text-white">
            <span className="w-2 h-2 rounded-full bg-purple-500 shadow-[0_0_8px_#a855f7]" />
            <span>320kbps Lossless Opus</span>
          </div>
        </div>
      </div>

      {/* 3-CARD FEATURE SHOWCASE */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Link
          href="/dashboard"
          className="glass-card p-6 rounded-2xl border border-white/5 hover:border-purple-500/40 bg-white/[0.02] hover:bg-white/[0.04] transition-all group cursor-pointer"
        >
          <div className="w-12 h-12 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 text-2xl mb-4 group-hover:scale-110 transition-transform">
            🎛️
          </div>
          <h3 className="text-base font-bold text-white mb-2 group-hover:text-purple-300 transition-colors">
            Cyber-Analog Turntable
          </h3>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            Dual stereo analog VU meters with dB scales, metallic tonearm tracking, spinning vinyl micro-grooves, and 10-band DSP filters.
          </p>
        </Link>

        <Link
          href="/search"
          className="glass-card p-6 rounded-2xl border border-white/5 hover:border-cyan-500/40 bg-white/[0.02] hover:bg-white/[0.04] transition-all group cursor-pointer"
        >
          <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 text-2xl mb-4 group-hover:scale-110 transition-transform">
            🎵
          </div>
          <h3 className="text-base font-bold text-white mb-2 group-hover:text-cyan-300 transition-colors">
            Multi-Source Aux & Playlists
          </h3>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            Search songs across YouTube, Spotify, and SoundCloud. Pass the aux cord to server friends and save persistent favorites.
          </p>
        </Link>

        <Link
          href="/owner"
          className="glass-card p-6 rounded-2xl border border-white/5 hover:border-amber-500/40 bg-white/[0.02] hover:bg-white/[0.04] transition-all group cursor-pointer"
        >
          <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 text-2xl mb-4 group-hover:scale-110 transition-transform">
            🛡️
          </div>
          <h3 className="text-base font-bold text-white mb-2 group-hover:text-amber-300 transition-colors">
            Creator Operations Room
          </h3>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            Self-healing extractor watchdog, VIP entitlement manager, hot SQLite WAL database backups, and emergency safe mode killswitch.
          </p>
        </Link>
      </div>
    </div>
  );
}
