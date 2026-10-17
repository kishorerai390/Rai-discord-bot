import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getMusicDb } from "@/lib/db";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const guildId = String(body.guild_id || "1457382179981099090");
    const action = String(body.action || "").toUpperCase().trim();
    const payload = body.payload || {};

    if (!action) {
      return NextResponse.json({ success: false, error: "Action is required" }, { status: 400 });
    }

    const user = await getCurrentUser(req);
    const userId = user?.id || "1457382179981099090";

    const db = getMusicDb();
    const nowIso = new Date().toISOString();

    // 1. Enqueue action for autonomous Discord bot worker
    const actionId = `act_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    try {
      db.prepare(
        `INSERT INTO music_web_actions (guild_id, action, payload_json, user_id, status, created_at)
         VALUES (?, ?, ?, ?, 'PENDING', ?)`
      ).run(guildId, action, JSON.stringify(payload), userId, nowIso);
    } catch (e) {
      // Fallback if table schema differs
      try {
        db.prepare(
          `INSERT INTO music_web_actions (guild_id, action, payload_json, user_id, created_at)
           VALUES (?, ?, ?, ?, ?)`
        ).run(guildId, action, JSON.stringify(payload), userId, nowIso);
      } catch (err2) {
        console.warn("music_web_actions enqueue notice:", err2);
      }
    }

    // 2. Direct database session state update for instant UI feedback
    try {
      if (action === "PAUSE") {
        db.prepare("UPDATE music_sessions SET is_paused = 1, state = 'PAUSED' WHERE guild_id = ?").run(guildId);
      } else if (action === "RESUME") {
        db.prepare("UPDATE music_sessions SET is_paused = 0, state = 'PLAYING' WHERE guild_id = ?").run(guildId);
      } else if (action === "VOLUME") {
        const vol = Math.max(0, Math.min(150, Number(payload.volume ?? 80)));
        db.prepare("UPDATE music_sessions SET volume = ? WHERE guild_id = ?").run(vol, guildId);
        db.prepare("UPDATE music_guild_settings SET default_volume = ? WHERE guild_id = ?").run(vol, guildId);
      } else if (action === "247_TOGGLE") {
        const cur = db.prepare("SELECT twenty_four_seven_enabled FROM music_guild_settings WHERE guild_id = ?").get(guildId) as any;
        const nextState = cur ? (cur.twenty_four_seven_enabled ? 0 : 1) : 1;
        db.prepare(
          "INSERT INTO music_guild_settings (guild_id, twenty_four_seven_enabled) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET twenty_four_seven_enabled = excluded.twenty_four_seven_enabled"
        ).run(guildId, nextState);
      }
    } catch (dbErr) {
      console.warn("Direct session update notice:", dbErr);
    }

    return NextResponse.json({
      success: true,
      data: {
        action,
        status: "dispatched",
        guild_id: guildId,
      },
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
