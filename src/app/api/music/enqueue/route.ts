import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { submitWebAction } from "@/lib/db";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const guildId = String(body.guild_id || "1525030316845301781");
    const query = String(body.query || "").trim();

    if (!query) {
      return NextResponse.json(
        { success: false, error: "Search query or URL is required" },
        { status: 400 }
      );
    }

    const user = await getCurrentUser(req);
    const userId = user?.id || "1457382179981099090";

    const botApiUrl = process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "https://rai-discord-bot.onrender.com";
    try {
      const resBot = await fetch(`${botApiUrl}/api/music/enqueue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ guild_id: guildId, query, user_id: userId }),
        signal: AbortSignal.timeout(4000),
      });
      if (resBot.ok) {
        const botJson = await resBot.json();
        if (botJson.success) {
          return NextResponse.json(botJson);
        }
      }
    } catch {
      // Fallback to local SQLite action
    }

    const actionId = submitWebAction(guildId, "ENQUEUE", { query }, userId);

    return NextResponse.json({
      success: true,
      data: { action_id: actionId, status: "ENQUEUE_QUEUED" },
    });
  } catch (error: any) {
    return NextResponse.json(
      { success: false, error: error.message || "Failed to enqueue track" },
      { status: 500 }
    );
  }
}
