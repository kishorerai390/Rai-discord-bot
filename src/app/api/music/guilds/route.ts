import { NextResponse } from "next/server";
import { getMusicDb } from "@/lib/db";

export async function GET() {
  const botApiUrl = process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "https://rai-discord-bot.onrender.com";
  try {
    const resBot = await fetch(`${botApiUrl}/api/music/guilds`, {
      signal: AbortSignal.timeout(2000),
      cache: "no-store",
    });
    if (resBot.ok) {
      const botJson = await resBot.json();
      if (botJson.success && Array.isArray(botJson.data)) {
        return NextResponse.json(botJson);
      }
    }
  } catch {
    // Fallback to local DB
  }

  try {
    const db = getMusicDb();
    let rows: any[] = [];
    try {
      rows = db.prepare("SELECT * FROM music_guild_settings LIMIT 100").all() as any[];
    } catch {
      rows = [];
    }

    const activeSessions = db
      .prepare("SELECT guild_id, state FROM music_sessions")
      .all() as any[];

    const sessionMap = new Map<string, string>();
    for (const s of activeSessions) {
      sessionMap.set(String(s.guild_id), s.state);
    }

    const guilds = rows.map((r) => ({
      id: String(r.guild_id),
      name: `Server ${r.guild_id}`,
      icon: null,
      is_active: sessionMap.has(String(r.guild_id)),
      has_session: sessionMap.has(String(r.guild_id)),
      voice_connected: sessionMap.get(String(r.guild_id)) === "PLAYING",
    }));

    if (guilds.length === 0) {
      guilds.push({
        id: "1457382179981099090",
        name: "✦ ʀᴀɪ ʀᴀᴍ ✦",
        icon: null,
        is_active: true,
        has_session: true,
        voice_connected: true,
      });
    }

    return NextResponse.json({
      success: true,
      data: {
        guilds,
      },
    });
  } catch (err: any) {
    return NextResponse.json({
      success: false,
      error: err.message,
      data: { guilds: [] },
    });
  }
}
