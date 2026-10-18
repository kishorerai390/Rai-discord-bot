export interface Track {
  id?: string | number;
  title: string;
  url: string;
  artist?: string;
  author?: string;
  duration: number; // in seconds
  thumbnail?: string;
  requested_by?: string;
  requested_by_id?: string;
  requester_name?: string;
  source?: string;
  is_live?: boolean;
}

export interface MusicSession {
  guild_id: string;
  channel_id: string | null;
  channel_name?: string | null;
  voice_channel_name?: string | null;
  is_playing: boolean;
  is_paused: boolean;
  volume: number; // 0-150
  loop_mode: "off" | "track" | "queue";
  twenty_four_seven: boolean;
  is_247?: boolean;
  shuffle: boolean;
  elapsed_seconds: number;
  duration_seconds: number;
  position_seconds?: number;
  current_track: Track | null;
  queue_length: number;
  dj_enabled: boolean;
  auto_dj?: boolean;
  dj_mode?: string;
  dj_mood?: string;
  active_filter?: string;
  eq_preset?: string;
  state?: "PLAYING" | "PAUSED" | "IDLE" | "DISCONNECTED";
}

export interface GuildOption {
  id: string;
  name: string;
  icon: string | null;
  is_active: boolean;
  has_session: boolean;
  voice_connected: boolean;
  member_count?: number;
}

export interface Playlist {
  id: string | number;
  name: string;
  guild_id?: string;
  user_id?: string;
  created_at: string;
  track_count: number;
  tracks?: Track[];
  tracks_json?: string | any[];
}

export interface FavoriteItem {
  id: string | number;
  user_id: string;
  title: string;
  url: string;
  artist?: string;
  author?: string;
  duration?: number;
  thumbnail?: string;
  added_at: string;
}

export interface DSPEqualizerPreset {
  id: string;
  name: string;
  icon: string;
  description: string;
  is_premium: boolean;
  filters: Record<string, string | number>;
}

export interface SearchResult {
  id: string;
  title: string;
  artist: string;
  url: string;
  duration: number;
  duration_fmt?: string;
  thumbnail: string;
  provider?: string;
  source?: string;
}
