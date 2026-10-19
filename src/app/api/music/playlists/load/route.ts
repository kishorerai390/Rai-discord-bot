import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getMusicDb, submitWebAction } from "@/lib/db";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const guildId = String(body.guild_id || "1525030316845301781");
    const name = body.name ? String(body.name).trim() : "";
    const playlistId = body.playlist_id || body.id;

    if (!name && !playlistId) {
      return NextResponse.json(
        { success: false, error: "Playlist name or playlist_id is required" },
        { status: 400 }
      );
    }

    const user = await getCurrentUser(req);
    const userId = user?.id || "1457382179981099090";

    // 1. Try bot API first
    const botApiUrl =
      process.env.DISCORD_BOT_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "https://rai-discord-bot.onrender.com";

    try {
      const resBot = await fetch(`${botApiUrl}/api/music/playlists/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          guild_id: guildId,
          name: name || undefined,
          playlist_id: playlistId || undefined,
          user_id: userId,
        }),
        signal: AbortSignal.timeout(4000),
      });
      if (resBot.ok) {
        const botJson = await resBot.json();
        if (botJson.success) {
          return NextResponse.json(botJson);
        }
      }
    } catch {
      // Fallback to local DB queue injection
    }

    const db = getMusicDb();
    let playlist: any = null;

    if (playlistId) {
      playlist = db
        .prepare("SELECT * FROM music_playlists WHERE id = ?")
        .get(playlistId);
    } else if (name) {
      playlist = db
        .prepare(
          "SELECT * FROM music_playlists WHERE name = ? AND (guild_id = ? OR user_id = ?)"
        )
        .get(name, guildId, userId);
    }

    if (!playlist) {
      return NextResponse.json(
        { success: false, error: "Playlist not found" },
        { status: 404 }
      );
    }

    // Fetch tracks
    let tracks: any[] = [];
    try {
      const rows = db
        .prepare(
          "SELECT * FROM music_playlist_tracks WHERE playlist_id = ? ORDER BY position ASC"
        )
        .all(playlist.id) as any[];
      if (rows && rows.length > 0) {
        tracks = rows;
      } else if (playlist.tracks_json) {
        tracks = JSON.parse(playlist.tracks_json);
      }
    } catch {
      tracks = [];
    }

    if (!Array.isArray(tracks) || tracks.length === 0) {
      return NextResponse.json(
        { success: false, error: "Playlist has no tracks to load" },
        { status: 400 }
      );
    }

    // Insert tracks into music_queues or submit web action
    let loadedCount = 0;
    const nowIso = new Date().toISOString();
    for (const [idx, t] of tracks.entries()) {
      try {
        db.prepare(
          `INSERT INTO music_queues (guild_id, track_index, position, title, url, author, artist, duration, thumbnail, requester_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
        ).run(
          guildId,
          idx,
          idx,
          t.title || "Track",
          t.url || "",
          t.author || t.artist || "Unknown",
          t.artist || t.author || "Unknown",
          t.duration || 0,
          t.thumbnail || null,
          user?.username || "Web User",
          nowIso
        );
        loadedCount++;
      } catch (err) {
        console.warn("Queue track insertion notice:", err);
      }
    }

    submitWebAction(guildId, "PLAYLIST_LOAD", { name: playlist.name, count: loadedCount }, userId);

    return NextResponse.json({
      success: true,
      data: {
        name: playlist.name,
        tracks_loaded: loadedCount,
        guild_id: guildId,
      },
    });
  } catch (err: any) {
    return NextResponse.json(
      { success: false, error: err.message },
      { status: 500 }
    );
  }
}
