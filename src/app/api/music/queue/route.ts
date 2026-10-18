import { NextRequest, NextResponse } from "next/server";
import { getQueue } from "@/lib/db";
import { DEFAULT_TRACK_ARTWORK } from "@/lib/utils";

export async function GET(req: NextRequest) {
  const guildId = req.nextUrl.searchParams.get("guild_id") || "1457382179981099090";

  // Try fetching live queue from backend Python bot if running
  const botApiUrl = process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  try {
    const resBot = await fetch(`${botApiUrl}/api/music/queue?guild_id=${encodeURIComponent(guildId)}`, {
      signal: AbortSignal.timeout(2000),
      cache: "no-store",
    });
    if (resBot.ok) {
      const botJson = await resBot.json();
      if (botJson.success && botJson.data) {
        return NextResponse.json(botJson);
      }
    }
  } catch {
    // Fallback to SQLite queue
  }

  try {
    const rows = getQueue(guildId);
    const queue = rows.map((r, idx) => ({
      id: String(r.id || idx),
      title: r.title || "Unknown Track",
      url: r.url || "",
      author: r.artist || r.author || "Unknown Artist",
      artist: r.artist || r.author || "Unknown Artist",
      duration: Number(r.duration || 0),
      thumbnail: r.thumbnail || DEFAULT_TRACK_ARTWORK,
      requested_by: r.requester_name || r.requested_by || "Discord User",
      requester_name: r.requester_name || r.requested_by || "Discord User",
      position: r.track_index ?? r.position ?? idx,
    }));

    return NextResponse.json({
      success: true,
      data: {
        queue,
        total: queue.length,
      },
    });
  } catch (err: any) {
    return NextResponse.json({
      success: false,
      error: err.message,
      data: { queue: [] },
    });
  }
}
