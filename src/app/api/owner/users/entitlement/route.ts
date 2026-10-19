import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getMusicDb } from "@/lib/db";

export async function POST(req: NextRequest) {
  const user = await getCurrentUser(req);
  if (!user || !user.is_owner) {
    return NextResponse.json(
      { success: false, error: { code: "FORBIDDEN", message: "Bot Owner privileges required" } },
      { status: 403 }
    );
  }

  try {
    const body = await req.json();
    const userId = String(body.user_id || "").trim();
    const action = String(body.action || "").toLowerCase().trim();
    const tier = String(body.tier || "premium").toLowerCase().trim();
    const days = Math.max(1, Math.min(365, Number(body.days || 30)));
    const reason = String(body.reason || "").trim();

    if (!userId) {
      return NextResponse.json(
        { success: false, error: { code: "INVALID_USER_ID", message: "User ID is required" } },
        { status: 400 }
      );
    }
    if (!reason) {
      return NextResponse.json(
        { success: false, error: { code: "REASON_REQUIRED", message: "Reason is required for entitlement alterations" } },
        { status: 400 }
      );
    }

    const botApiUrl =
      process.env.DISCORD_BOT_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "https://rai-discord-bot.onrender.com";

    try {
      const cookieHeader = req.headers.get("cookie") || "";
      const resBot = await fetch(`${botApiUrl}/api/owner/users/entitlement`, {
        method: "POST",
        headers: { "Content-Type": "application/json", cookie: cookieHeader },
        body: JSON.stringify({
          user_id: userId,
          action,
          tier,
          days,
          reason,
        }),
        signal: AbortSignal.timeout(4000),
      });
      if (resBot.ok) {
        const data = await resBot.json();
        return NextResponse.json(data);
      }
    } catch {}

    const db = getMusicDb();
    const now = new Date();
    const expiresAt = new Date(now.getTime() + days * 24 * 60 * 60 * 1000).toISOString();

    if (action === "grant") {
      db.prepare(
        `INSERT INTO music_premium (entity_type, entity_id, is_premium, tier, expires_at, updated_at)
         VALUES ('user', ?, 1, ?, ?, ?)
         ON CONFLICT(entity_type, entity_id) DO UPDATE SET
           is_premium = 1,
           tier = excluded.tier,
           expires_at = excluded.expires_at,
           updated_at = excluded.updated_at`
      ).run(userId, tier, expiresAt, now.toISOString());

      return NextResponse.json({
        success: true,
        data: {
          user_id: userId,
          tier,
          status: "active",
          expires_at: expiresAt,
          message: `Successfully granted ${tier.toUpperCase()} for ${days} days.`,
        },
      });
    } else {
      db.prepare(
        `UPDATE music_premium SET is_premium = 0, tier = 'free', updated_at = ? WHERE entity_type = 'user' AND entity_id = ?`
      ).run(now.toISOString(), userId);

      return NextResponse.json({
        success: true,
        data: {
          user_id: userId,
          status: "revoked",
          message: "Entitlement revoked successfully.",
        },
      });
    }
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
