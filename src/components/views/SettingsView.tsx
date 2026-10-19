"use client";

import React, { useState, useEffect } from "react";
import { Sliders, Shield, Volume2, Radio, Lock, Clock, Check, RefreshCw } from "lucide-react";
import type { GuildSettings } from "@/types/settings";
import type { DiscordUser } from "@/types/auth";

interface SettingsViewProps {
  guildId: string;
  user: DiscordUser | null;
  onShowToast: (msg: string, type?: "success" | "danger" | "info") => void;
}

export function SettingsView({ guildId, user, onShowToast }: SettingsViewProps) {
  const [settings, setSettings] = useState<GuildSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/music/settings?guild_id=${encodeURIComponent(guildId)}`);
      const json = await res.json();
      if (json.success && json.data) {
        setSettings(json.data);
      } else {
        onShowToast(json.error || "Failed to load guild settings", "danger");
      }
    } catch (e: any) {
      onShowToast(`Settings load error: ${e.message}`, "danger");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, [guildId]);

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const res = await fetch("/api/music/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...settings, guild_id: guildId }),
      });
      const json = await res.json();
      if (json.success) {
        onShowToast("Server administrator settings saved successfully! ✦", "success");
      } else {
        onShowToast(json.error?.message || json.error || "Save failed", "danger");
      }
    } catch (e: any) {
      onShowToast(`Save error: ${e.message}`, "danger");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center gap-3">
        <div className="w-8 h-8 rounded-full border-2 border-(--primary) border-t-transparent animate-spin" />
        <p className="text-sm text-(--text-muted)">Loading Server Administration Settings...</p>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-8 text-center backdrop-blur-xl">
        <p className="text-rose-400 font-semibold">Failed to load server settings.</p>
        <button onClick={fetchSettings} className="btn btn-secondary btn-sm mt-3">
          <RefreshCw className="w-4 h-4" /> Try Again
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto">
      {/* HEADER CARD */}
      <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6 backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-white flex items-center gap-2">
            <Sliders className="w-6 h-6 text-purple-400" />
            <span>Server Administrator Dashboard</span>
          </h2>
          <p className="text-xs text-(--text-muted) mt-1">
            Configure authoritative playback parameters, 24/7 staying lock, and DJ role permissions for guild ID: {guildId}.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchSettings}
            disabled={saving}
            className="btn btn-secondary btn-sm flex items-center gap-1.5"
          >
            <RefreshCw className="w-4 h-4" />
            <span>Refresh</span>
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="btn btn-primary btn-sm flex items-center gap-1.5"
          >
            <Check className="w-4 h-4" />
            <span>{saving ? "Saving..." : "Save Settings"}</span>
          </button>
        </div>
      </div>

      {/* SETTINGS MODULES */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* VOICE & 24/7 SETTINGS */}
        <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6 backdrop-blur-xl flex flex-col gap-4">
          <h3 className="text-base font-bold text-white flex items-center gap-2 border-b border-white/5 pb-2">
            <Radio className="w-5 h-5 text-cyan-400" />
            <span>Voice & Session Persistence</span>
          </h3>

          {/* 24/7 Staying Mode */}
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-white">24/7 Voice Lock</div>
              <div className="text-xs text-(--text-muted)">Keep bot connected in voice channel indefinitely</div>
            </div>
            <input
              type="checkbox"
              checked={settings.twenty_four_seven_enabled}
              onChange={(e) =>
                setSettings({ ...settings, twenty_four_seven_enabled: e.target.checked })
              }
              className="toggle w-5 h-5 accent-purple-500 rounded cursor-pointer"
            />
          </div>

          {/* Auto Leave on Empty */}
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-white">Auto-Leave on Empty Voice</div>
              <div className="text-xs text-(--text-muted)">Leave voice channel when all human listeners depart</div>
            </div>
            <input
              type="checkbox"
              checked={settings.auto_leave_enabled}
              onChange={(e) =>
                setSettings({ ...settings, auto_leave_enabled: e.target.checked })
              }
              className="toggle w-5 h-5 accent-purple-500 rounded cursor-pointer"
            />
          </div>

          {/* Auto Leave Timeout */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-white">Auto-Leave Idle Timeout</span>
              <span className="font-mono text-cyan-400">{settings.auto_leave_timeout}s</span>
            </div>
            <input
              type="range"
              min="30"
              max="600"
              step="30"
              value={settings.auto_leave_timeout}
              onChange={(e) =>
                setSettings({ ...settings, auto_leave_timeout: Number(e.target.value) })
              }
              className="w-full h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer accent-cyan-400"
            />
          </div>
        </div>

        {/* AUDIO & VOLUME SETTINGS */}
        <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6 backdrop-blur-xl flex flex-col gap-4">
          <h3 className="text-base font-bold text-white flex items-center gap-2 border-b border-white/5 pb-2">
            <Volume2 className="w-5 h-5 text-emerald-400" />
            <span>Audio & Output Volume</span>
          </h3>

          {/* Default Volume */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-white">Default Server Volume</span>
              <span className="font-mono text-emerald-400">{settings.default_volume}%</span>
            </div>
            <input
              type="range"
              min="10"
              max="150"
              value={settings.default_volume}
              onChange={(e) =>
                setSettings({ ...settings, default_volume: Number(e.target.value) })
              }
              className="w-full h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer accent-emerald-400"
            />
            <span className="text-[10px] text-(--text-dim)">Standard: 1-100% • VIP Boost: Up to 150%</span>
          </div>

          {/* Autoplay toggle */}
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-white">Autoplay & Smart Auto-DJ</div>
              <div className="text-xs text-(--text-muted)">Automatically stream recommended songs when queue is empty</div>
            </div>
            <input
              type="checkbox"
              checked={settings.autoplay_enabled}
              onChange={(e) =>
                setSettings({ ...settings, autoplay_enabled: e.target.checked })
              }
              className="toggle w-5 h-5 accent-purple-500 rounded cursor-pointer"
            />
          </div>

          {/* Command Prefix */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-white">Custom Command Prefix</label>
            <input
              type="text"
              value={settings.prefix}
              maxLength={5}
              onChange={(e) => setSettings({ ...settings, prefix: e.target.value })}
              className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-white text-xs font-mono"
            />
          </div>
        </div>

        {/* DJ ROLE & RBAC PERMISSIONS */}
        <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6 backdrop-blur-xl flex flex-col gap-4">
          <h3 className="text-base font-bold text-white flex items-center gap-2 border-b border-white/5 pb-2">
            <Shield className="w-5 h-5 text-amber-400" />
            <span>DJ Role & RBAC Access Control</span>
          </h3>

          {/* DJ Mode Enabled */}
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-white">Enforce DJ Permissions</div>
              <div className="text-xs text-(--text-muted)">Restrict skip, stop, clear, and volume to DJ role or administrators</div>
            </div>
            <input
              type="checkbox"
              checked={settings.dj_mode_enabled}
              onChange={(e) =>
                setSettings({ ...settings, dj_mode_enabled: e.target.checked })
              }
              className="toggle w-5 h-5 accent-amber-500 rounded cursor-pointer"
            />
          </div>

          {/* DJ Role ID */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-white">DJ Role ID (Discord Snowflake)</label>
            <input
              type="text"
              placeholder="e.g. 1098765432109876543"
              value={settings.dj_role_id || ""}
              onChange={(e) =>
                setSettings({ ...settings, dj_role_id: e.target.value.trim() || null })
              }
              className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-white text-xs font-mono"
            />
          </div>

          {/* Vote Skip Threshold */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between text-xs">
              <span className="font-semibold text-white">Vote Skip Threshold</span>
              <span className="font-mono text-amber-400">
                {Math.round(settings.vote_skip_threshold * 100)}% of Voice Room
              </span>
            </div>
            <input
              type="range"
              min="0.2"
              max="1.0"
              step="0.05"
              value={settings.vote_skip_threshold}
              onChange={(e) =>
                setSettings({ ...settings, vote_skip_threshold: Number(e.target.value) })
              }
              className="w-full h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer accent-amber-400"
            />
          </div>
        </div>

        {/* BOUND COMMAND CHANNELS */}
        <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6 backdrop-blur-xl flex flex-col gap-4">
          <h3 className="text-base font-bold text-white flex items-center gap-2 border-b border-white/5 pb-2">
            <Lock className="w-5 h-5 text-rose-400" />
            <span>Bound Channels & Restrictions</span>
          </h3>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-white">Bound Music Text Channel ID</label>
            <input
              type="text"
              placeholder="e.g. 1457382179981099090 (Leave blank for all channels)"
              value={settings.request_channel_id || ""}
              onChange={(e) =>
                setSettings({ ...settings, request_channel_id: e.target.value.trim() || null })
              }
              className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-white text-xs font-mono"
            />
            <span className="text-[10px] text-(--text-dim)">
              When specified, bot commands and player panels are restricted to this channel.
            </span>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-white">Queue Capacity Limit</label>
            <input
              type="number"
              min={10}
              max={500}
              value={settings.queue_limit}
              onChange={(e) =>
                setSettings({ ...settings, queue_limit: Number(e.target.value) })
              }
              className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-white text-xs font-mono"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
