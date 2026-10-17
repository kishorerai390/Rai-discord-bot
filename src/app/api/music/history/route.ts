import { NextRequest, NextResponse } from "next/server";
import { getMusicDb } from "@/lib/db";

export async function GET(req: NextRequest) {
  const guildId = req.nextUrl.searchParams.get("guild_id") || "1457382179981099090";

  try {
    const db = getMusicDb();
    const rows = db
      .prepare(
        "SELECT * FROM music_history WHERE guild_id = ? ORDER BY played_at DESC LIMIT 30"
      )
      .all(guildId) as any[];

    const history = rows.map((r) => ({
      id: String(r.id),
      title: r.title,
      url: r.url,
      author: r.author || "Unknown",
      duration: r.duration || 0,
      played_at: r.played_at,
    }));

    return NextResponse.json({
      success: true,
      data: { history },
    });
  } catch (err: any) {
    return NextResponse.json({
      success: true,
      data: { history: [] },
    });
  }
}
