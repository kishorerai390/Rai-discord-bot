import { NextRequest } from "next/server";
import { getWebSessionByToken } from "./db";
import { DiscordUser } from "@/types/auth";

export const DISCORD_CLIENT_ID = process.env.DISCORD_CLIENT_ID || "1556676516274905218";
export const DISCORD_CLIENT_SECRET = process.env.DISCORD_CLIENT_SECRET || "";
export const DISCORD_REDIRECT_URI =
  process.env.DISCORD_REDIRECT_URI || "http://localhost:8080/api/auth/callback";

// Cookie names used by the two auth flows.
// Python backend sets "rai_session"; Next.js callback sets "session_id".
// We must accept both so that users logged in via either flow are authenticated.
export const SESSION_COOKIE_NAMES = ["session_id", "rai_session"] as const;

export function getPublicBaseUrl(req?: NextRequest): string {
  if (process.env.PUBLIC_BASE_URL) return process.env.PUBLIC_BASE_URL.replace(/\/$/, "");
  if (process.env.MUSICMAID_WEBSITE_URL) return process.env.MUSICMAID_WEBSITE_URL.replace(/\/$/, "");
  if (process.env.RENDER_EXTERNAL_URL) return process.env.RENDER_EXTERNAL_URL.replace(/\/$/, "");
  if (req) {
    const proto = req.headers.get("x-forwarded-proto") || "http";
    const host = req.headers.get("host") || "localhost:8080";
    return `${proto}://${host}`;
  }
  return "https://rai-discord-bot.onrender.com";
}

export function getDiscordAuthUrl(baseUrl: string): string {
  const redirectUri = `${baseUrl}/api/auth/callback`;
  const scope = encodeURIComponent("identify email guilds");
  return `https://discord.com/api/oauth2/authorize?client_id=${DISCORD_CLIENT_ID}&redirect_uri=${encodeURIComponent(
    redirectUri
  )}&response_type=code&scope=${scope}`;
}

export async function getCurrentUser(req: NextRequest): Promise<DiscordUser | null> {
  // Accept both cookie names: session_id (Next.js flow) and rai_session (Python flow)
  let token: string | undefined;
  for (const name of SESSION_COOKIE_NAMES) {
    token = req.cookies.get(name)?.value;
    if (token) break;
  }
  // Also accept Authorization: Bearer <token> header
  if (!token) {
    token = req.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  }

  if (!token) return null;

  const session = getWebSessionByToken(token);
  if (!session) return null;

  // Reject expired sessions (expiry stored as ISO string)
  if (session.expires_at) {
    try {
      const expiry = new Date(session.expires_at);
      if (!isNaN(expiry.getTime()) && expiry < new Date()) {
        return null;
      }
    } catch {
      // Malformed expiry — treat as valid to avoid breaking existing sessions
    }
  }

  const userId = String(session.user_id || session.discord_user_id);
  const configuredOwners = (
    process.env.BOT_CREATOR_ID ||
    process.env.CREATOR_ID ||
    process.env.BOT_OWNER_ID ||
    process.env.BOT_OWNER_IDS ||
    process.env.OWNER_ID ||
    "1457380609641938981"
  )
    .split(",")
    .map((s) => s.trim());

  const isOwner = configuredOwners.includes(userId);

  return {
    id: userId,
    username: session.username || `User_${userId}`,
    display_name: session.username || `User_${userId}`,
    discriminator: session.discriminator || "0",
    avatar: session.avatar,
    avatar_url: session.avatar
      ? `https://cdn.discordapp.com/avatars/${userId}/${session.avatar}.png`
      : "https://cdn.discordapp.com/embed/avatars/0.png",
    is_admin: isOwner,
    is_staff: isOwner,
    is_owner: isOwner,
  };
}
