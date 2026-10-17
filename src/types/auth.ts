export interface DiscordUser {
  id: string;
  username: string;
  display_name: string;
  discriminator: string;
  avatar: string | null;
  avatar_url: string;
  email?: string | null;
  is_admin: boolean;
  is_staff: boolean;
  is_owner: boolean;
  guilds?: Array<{
    id: string;
    name: string;
    icon: string | null;
    owner: boolean;
    permissions: string;
  }>;
}

export interface WebSession {
  session_id: string;
  user_id: string;
  discord_user_id: string;
  username: string;
  discriminator: string;
  avatar: string | null;
  access_token: string;
  refresh_token: string;
  expires_at: string;
  created_at: string;
  is_active: number;
}
