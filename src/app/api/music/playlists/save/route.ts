import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getMusicDb, getQueue } from "@/lib/db";

export async function POST(req: NextRequest) {
  const user = await getCurrentUser(req);
  const userId = user?.id || "1457382179981099090";

  try {
    const body = await req.json();
    const name = String(body.name || "").trim();
    const guildId = String(body.guild_id || "1457382179981099090");

    if (!name) {
      return NextResponse.json({ success: false, error: "Playlist name is required" }, { status: 400 });
    }

    const db = getMusicDb();
    const queue = getQueue(guildId);
    const nowIso = new Date().toISOString();

    const info = db
      .prepare(
        "INSERT INTO music_playlists (name, guild_id, user_id, track_count, created_at) VALUES (?, ?, ?, ?, ?)"
      )
      .run(name, guildId, userId, queue.length, nowIso);

    const playlistId = info.lastInsertRowid;

    // Snapshot tracks
    for (const [idx, track] of queue.entries()) {
      try {
        db.prepare(
          "INSERT INTO music_playlist_tracks (playlist_id, title, url, author, duration, position) VALUES (?, ?, ?, ?, ?, ?)"
        ).run(playlistId, track.title, track.url, track.author || "", track.duration || 0, idx);
      } catch {}
    }

    return NextResponse.json({
      success: true,
      data: {
        id: String(playlistId),
        name,
        track_count: queue.length,
      },
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
