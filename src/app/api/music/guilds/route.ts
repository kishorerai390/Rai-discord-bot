import { NextResponse } from "next/server";
import { getMusicDb } from "@/lib/db";

export async function GET() {
  try {
    const db = getMusicDb();
    const rows = db
      .prepare(
        `SELECT guild_id, prefix, twenty_four_seven_enabled, default_volume, autodj_enabled 
         FROM music_guild_settings LIMIT 100`
      )
      .all() as any[];

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
