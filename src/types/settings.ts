export interface GuildSettings {
  guild_id: string;
  prefix: string;
  default_volume: number;
  autoplay_enabled: boolean;
  auto_leave_enabled: boolean;
  auto_leave_timeout: number;
  natural_requests_enabled: boolean;
  allowed_channels: string[];
  allowed_voice_channels: string[];
  queue_limit: number;
  quiet_mode: boolean;
  response_style: string;
  vote_skip_threshold: number;
  dj_mode_enabled: boolean;
  dj_role_id: string | null;
  request_channel_id: string | null;
  twenty_four_seven_enabled: boolean;
  twenty_four_seven_channel_id: string | null;
}

export interface SoundboardSound {
  id: string;
  name: string;
  emoji: string;
  query: string;
  category: "Classic" | "Reaction" | "Comedy" | "Anime" | "Meme" | "Gaming";
}
