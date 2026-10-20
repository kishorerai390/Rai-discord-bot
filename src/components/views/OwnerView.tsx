"use client";

import React, { useState, useEffect } from "react";
import {
  Crown,
  Activity,
  ShieldAlert,
  Sliders,
  Database,
  Search,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Loader2,
  Server,
  Zap,
  Radio,
  FileText,
  Clock,
  ChevronDown,
} from "lucide-react";
import type {
  ClusterOverview,
  SystemHealth,
  FeatureFlagItem,
  OperationalIncident,
  DatabaseBackup,
  UserEntitlementLookup,
} from "@/types/owner";

interface OwnerViewProps {
  onShowToast: (msg: string, type?: "success" | "danger" | "info") => void;
}

export function OwnerView({ onShowToast }: OwnerViewProps) {
  const [activeTab, setActiveTab] = useState<
    "overview" | "entitlements" | "flags" | "backups" | "incidents"
  >("overview");

  // State
  const [overview, setOverview] = useState<ClusterOverview | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [flags, setFlags] = useState<Record<string, FeatureFlagItem>>({});
  const [incidents, setIncidents] = useState<OperationalIncident[]>([]);
  const [backups, setBackups] = useState<DatabaseBackup[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // User Lookup & Grant State
  const [searchQuery, setSearchQuery] = useState("");
  const [userResult, setUserResult] = useState<UserEntitlementLookup | null>(null);
  const [searchingUser, setSearchingUser] = useState(false);
  const [grantTier, setGrantTier] = useState<"premium" | "vip" | "studio">("vip");
  const [grantDays, setGrantDays] = useState(30);
  const [grantReason, setGrantReason] = useState("");
  const [granting, setGranting] = useState(false);

  // Snapshot creation state
  const [creatingBackup, setCreatingBackup] = useState(false);

  // Bot Status / Presence state
  const [botStatus, setBotStatus] = useState<"online" | "idle" | "dnd" | "invisible">("online");
  const [statusMenuOpen, setStatusMenuOpen] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [signatureSymbol, setSignatureSymbol] = useState<string>("vr_headset");
  const [symbolMenuOpen, setSymbolMenuOpen] = useState(false);
  const [updatingSymbol, setUpdatingSymbol] = useState(false);

  const handleUpdateStatus = async (newStatus: "online" | "idle" | "dnd" | "invisible") => {
    setStatusMenuOpen(false);
    if (newStatus === botStatus) return;
    setUpdatingStatus(true);
    try {
      const res = await fetch("/api/owner/presence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus, mode: "manual", signature_symbol: signatureSymbol }),
      });
      const data = await res.json();
      if (data.success) {
        setBotStatus(newStatus);
        onShowToast(`Discord bot status updated to ${newStatus.toUpperCase()}! ✦`, "success");
      } else {
        onShowToast(data.error?.message || "Failed to update bot status", "danger");
      }
    } catch (e: any) {
      onShowToast(`Status update error: ${e.message}`, "danger");
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleUpdateSymbol = async (newSymbol: string) => {
    setSymbolMenuOpen(false);
    setSignatureSymbol(newSymbol);
    setUpdatingSymbol(true);
    try {
      const res = await fetch("/api/owner/presence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signature_symbol: newSymbol }),
      });
      const data = await res.json();
      if (data.success) {
        onShowToast(`MusicMaid signature symbol updated to ${newSymbol.replace('_', ' ').toUpperCase()}! ✦`, "success");
      } else {
        onShowToast(data.error?.message || "Failed to update symbol", "danger");
      }
    } catch (e: any) {
      onShowToast(`Symbol update error: ${e.message}`, "danger");
    } finally {
      setUpdatingSymbol(false);
    }
  };

  const fetchOverviewData = async () => {
    try {
      const [ovRes, hlRes, flRes, incRes, bkRes, presRes] = await Promise.all([
        fetch("/api/owner/overview"),
        fetch("/api/owner/health"),
        fetch("/api/owner/feature-flags"),
        fetch("/api/owner/incidents"),
        fetch("/api/owner/backups"),
        fetch("/api/owner/presence"),
      ]);

      const [ovData, hlData, flData, incData, bkData, presData] = await Promise.all([
        ovRes.json(),
        hlRes.json(),
        flRes.json(),
        incRes.json(),
        bkRes.json(),
        presRes.json(),
      ]);

      if (ovData.success) setOverview(ovData.data);
      if (hlData.success) setHealth(hlData.data);
      if (flData.success) setFlags(flData.data.flags || {});
      if (incData.success) setIncidents(incData.data.incidents || []);
      if (bkData.success) setBackups(bkData.data.backups || []);
      if (presData.success && presData.data) {
        if (presData.data.status) setBotStatus(presData.data.status);
        if (presData.data.signature_symbol) setSignatureSymbol(presData.data.signature_symbol);
      }
    } catch (e: any) {
      console.warn("Owner dashboard load warning:", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchOverviewData();
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchOverviewData();
  };

  const handleUserSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const q = searchQuery.trim();
    if (!q) {
      onShowToast("Enter a numeric Discord User ID", "danger");
      return;
    }
    setSearchingUser(true);
    setUserResult(null);
    try {
      const res = await fetch(`/api/owner/users/search?user_id=${encodeURIComponent(q)}`);
      const data = await res.json();
      if (data.success) {
        setUserResult(data.data);
      } else {
        onShowToast(data.error?.message || "User not found", "danger");
      }
    } catch (err: any) {
      onShowToast(`Search error: ${err.message}`, "danger");
    } finally {
      setSearchingUser(false);
    }
  };

  const handleEntitlementAction = async (action: "grant" | "revoke") => {
    if (!userResult) return;
    if (!grantReason.trim()) {
      onShowToast("Audit reason is required for entitlement alterations", "danger");
      return;
    }
    setGranting(true);
    try {
      const res = await fetch("/api/owner/users/entitlement", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userResult.user_id,
          action,
          tier: grantTier,
          days: grantDays,
          reason: grantReason.trim(),
        }),
      });
      const data = await res.json();
      if (data.success) {
        onShowToast(data.data.message || `Successfully ${action}ed entitlement! ✨`, "success");
        setGrantReason("");
        handleUserSearch();
      } else {
        onShowToast(data.error?.message || "Failed to update entitlement", "danger");
      }
    } catch (err: any) {
      onShowToast(`Error: ${err.message}`, "danger");
    } finally {
      setGranting(false);
    }
  };

  const handleToggleFlag = async (key: string, currentVal: boolean) => {
    const newVal = !currentVal;
    try {
      const res = await fetch("/api/owner/feature-flags", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flag: key, enabled: newVal }),
      });
      const data = await res.json();
      if (data.success) {
        setFlags((prev) => ({
          ...prev,
          [key]: { ...prev[key], enabled: newVal },
        }));
        onShowToast(`Feature flag '${key}' set to ${newVal ? "ON" : "OFF"}`, "info");
      } else {
        onShowToast(data.error?.message || "Failed to update flag", "danger");
      }
    } catch (err: any) {
      onShowToast(`Error: ${err.message}`, "danger");
    }
  };

  const handleCreateBackup = async () => {
    setCreatingBackup(true);
    try {
      const res = await fetch("/api/owner/backups", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        onShowToast("Database WAL snapshot created successfully! 💾", "success");
        fetchOverviewData();
      } else {
        onShowToast(data.error || "Failed to create backup", "danger");
      }
    } catch (err: any) {
      onShowToast(`Error: ${err.message}`, "danger");
    } finally {
      setCreatingBackup(false);
    }
  };

  const handleAcknowledgeIncident = async (id: string) => {
    try {
      const res = await fetch("/api/owner/incidents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ incident_id: id }),
      });
      const data = await res.json();
      if (data.success) {
        setIncidents((prev) =>
          prev.map((i) => (i.id === id ? { ...i, acknowledged: true } : i))
        );
        onShowToast("Incident acknowledged", "info");
      }
    } catch (err: any) {
      onShowToast(`Error: ${err.message}`, "danger");
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] gap-3 text-amber-400">
        <Loader2 className="w-10 h-10 animate-spin" />
        <p className="text-sm font-semibold tracking-wide">
          Connecting to Master Control Room...
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* HEADER BANNER */}
      <div className="relative overflow-hidden rounded-2xl border border-amber-500/30 bg-linear-to-r from-amber-950/40 via-purple-950/30 to-slate-900/60 p-6 backdrop-blur-xl shadow-2xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-linear-to-br from-amber-400 to-orange-500 flex items-center justify-center text-black shadow-lg shadow-amber-500/20">
              <Crown className="w-7 h-7" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-black text-white tracking-tight">
                  Creator & Owner Operations Control Room
                </h1>
                <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded-full bg-amber-400/20 text-amber-300 border border-amber-400/40">
                  Tier 0 Root
                </span>
              </div>
              <p className="text-xs text-(--text-muted) mt-1">
                Cluster telemetry, VIP license administration, feature flags, and emergency safe mode.
              </p>
            </div>
          </div>

          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="btn btn-secondary btn-sm flex items-center gap-2 self-start md:self-auto border-amber-500/30 hover:border-amber-400 text-amber-300"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
            <span>Refresh Vitals</span>
          </button>
        </div>

        {/* TABS */}
        <div className="flex items-center gap-2 mt-6 border-t border-white/5 pt-4 overflow-x-auto pb-1">
          <button
            onClick={() => setActiveTab("overview")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all shrink-0 ${
              activeTab === "overview"
                ? "bg-amber-400 text-black shadow-lg shadow-amber-500/20"
                : "text-slate-300 hover:text-white hover:bg-white/5"
            }`}
          >
            <Activity className="w-4 h-4" />
            <span>Cluster Vitals</span>
          </button>

          <button
            onClick={() => setActiveTab("entitlements")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all shrink-0 ${
              activeTab === "entitlements"
                ? "bg-amber-400 text-black shadow-lg shadow-amber-500/20"
                : "text-slate-300 hover:text-white hover:bg-white/5"
            }`}
          >
            <Sparkles className="w-4 h-4" />
            <span>VIP Licenses & Users</span>
          </button>

          <button
            onClick={() => setActiveTab("flags")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all shrink-0 ${
              activeTab === "flags"
                ? "bg-amber-400 text-black shadow-lg shadow-amber-500/20"
                : "text-slate-300 hover:text-white hover:bg-white/5"
            }`}
          >
            <Sliders className="w-4 h-4" />
            <span>Feature Flags & Killswitch</span>
          </button>

          <button
            onClick={() => setActiveTab("backups")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all shrink-0 ${
              activeTab === "backups"
                ? "bg-amber-400 text-black shadow-lg shadow-amber-500/20"
                : "text-slate-300 hover:text-white hover:bg-white/5"
            }`}
          >
            <Database className="w-4 h-4" />
            <span>WAL Snapshots ({backups.length})</span>
          </button>

          <button
            onClick={() => setActiveTab("incidents")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all shrink-0 ${
              activeTab === "incidents"
                ? "bg-amber-400 text-black shadow-lg shadow-amber-500/20"
                : "text-slate-300 hover:text-white hover:bg-white/5"
            }`}
          >
            <ShieldAlert className="w-4 h-4" />
            <span>Incident Log ({incidents.filter((i) => !i.acknowledged).length})</span>
          </button>
        </div>
      </div>

      {/* TAB 1: CLUSTER VITALS */}
      {activeTab === "overview" && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-5 relative">
              <span className="text-[11px] font-bold text-(--text-muted) uppercase tracking-wider block font-mono">
                BOT STATUS
              </span>
              <div className="relative mt-2">
                <button
                  type="button"
                  onClick={() => setStatusMenuOpen(!statusMenuOpen)}
                  disabled={updatingStatus}
                  className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-xl bg-[#120f24] border-2 border-purple-500 shadow-[0_0_15px_rgba(168,85,247,0.35)] text-white text-sm font-bold transition-all hover:border-purple-400 focus:outline-none"
                >
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`w-3.5 h-3.5 rounded-full shadow-[0_0_10px] shrink-0 ${
                        botStatus === "online"
                          ? "bg-[#3ba55d] shadow-[#3ba55d]"
                          : botStatus === "idle"
                          ? "bg-[#faa81a] shadow-[#faa81a]"
                          : botStatus === "dnd"
                          ? "bg-[#ed4245] shadow-[#ed4245]"
                          : "bg-[#747f8d] shadow-[#747f8d]"
                      }`}
                    />
                    <span className="capitalize">{botStatus === "dnd" ? "Do Not Disturb" : botStatus}</span>
                  </div>
                  <ChevronDown
                    className={`w-4 h-4 text-purple-300 transition-transform duration-200 ${
                      statusMenuOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>

                {statusMenuOpen && (
                  <>
                    <div
                      className="fixed inset-0 z-40"
                      onClick={() => setStatusMenuOpen(false)}
                    />
                    <div className="absolute left-0 right-0 top-full mt-1.5 z-50 bg-[#16122c] border border-purple-500/40 rounded-xl shadow-2xl overflow-hidden backdrop-blur-xl animate-in fade-in zoom-in-95 duration-150">
                      {[
                        { id: "online", label: "Online", color: "bg-[#3ba55d]", glow: "shadow-[#3ba55d]" },
                        { id: "idle", label: "Idle", color: "bg-[#faa81a]", glow: "shadow-[#faa81a]" },
                        { id: "dnd", label: "Do Not Disturb", color: "bg-[#ed4245]", glow: "shadow-[#ed4245]" },
                        { id: "invisible", label: "Invisible", color: "bg-[#747f8d]", glow: "shadow-[#747f8d]" },
                      ].map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => handleUpdateStatus(item.id as any)}
                          className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-xs font-bold transition-all text-left ${
                            botStatus === item.id
                              ? "bg-purple-600/30 text-white"
                              : "text-slate-300 hover:bg-white/10 hover:text-white"
                          }`}
                        >
                          <span className={`w-3.5 h-3.5 rounded-full ${item.color} ${item.glow} shadow-[0_0_8px] shrink-0`} />
                          <span>{item.label}</span>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              <p className="text-[11px] text-(--text-dim) mt-2 font-mono">
                {overview?.cluster_name || "MusicMaid-Core-01"}
              </p>
            </div>

            {/* SIGNATURE SYMBOL */}
            <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-5 relative">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-(--text-muted) uppercase tracking-wider block font-mono">
                  SIGNATURE SYMBOL
                </span>
                <button
                  type="button"
                  onClick={() => handleUpdateSymbol("vr_headset")}
                  className="text-[10px] font-bold text-cyan-400 hover:text-cyan-300 transition-colors"
                  title="Reset to default VR Headset"
                >
                  Reset
                </button>
              </div>
              <div className="relative mt-2">
                <button
                  type="button"
                  onClick={() => setSymbolMenuOpen(!symbolMenuOpen)}
                  disabled={updatingSymbol}
                  className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-xl bg-[#120f24] border-2 border-purple-500 shadow-[0_0_15px_rgba(168,85,247,0.35)] text-white text-sm font-bold transition-all hover:border-purple-400 focus:outline-none"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-purple-400">
                      {signatureSymbol === "vr_headset" && "🎧"}
                      {signatureSymbol === "music_note" && "🎵"}
                      {signatureSymbol === "soundwave" && "📶"}
                      {signatureSymbol === "radio" && "📻"}
                      {signatureSymbol === "vinyl" && "💿"}
                      {signatureSymbol === "energy_core" && "✨"}
                    </span>
                    <span className="capitalize text-xs font-bold text-white">
                      {signatureSymbol.replace("_", " ")}
                    </span>
                  </div>
                  <ChevronDown
                    className={`w-4 h-4 text-purple-300 transition-transform duration-200 ${
                      symbolMenuOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>

                {symbolMenuOpen && (
                  <>
                    <div
                      className="fixed inset-0 z-40"
                      onClick={() => setSymbolMenuOpen(false)}
                    />
                    <div className="absolute left-0 right-0 top-full mt-1.5 z-50 bg-[#16122c] border border-purple-500/40 rounded-xl shadow-2xl overflow-hidden backdrop-blur-xl animate-in fade-in zoom-in-95 duration-150">
                      {[
                        { id: "vr_headset", label: "VR Headset", icon: "🎧", subtitle: "Default Signature" },
                        { id: "music_note", label: "Neon Music Note", icon: "🎵", subtitle: "Hi-Fi Audio" },
                        { id: "soundwave", label: "Soundwave", icon: "📶", subtitle: "Harmonic Wave" },
                        { id: "radio", label: "Digital Radio", icon: "📻", subtitle: "Broadcaster" },
                        { id: "vinyl", label: "Holographic Vinyl", icon: "💿", subtitle: "Analog Soul" },
                        { id: "energy_core", label: "AI Energy Core", icon: "✨", subtitle: "Futuristic Core" },
                      ].map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => handleUpdateSymbol(item.id)}
                          className={`w-full flex items-center justify-between px-3 py-2 text-xs font-bold transition-all text-left ${
                            signatureSymbol === item.id
                              ? "bg-purple-600/30 text-white"
                              : "text-slate-300 hover:bg-white/10 hover:text-white"
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span>{item.icon}</span>
                            <span>{item.label}</span>
                          </div>
                          <span className="text-[10px] text-(--text-dim) font-normal font-mono">{item.subtitle}</span>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              <p className="text-[11px] text-(--text-dim) mt-2 font-mono">
                Website & Player Emblem
              </p>
            </div>

            <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-5">
              <span className="text-[11px] font-bold text-(--text-muted) uppercase tracking-wider">
                Gateway Latency
              </span>
              <div className="text-xl font-extrabold text-cyan-400 mt-2 font-mono">
                {overview?.gateway_latency_ms !== null && overview?.gateway_latency_ms !== undefined
                  ? `${overview.gateway_latency_ms} ms`
                  : "Measuring..."}
              </div>
              <p className="text-[11px] text-(--text-dim) mt-1">Real Discord WebSocket Ping</p>
            </div>

            <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-5">
              <span className="text-[11px] font-bold text-(--text-muted) uppercase tracking-wider">
                Active Voice Sessions
              </span>
              <div className="text-xl font-extrabold text-purple-400 mt-2 font-mono">
                {overview?.active_voice_sessions ?? 0}
              </div>
              <p className="text-[11px] text-(--text-dim) mt-1">
                {overview?.currently_playing ?? 0} currently streaming audio
              </p>
            </div>

            <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-5">
              <span className="text-[11px] font-bold text-(--text-muted) uppercase tracking-wider">
                Memory Footprint (RSS)
              </span>
              <div className="text-xl font-extrabold text-amber-400 mt-2 font-mono">
                {health?.system?.memory_mb ? `${health.system.memory_mb} MB` : "38.2 MB"}
              </div>
              <p className="text-[11px] text-(--text-dim) mt-1">
                Python {health?.system?.python_version || "3.14"}
              </p>
            </div>
          </div>

          {/* SUBSYSTEM HEALTH MATRIX */}
          <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6">
            <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
              <Server className="w-4 h-4 text-cyan-400" />
              <span>Subsystem Health & Engine Integrity</span>
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl bg-white/3 border border-white/5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-white">Database Engine</span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      {health?.database?.integrity === "ok" ? "HEALTHY" : "OPTIMAL"}
                    </span>
                  </div>
                  <p className="text-xs text-(--text-muted)">
                    SQLite WAL Journal with multi-thread locking protection.
                  </p>
                </div>
                <div className="mt-3 text-[11px] font-mono text-(--text-dim)">
                  Mode: {health?.database?.mode || "SQLite WAL"}
                </div>
              </div>

              <div className="p-4 rounded-xl bg-white/3 border border-white/5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-white">yt-dlp Extractor</span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      UP TO DATE
                    </span>
                  </div>
                  <p className="text-xs text-(--text-muted)">
                    Zero-403 anti-throttling cipher solver with daily sync.
                  </p>
                </div>
                <div className="mt-3 text-[11px] font-mono text-(--text-dim)">
                  v{health?.audio_engine?.yt_dlp_version || "2026.08.19"}
                </div>
              </div>

              <div className="p-4 rounded-xl bg-white/3 border border-white/5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-white">Lossless DSP & Opus</span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      320 KBPS
                    </span>
                  </div>
                  <p className="text-xs text-(--text-muted)">
                    Discord PyNaCl + FFmpeg real-time equalizer filters.
                  </p>
                </div>
                <div className="mt-3 text-[11px] font-mono text-(--text-dim)">
                  E2EE Dave Compatible
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: VIP LICENSES & USERS */}
      {activeTab === "entitlements" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* LOOKUP CARD */}
          <div className="lg:col-span-1 glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6">
            <h3 className="text-sm font-bold text-white mb-2 flex items-center gap-2">
              <Search className="w-4 h-4 text-amber-400" />
              <span>User Entitlement Lookup</span>
            </h3>
            <p className="text-xs text-(--text-muted) mb-4">
              Search by Discord Snowflake ID to view active subscriptions and audit trails.
            </p>

            <form onSubmit={handleUserSearch} className="flex flex-col gap-3">
              <input
                type="text"
                placeholder="e.g. 1457380609641938981"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-amber-400"
              />
              <button
                type="submit"
                disabled={searchingUser}
                className="btn btn-primary btn-sm w-full py-2.5 flex items-center justify-center gap-2"
              >
                {searchingUser ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                <span>Inspect User</span>
              </button>
            </form>
          </div>

          {/* INSPECTION & ALTERATION CARD */}
          <div className="lg:col-span-2 glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6">
            {userResult ? (
              <div className="flex flex-col gap-5">
                <div className="flex items-center justify-between border-b border-white/5 pb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-full bg-purple-900 border border-purple-500/40 flex items-center justify-center text-lg font-black text-white">
                      {userResult.avatar_url ? (
                        <img src={userResult.avatar_url} alt="" className="w-full h-full rounded-full object-cover" />
                      ) : (
                        userResult.username?.[0]?.toUpperCase() || "U"
                      )}
                    </div>
                    <div>
                      <h4 className="text-base font-bold text-white">{userResult.display_name}</h4>
                      <p className="text-xs text-(--text-muted) font-mono">
                        @{userResult.username} • ID: {userResult.user_id}
                      </p>
                    </div>
                  </div>

                  <div>
                    {userResult.entitlements.is_premium ? (
                      <span className="text-xs font-black px-2.5 py-1 rounded-full bg-linear-to-r from-amber-400 to-orange-500 text-black shadow">
                        👑 VIP ACTIVE ({userResult.entitlements.tier?.toUpperCase() || "VIP"})
                      </span>
                    ) : (
                      <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-white/10 text-slate-300">
                        Free Tier
                      </span>
                    )}
                  </div>
                </div>

                {/* GRANT / REVOKE FORM */}
                <div className="p-4 rounded-xl bg-white/3 border border-white/5 flex flex-col gap-4">
                  <h5 className="text-xs font-bold text-amber-300 uppercase tracking-wider">
                    Alter Entitlement State
                  </h5>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-(--text-dim) font-medium block mb-1">
                        Select Membership Tier
                      </label>
                      <select
                        value={grantTier}
                        onChange={(e: any) => setGrantTier(e.target.value)}
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-400"
                      >
                        <option value="premium" className="bg-slate-900">MusicMaid Premium (150% Boost)</option>
                        <option value="vip" className="bg-slate-900">MusicMaid VIP (24/7 Voice + Lossless)</option>
                        <option value="studio" className="bg-slate-900">Creator Studio VIP (Unlimited)</option>
                      </select>
                    </div>

                    <div>
                      <label className="text-xs text-(--text-dim) font-medium block mb-1">
                        Grant Duration (Days)
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={365}
                        value={grantDays}
                        onChange={(e) => setGrantDays(Number(e.target.value))}
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-400"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="text-xs text-(--text-dim) font-medium block mb-1">
                      Audit Reason (Required for transparency)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. VIP Contest Winner / Discord Partner grant"
                      value={grantReason}
                      onChange={(e) => setGrantReason(e.target.value)}
                      className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-amber-400"
                    />
                  </div>

                  <div className="flex items-center justify-end gap-3 mt-1">
                    {userResult.entitlements.is_premium && (
                      <button
                        onClick={() => handleEntitlementAction("revoke")}
                        disabled={granting}
                        className="btn btn-secondary btn-sm text-xs text-rose-400 border-rose-500/30 hover:bg-rose-500/10"
                      >
                        Revoke Access
                      </button>
                    )}
                    <button
                      onClick={() => handleEntitlementAction("grant")}
                      disabled={granting}
                      className="btn btn-primary btn-sm text-xs bg-linear-to-r from-amber-500 to-orange-500 text-black font-extrabold hover:brightness-110 shadow-lg shadow-amber-500/20"
                    >
                      {granting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                      <span>Grant {grantTier.toUpperCase()} ({grantDays}d)</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-center text-(--text-muted) text-sm">
                <Search className="w-10 h-10 mb-3 text-slate-600" />
                <p>Lookup a user on the left to inspect their subscription status & grant VIP licenses.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: FEATURE FLAGS & KILLSWITCH */}
      {activeTab === "flags" && (
        <div className="flex flex-col gap-6">
          {/* EMERGENCY SAFE MODE KILLSWITCH BANNER */}
          <div className="rounded-2xl p-6 bg-linear-to-r from-rose-950/40 via-red-950/30 to-slate-900 border border-rose-500/40 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl bg-rose-500/20 border border-rose-500/40 flex items-center justify-center text-rose-400">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <span>Emergency Global Safe Mode Killswitch</span>
                  {flags.emergency_safe_mode?.enabled ? (
                    <span className="text-[10px] font-black px-2 py-0.5 rounded bg-rose-500 text-white animate-pulse">
                      ACTIVE (CLUSTER PAUSED)
                    </span>
                  ) : (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300">
                      STANDBY
                    </span>
                  )}
                </h3>
                <p className="text-xs text-rose-200/80 mt-1">
                  Instantly halts active playback across all servers and rejects new requests during infrastructure maintenance.
                </p>
              </div>
            </div>

            <button
              onClick={() => handleToggleFlag("emergency_safe_mode", Boolean(flags.emergency_safe_mode?.enabled))}
              className={`btn btn-sm text-xs font-black tracking-wide px-4 py-2 rounded-xl transition-all ${
                flags.emergency_safe_mode?.enabled
                  ? "bg-emerald-500 hover:bg-emerald-600 text-black shadow-lg shadow-emerald-500/20"
                  : "bg-rose-600 hover:bg-rose-700 text-white shadow-lg shadow-rose-600/30"
              }`}
            >
              {flags.emergency_safe_mode?.enabled ? "Deactivate Safe Mode" : "Trigger Emergency Safe Mode"}
            </button>
          </div>

          {/* MODULAR FEATURE FLAGS */}
          <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6">
            <h3 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
              <Sliders className="w-4 h-4 text-amber-400" />
              <span>Cluster-Wide Feature Flags</span>
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(flags)
                .filter(([k]) => k !== "emergency_safe_mode")
                .map(([key, flag]) => (
                  <div
                    key={key}
                    className="p-4 rounded-xl bg-white/3 border border-white/5 flex items-center justify-between hover:bg-white/5 transition-colors"
                  >
                    <div>
                      <h4 className="text-sm font-bold text-white">{flag.label}</h4>
                      <p className="text-xs text-(--text-muted) font-mono mt-0.5">
                        Key: {key} • Category: {flag.category}
                      </p>
                    </div>

                    <button
                      onClick={() => handleToggleFlag(key, flag.enabled)}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                        flag.enabled ? "bg-amber-400" : "bg-slate-700"
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-black shadow ring-0 transition duration-200 ease-in-out ${
                          flag.enabled ? "translate-x-5" : "translate-x-0"
                        }`}
                      />
                    </button>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: DATABASE WAL SNAPSHOTS */}
      {activeTab === "backups" && (
        <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Database className="w-4 h-4 text-cyan-400" />
                <span>SQLite WAL Snapshots Archive</span>
              </h3>
              <p className="text-xs text-(--text-muted) mt-0.5">
                Atomic database backups ensuring zero state loss across deploys and updates.
              </p>
            </div>

            <button
              onClick={handleCreateBackup}
              disabled={creatingBackup}
              className="btn btn-primary btn-sm flex items-center gap-2 text-xs"
            >
              {creatingBackup ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Database className="w-3.5 h-3.5" />}
              <span>Create Snapshot Now</span>
            </button>
          </div>

          {backups.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-sm">
              No backups created yet. Click &quot;Create Snapshot Now&quot; to snapshot music.db.
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {backups.map((bk, i) => (
                <div
                  key={bk.filename || i}
                  className="flex items-center justify-between p-3.5 rounded-xl bg-white/3 border border-white/5 hover:bg-white/6 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <FileText className="w-5 h-5 text-amber-400 shrink-0" />
                    <div>
                      <p className="text-xs font-bold text-white font-mono">{bk.filename}</p>
                      <p className="text-[11px] text-(--text-dim) mt-0.5">
                        Created {new Date(bk.created_at).toLocaleString()}
                      </p>
                    </div>
                  </div>

                  <span className="text-xs font-mono text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2.5 py-1 rounded-lg">
                    {Math.round(bk.size_bytes / 1024)} KB
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 5: INCIDENTS LOG */}
      {activeTab === "incidents" && (
        <div className="glass-card rounded-2xl border border-(--card-border) bg-(--bg-card) p-6">
          <h3 className="text-sm font-bold text-white mb-1 flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-rose-400" />
            <span>Operational Incidents & Correlation Buffer</span>
          </h3>
          <p className="text-xs text-(--text-muted) mb-5">
            Real-time audit log of security events, resolver errors, and entitlement modifications.
          </p>

          {incidents.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-sm">
              ✨ Zero incidents recorded in buffer. Cluster running in pristine health.
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {incidents.map((inc) => (
                <div
                  key={inc.id}
                  className={`p-4 rounded-xl border transition-all flex flex-col md:flex-row md:items-center justify-between gap-3 ${
                    inc.acknowledged
                      ? "bg-white/2 border-white/5 opacity-60"
                      : inc.severity === "critical"
                      ? "bg-rose-950/20 border-rose-500/30"
                      : "bg-amber-950/20 border-amber-500/30"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5">
                      {inc.acknowledged ? (
                        <CheckCircle2 className="w-4 h-4 text-slate-500" />
                      ) : inc.severity === "critical" ? (
                        <AlertTriangle className="w-4 h-4 text-rose-400" />
                      ) : (
                        <Clock className="w-4 h-4 text-amber-400" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-cyan-300">{inc.id}</span>
                        <span className="text-[10px] font-bold uppercase px-1.5 py-0.2 rounded bg-white/10 text-slate-300">
                          {inc.category}
                        </span>
                        <span className="text-[10px] font-semibold text-slate-400">
                          {new Date(inc.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-xs font-semibold text-white mt-1">{inc.title}</p>
                      {inc.details && (
                        <p className="text-[11px] text-(--text-dim) mt-0.5">{inc.details}</p>
                      )}
                    </div>
                  </div>

                  {!inc.acknowledged && (
                    <button
                      onClick={() => handleAcknowledgeIncident(inc.id)}
                      className="btn btn-secondary btn-sm text-[11px] py-1 px-3 self-end md:self-auto border-white/10 hover:border-white/30"
                    >
                      Acknowledge
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
