import { NextRequest, NextResponse } from "next/server";
import { getMusicDb } from "@/lib/db";

export async function GET(req: NextRequest) {
  const guildId = req.nextUrl.searchParams.get("guild_id") || "1457382179981099090";

  try {
    const db = getMusicDb();
    const settings = db
      .prepare("SELECT * FROM music_dj_settings WHERE guild_id = ?")
      .get(guildId) as any;

    const guildSettings = db
      .prepare("SELECT autodj_enabled FROM music_guild_settings WHERE guild_id = ?")
      .get(guildId) as any;

    return NextResponse.json({
      success: true,
      data: {
        enabled: Boolean(guildSettings?.autodj_enabled || settings?.enabled),
        mode: settings?.mode || "balanced",
        energy_level: settings?.energy_level || 50,
        recommendations: [
          {
            title: "NEO-TOKYO CYBERPUNK 2026",
            url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            author: "Synthwave Master",
            duration: 215,
          },
          {
            title: "Anime Chill Lo-Fi Study Beats",
            url: "https://www.youtube.com/watch?v=jfKfPfyJRdk",
            author: "Lofi Girl",
            duration: 180,
          },
        ],
      },
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const guildId = String(body.guild_id || "1457382179981099090");
    const enabled = Boolean(body.enabled);
    const mode = String(body.mode || "balanced");

    const db = getMusicDb();
    db.prepare(
      `INSERT INTO music_guild_settings (guild_id, autodj_enabled) VALUES (?, ?)
       ON CONFLICT(guild_id) DO UPDATE SET autodj_enabled = excluded.autodj_enabled`
    ).run(guildId, enabled ? 1 : 0);

    return NextResponse.json({
      success: true,
      data: { enabled, mode, guild_id: guildId },
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
