"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { LogIn, Headphones, Crown, Sparkles, Shield, Disc3, Radio, Plus, MessageCircle, ExternalLink, Activity } from "lucide-react";
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

      {/* HERO WELCOME CARD */}
      <div className="glass-card relative overflow-hidden rounded-3xl border border-purple-500/30 bg-gradient-to-b from-purple-900/25 via-[#0b0d14] to-[#07090e] p-8 md:p-12 text-center backdrop-blur-2xl shadow-2xl shadow-purple-950/40">
        <div className="relative z-10 flex flex-col items-center">
          {/* AVATAR GLOW */}
          <div className="relative w-24 h-24 mb-6">
            <div className="w-full h-full rounded-full border-2 border-purple-500 p-1 bg-gradient-to-tr from-purple-600 to-cyan-400 shadow-[0_0_35px_rgba(147,51,234,0.5)] flex items-center justify-center text-4xl">
              🎵
            </div>
            <span className="absolute bottom-1 right-1 w-4 h-4 rounded-full bg-emerald-400 border-2 border-black animate-pulse" />
          </div>

          {/* CHIP PILLS */}
          <div className="flex items-center justify-center gap-2 mb-4 flex-wrap">
            <span className="chip-pill text-emerald-400 bg-emerald-500/15 border border-emerald-500/30">
              ● 24/7 Voice Ready
            </span>
            <span className="chip-pill text-cyan-300 bg-cyan-500/15 border border-cyan-500/30">
              {gatewayPing !== null ? `⚡ ${gatewayPing}ms Gateway Ping` : "⚡ Realtime Gateway Sync"}
            </span>
            <span className="chip-pill text-pink-400 bg-pink-500/15 border border-pink-500/30">
              🛡️ Extractor Auto-Heal ON
            </span>
          </div>

          <h1 className="text-3xl md:text-5xl font-black text-white tracking-tight leading-tight mb-4 max-w-2xl">
            Welcome to MusicMaid Studio
          </h1>
          <p className="text-sm md:text-base text-[var(--text-muted)] max-w-2xl leading-relaxed mb-8">
            Lossless 320kbps Discord audio streaming with cyber-analog turntable controls, dual stereo VU meters, social aux sharing, and autonomous self-healing.
          </p>

          {isAuth ? (
            <div className="flex flex-col items-center gap-4 w-full max-w-md">
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

              <div className="flex items-center justify-center gap-3 w-full flex-wrap">
                <Link
                  href="/dashboard"
                  className="btn btn-primary flex-1 py-3 px-6 font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-purple-600/30"
                >
                  <Headphones className="w-4 h-4" />
                  <span>Enter User Dashboard ↗</span>
                </Link>
                {isOwner && (
                  <Link
                    href="/owner"
                    className="btn btn-secondary py-3 px-5 font-bold text-sm text-amber-400 border-amber-500/40 hover:bg-amber-500/10 flex items-center justify-center gap-2"
                  >
                    <Crown className="w-4 h-4" />
                    <span>Owner Room</span>
                  </Link>
                )}
                <a
                  href="/api/auth/logout"
                  className="btn btn-secondary py-3 px-4 text-xs text-[var(--text-muted)] hover:text-white"
                >
                  Logout
                </a>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3.5 w-full max-w-sm">
              <a
                href="/api/auth/login"
                className="w-full flex items-center justify-center gap-2.5 py-3.5 px-6 rounded-2xl font-black text-base text-white bg-gradient-to-r from-[#5865F2] to-[#4752C4] hover:opacity-95 shadow-xl shadow-[#5865F2]/30 transition-all hover:scale-[1.02] active:scale-[0.98]"
              >
                <LogIn className="w-5 h-5" />
                <span>Sign in with Discord</span>
              </a>
              <div className="flex items-center gap-2.5 w-full">
                <Link
                  href="/dashboard"
                  className="btn btn-secondary flex-1 py-2.5 px-4 text-xs font-bold flex items-center justify-center gap-2"
                >
                  <Headphones className="w-4 h-4 text-cyan-400" />
                  <span>Preview as Listener</span>
                </Link>
                <a
                  href="https://discord.com/oauth2/authorize?client_id=1418299882950623253&permissions=3165184&scope=bot%20applications.commands"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-secondary py-2.5 px-4 text-xs font-bold flex items-center justify-center gap-1.5"
                >
                  <Plus className="w-4 h-4 text-emerald-400" />
                  <span>Add Bot</span>
                </a>
              </div>
            </div>
          )}
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

      {/* INVITE BANNER */}
      <div className="glass-card p-6 rounded-2xl border border-white/5 bg-gradient-to-r from-purple-950/30 to-black/60 flex flex-col md:flex-row items-center justify-between gap-4">
        <div>
          <h4 className="text-base font-bold text-white">Want MusicMaid in Your Discord Server?</h4>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            Zero complex setup — invites with one click and auto-configures your voice room.
          </p>
        </div>
        <div className="flex items-center gap-2.5 shrink-0">
          <a
            href="https://discord.com/oauth2/authorize?client_id=1418299882950623253&permissions=3165184&scope=bot%20applications.commands"
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-primary btn-sm flex items-center gap-1.5 py-2 px-4 text-xs font-bold"
          >
            <Plus className="w-4 h-4" />
            <span>Add to Discord</span>
          </a>
          <a
            href="https://discord.gg/KSxEHfmpCe"
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-secondary btn-sm flex items-center gap-1.5 py-2 px-4 text-xs font-bold"
          >
            <MessageCircle className="w-4 h-4" />
            <span>Community</span>
          </a>
        </div>
      </div>

      {/* FOOTER LEGAL LINKS */}
      <div className="flex items-center justify-center gap-4 text-xs text-[var(--text-muted)] py-4">
        <Link href="/terms" className="hover:text-white transition-colors">
          Terms of Service
        </Link>
        <span>•</span>
        <Link href="/privacy" className="hover:text-white transition-colors">
          Privacy Policy
        </Link>
        <span>•</span>
        <Link href="/refund" className="hover:text-white transition-colors">
          Refund Policy
        </Link>
        <span>•</span>
        <Link href="/contact" className="hover:text-white transition-colors">
          Contact Support
        </Link>
      </div>
    </div>
  );
}
