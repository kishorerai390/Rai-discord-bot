export interface ClusterOverview {
  bot_status: "ONLINE" | "STARTING" | "OFFLINE";
  cluster_name: string;
  uptime_seconds: number;
  gateway_latency_ms: number | null;
  active_guilds: number;
  active_voice_sessions: number;
  currently_playing: number;
  version: string;
  commit: string;
  creator_id?: string | number;
  sla_percentage?: number | null;
  sla_target?: number;
}

export interface SystemHealth {
  system: {
    cpu_percent: number | null;
    memory_mb: number | null;
    memory_percent: number | null;
    python_version: string;
  };
  database: {
    connected: boolean;
    mode: string;
    integrity: string;
  };
  audio_engine: {
    yt_dlp_version: string;
    cookies_present: boolean;
    cookies_status: string;
    lossless_dsp: string;
  };
  timestamp: string;
}

export interface FeatureFlagItem {
  enabled: boolean;
  label: string;
  category: "audio" | "ui" | "community" | "system";
}

export interface OperationalIncident {
  id: string;
  category: string;
  severity: "info" | "warning" | "critical";
  title: string;
  details?: string;
  error?: string;
  acknowledged: boolean;
  timestamp: string;
}

export interface DatabaseBackup {
  filename: string;
  size_bytes: number;
  created_at: string;
}

export interface UserEntitlementLookup {
  user_id: string;
  username: string | null;
  display_name: string | null;
  avatar_url: string | null;
  entitlements: {
    is_premium: boolean;
    tier?: string;
    expires_at?: string | null;
  };
  subscription?: any;
  audit_logs: Array<{
    action: string;
    timestamp: string;
    details: any;
  }>;
}
