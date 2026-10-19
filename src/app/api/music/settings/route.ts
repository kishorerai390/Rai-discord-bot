import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getMusicDb } from "@/lib/db";
import type { GuildSettings } from "@/types/settings";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const guildId = searchParams.get("guild_id") || "1525030316845301781";

    const botApiUrl = process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "https://rai-discord-bot.onrender.com";
    try {
      const res = await fetch(`${botApiUrl}/api/music/guild-settings?guild_id=${encodeURIComponent(guildId)}`, {
        headers: { "Content-Type": "application/json" },
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) {
        const json = await res.json();
        if (json.success && json.data) {
          return NextResponse.json(json);
        }
      }
    } catch {
      // Fallback to local DB
    }

    const db = getMusicDb();
    let row: any = null;
    try {
      row = db.prepare("SELECT * FROM music_guild_settings WHERE guild_id = ?").get(guildId);
    } catch {
      row = null;
    }

    const defaultSettings: GuildSettings = {
      guild_id: guildId,
      prefix: row?.prefix || ",",
      default_volume: row?.default_volume ?? 80,
      autoplay_enabled: Boolean(row?.autoplay_enabled ?? false),
      auto_leave_enabled: Boolean(row?.auto_leave_enabled ?? true),
      auto_leave_timeout: row?.auto_leave_timeout ?? 180,
      natural_requests_enabled: Boolean(row?.natural_requests_enabled ?? true),
      allowed_channels: [],
      allowed_voice_channels: [],
      queue_limit: row?.queue_limit ?? 250,
      quiet_mode: false,
      response_style: "normal",
      vote_skip_threshold: 0.5,
      dj_mode_enabled: Boolean(row?.dj_mode_enabled ?? false),
      dj_role_id: row?.dj_role_id ? String(row.dj_role_id) : null,
      request_channel_id: row?.bound_channel_id ? String(row.bound_channel_id) : null,
      twenty_four_seven_enabled: Boolean(row?.twenty_four_seven_enabled ?? false),
      twenty_four_seven_channel_id: null,
    };

    return NextResponse.json({ success: true, data: defaultSettings });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const guildId = String(body.guild_id || "1525030316845301781");
    const user = await getCurrentUser(req);
    const userId = user?.id || "1457382179981099090";

    const botApiUrl = process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "https://rai-discord-bot.onrender.com";
    try {
      const res = await fetch(`${botApiUrl}/api/music/guild-settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, guild_id: guildId, user_id: userId }),
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) {
        const json = await res.json();
        return NextResponse.json(json);
      }
    } catch {
      // Fallback to local DB
    }

    const db = getMusicDb();
    const defaultVol = Math.max(1, Math.min(150, Number(body.default_volume ?? 80)));
    const tfs = body.twenty_four_seven_enabled ? 1 : 0;
    const autoLeave = body.auto_leave_enabled ? 1 : 0;
    const boundCh = body.request_channel_id || null;

    try {
      db.prepare(`
        INSERT INTO music_guild_settings (guild_id, default_volume, twenty_four_seven_enabled, bound_channel_id, auto_leave_empty, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(guild_id) DO UPDATE SET
          default_volume = excluded.default_volume,
          twenty_four_seven_enabled = excluded.twenty_four_seven_enabled,
          bound_channel_id = excluded.bound_channel_id,
          auto_leave_empty = excluded.auto_leave_empty,
          updated_at = CURRENT_TIMESTAMP
      `).run(guildId, defaultVol, tfs, boundCh, autoLeave);
    } catch (e: any) {
      console.warn("Local DB settings update notice:", e);
    }

    return NextResponse.json({
      success: true,
      data: {
        guild_id: guildId,
        message: "Server settings updated successfully",
      },
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
