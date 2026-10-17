import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getPlaylists, getMusicDb } from "@/lib/db";

export async function GET(req: NextRequest) {
  const guildId = req.nextUrl.searchParams.get("guild_id") || undefined;
  const user = await getCurrentUser(req);
  const userId = user?.id;

  const rows = getPlaylists(guildId, userId);
  const playlists = rows.map((r) => ({
    id: String(r.id),
    name: r.name,
    guild_id: String(r.guild_id || ""),
    user_id: String(r.user_id || ""),
    track_count: r.track_count || 0,
    created_at: r.created_at,
  }));

  return NextResponse.json({
    success: true,
    data: { playlists },
  });
}
