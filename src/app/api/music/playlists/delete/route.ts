import { NextRequest, NextResponse } from "next/server";
import { getMusicDb } from "@/lib/db";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const playlistId = body.id || body.playlist_id;
    if (!playlistId) {
      return NextResponse.json({ success: false, error: "Playlist id is required" }, { status: 400 });
    }

    const db = getMusicDb();
    db.prepare("DELETE FROM music_playlist_tracks WHERE playlist_id = ?").run(playlistId);
    db.prepare("DELETE FROM music_playlists WHERE id = ?").run(playlistId);

    return NextResponse.json({ success: true, data: { deleted: true } });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
