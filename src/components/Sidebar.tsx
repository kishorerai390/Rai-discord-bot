"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  Sparkles,
  Search,
  Music,
  Radio,
  Sliders,
  Library,
  BarChart3,
  Bot,
  LogOut,
  LogIn,
  Crown,
  Volume2,
  Settings,
} from "lucide-react";
import { DiscordUser } from "@/types/auth";
import { GuildOption } from "@/types/music";

interface SidebarProps {
  currentUser: DiscordUser | null;
  guilds: GuildOption[];
  activeGuildId: string;
  onSelectGuild: (guildId: string) => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  voiceStatusText?: string;
}

export function Sidebar({
  currentUser,
  guilds,
  activeGuildId,
  onSelectGuild,
  mobileOpen,
  onCloseMobile,
  voiceStatusText = "320kbps Lossless Ready",
}: SidebarProps) {
  const pathname = usePathname();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const activeGuild =
    guilds.find((g) => g.id === activeGuildId) || guilds[0] || {
      id: "1457382179981099090",
      name: "✦ ʀᴀɪ ʀᴀᴍ ✦",
    };

  const navLinks = [
    { href: "/login", label: "Login & Welcome", icon: LogIn },
    { href: "/dashboard", label: "User Dashboard", icon: Home },
    { href: "/premium", label: "MusicMaid VIP", icon: Sparkles, isPremium: true },
    { href: "/search", label: "Search & Discover", icon: Search },
    { href: "/queue", label: "Queue & Live Player", icon: Music },
    { href: "/canvas", label: "Stage Visualizer", icon: Radio },
    { href: "/soundboard", label: "Voice Soundboard", icon: Volume2 },
    { href: "/autodj", label: "Smart Auto-DJ", icon: Bot },
    { href: "/library", label: "Playlists & Library", icon: Library },
    { href: "/audio", label: "Equalizer & DSP", icon: Sliders },
    { href: "/settings", label: "Server Settings", icon: Settings },
    { href: "/stats", label: "Telemetry & Health", icon: BarChart3 },
  ];

  const isOwner = currentUser?.is_owner;

  return (
    <aside
      className={`fixed top-0 left-0 bottom-[var(--player-height)] z-50 w-[var(--sidebar-width)] bg-[var(--bg-sidebar)] border-r border-[var(--border-subtle)] backdrop-blur-xl flex flex-col p-4 gap-3 overflow-y-auto overflow-x-hidden transition-transform duration-300 ${
        mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
      }`}
    >
      {/* BRAND LOGO */}
      <Link href="/" className="flex items-center gap-3 p-2 rounded-xl hover:bg-white/5 transition-all">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-600 to-cyan-400 flex items-center justify-center text-xl shadow-lg shadow-purple-600/30">
          🎵
        </div>
        <div>
          <h1 className="font-extrabold text-base tracking-tight text-white leading-tight">
            MusicMaid
          </h1>
          <p className="text-xs text-[var(--text-dim)] font-medium">Discord Music Engine</p>
        </div>
      </Link>

      {/* SERVER SWITCHER */}
      <div className="relative">
        <button
          onClick={() => setDropdownOpen(!dropdownOpen)}
          className="w-full flex items-center justify-between p-2.5 rounded-xl bg-white/[0.04] border border-[var(--border-subtle)] hover:border-purple-500/40 transition-all text-left"
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-6 h-6 rounded-lg bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-xs font-bold text-white shrink-0">
              ⚡
            </div>
            <div className="truncate">
              <div className="text-xs font-bold text-white truncate">{activeGuild.name}</div>
              <div className="text-[10px] text-emerald-400 flex items-center gap-1">
                <span className="pulse-dot"></span>
                <span>Connected</span>
              </div>
            </div>
          </div>
          <span className="text-xs text-[var(--text-dim)] shrink-0">▼</span>
        </button>

        {dropdownOpen && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-[#0c1020] border border-purple-500/30 rounded-xl shadow-2xl p-1.5 z-50 max-h-56 overflow-y-auto">
            {guilds.map((g) => (
              <button
                key={g.id}
                onClick={() => {
                  onSelectGuild(g.id);
                  setDropdownOpen(false);
                }}
                className={`w-full text-left px-3 py-2 text-xs rounded-lg flex items-center justify-between transition-colors ${
                  g.id === activeGuildId
                    ? "bg-purple-600/30 text-white font-bold"
                    : "text-slate-300 hover:bg-white/5"
                }`}
              >
                <span className="truncate">{g.name}</span>
                {g.id === activeGuildId && <span className="text-purple-400">✓</span>}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* PROMINENT SIDEBAR PREMIUM PROMO CARD */}
      <Link
        href="/premium"
        onClick={onCloseMobile}
        className="group relative overflow-hidden rounded-xl p-3 bg-gradient-to-br from-purple-900/30 via-fuchsia-900/20 to-pink-900/30 border border-fuchsia-500/40 hover:border-fuchsia-400/80 transition-all shadow-lg hover:shadow-fuchsia-500/20"
      >
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] font-extrabold tracking-wider text-pink-400 uppercase">
            ✨ 150% Boost • 24/7 Voice
          </span>
          <Crown className="w-3.5 h-3.5 text-pink-400" />
        </div>
        <div className="text-xs font-bold text-white group-hover:text-pink-200 transition-colors">
          💎 MusicMaid VIP
        </div>
        <p className="text-[11px] text-slate-400 leading-tight mt-0.5">
          Studio DSP, 24/7 staying mode & zero queue limits
        </p>
        <div className="mt-2 inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-gradient-to-r from-pink-500 to-purple-600 text-white shadow">
          <span>View Plans</span>
          <span>⚡</span>
        </div>
      </Link>

      {/* NAVIGATION LIST */}
      <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-dim)] px-2 mt-1">
        Music Engine
      </div>
      <nav className="flex flex-col gap-1">
        {navLinks.map((link) => {
          const Icon = link.icon;
          const isActive = pathname === link.href || (link.href === "/dashboard" && pathname === "/");
          return (
            <Link
              key={link.href}
              href={link.href}
              onClick={onCloseMobile}
              className={`flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-semibold transition-all ${
                link.isPremium
                  ? isActive
                    ? "bg-gradient-to-r from-pink-500/30 to-purple-600/30 text-white border border-pink-500/50 shadow-lg shadow-pink-500/20"
                    : "text-pink-300 bg-pink-500/10 border border-pink-500/30 hover:bg-pink-500/20 hover:text-white"
                  : isActive
                  ? "bg-gradient-to-r from-purple-600/30 to-cyan-500/15 text-white border border-purple-500/45 shadow-md shadow-purple-600/15"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span>{link.label}</span>
            </Link>
          );
        })}

        {isOwner && (
          <Link
            href="/owner"
            onClick={onCloseMobile}
            className={`flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-black transition-all ${
              pathname === "/owner"
                ? "bg-gradient-to-r from-amber-500/30 to-orange-500/30 text-amber-300 border border-amber-400/60 shadow-lg shadow-amber-500/20"
                : "text-amber-300 bg-amber-500/10 border border-amber-500/30 hover:bg-amber-500/20 hover:text-white"
            }`}
          >
            <Crown className="w-4 h-4 text-amber-400 shrink-0" />
            <span>Control Room</span>
          </Link>
        )}
      </nav>

      {/* SIDEBAR FOOTER (VOICE PILL & USER PROFILE) */}
      <div className="mt-auto pt-3 border-t border-[var(--border-subtle)] flex flex-col gap-2.5">
        <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/25 text-emerald-400 text-xs font-medium">
          <Volume2 className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">{voiceStatusText}</span>
        </div>

        {currentUser ? (
          <div className="flex flex-col gap-2 p-2 rounded-xl bg-white/[0.03] border border-[var(--border-subtle)]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <img
                  src={currentUser.avatar_url}
                  alt={currentUser.username}
                  className="w-7 h-7 rounded-full bg-purple-900 border border-purple-500/40"
                />
                <div className="truncate">
                  <div className="text-xs font-bold text-white truncate leading-none">
                    {currentUser.display_name}
                  </div>
                  <div className="mt-0.5">
                    {isOwner ? (
                      <span className="text-[10px] font-black px-1.5 py-0.5 rounded bg-gradient-to-r from-amber-400 to-orange-500 text-black">
                        👑 CREATOR VIP
                      </span>
                    ) : (
                      <span className="text-[10px] font-semibold text-slate-400">
                        Free Member
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <Link
                href="/api/auth/logout"
                title="Sign out"
                className="p-1 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
              >
                <LogOut className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        ) : (
          <Link
            href="/api/auth/login"
            className="flex items-center justify-center gap-2 w-full py-2 px-3 rounded-xl bg-[#5865F2] hover:bg-[#4752c4] text-white text-xs font-bold transition-all shadow-md shadow-[#5865F2]/25"
          >
            <LogIn className="w-3.5 h-3.5" />
            <span>Sign in with Discord</span>
          </Link>
        )}
      </div>
    </aside>
  );
}
