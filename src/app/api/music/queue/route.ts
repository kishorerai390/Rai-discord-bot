import { NextRequest, NextResponse } from "next/server";
import { getQueue } from "@/lib/db";

export async function GET(req: NextRequest) {
  const guildId = req.nextUrl.searchParams.get("guild_id") || "1457382179981099090";

  try {
    const rows = getQueue(guildId);
    const queue = rows.map((r) => ({
      id: String(r.id),
      title: r.title,
      url: r.url,
      author: r.author || "Unknown Artist",
      duration: r.duration || 0,
      thumbnail: r.thumbnail || "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=120",
      requested_by: r.requested_by || "User",
      position: r.position,
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
