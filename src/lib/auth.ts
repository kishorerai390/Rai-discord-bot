import { NextRequest } from "next/server";
import { getWebSessionByToken } from "./db";
import { DiscordUser } from "@/types/auth";

export const DISCORD_CLIENT_ID = process.env.DISCORD_CLIENT_ID || "1556676516274905218";
export const DISCORD_CLIENT_SECRET = process.env.DISCORD_CLIENT_SECRET || "";
export const DISCORD_REDIRECT_URI =
  process.env.DISCORD_REDIRECT_URI || "http://localhost:8080/api/auth/callback";

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
  const token =
    req.cookies.get("session_id")?.value ||
    req.headers.get("authorization")?.replace(/^Bearer\s+/i, "");

  if (!token) return null;

  const session = getWebSessionByToken(token);
  if (!session) return null;

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
