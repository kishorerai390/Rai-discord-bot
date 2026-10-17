import { NextRequest, NextResponse } from "next/server";
import { getMusicDb, getActiveSession } from "@/lib/db";

export async function GET(req: NextRequest) {
  const guildId = req.nextUrl.searchParams.get("guild_id") || "1457382179981099090";

  try {
    const db = getMusicDb();
    const session = getActiveSession(guildId);
    const settings = db
      .prepare("SELECT * FROM music_guild_settings WHERE guild_id = ?")
      .get(guildId) as any;

    const queueCount = (
      db
        .prepare("SELECT COUNT(*) as count FROM music_queues WHERE guild_id = ?")
        .get(guildId) as any
    )?.count || 0;

    let currentTrack = null;
    if (session && session.track_title) {
      currentTrack = {
        title: session.track_title,
        url: session.track_url || "",
        author: session.track_author || "Unknown Artist",
        duration: session.duration || 0,
        thumbnail:
          session.track_thumbnail ||
          "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=120",
        requested_by: session.requested_by || "Discord User",
      };
    }

    const isPlaying = session?.state === "PLAYING";
    const isPaused = session?.state === "PAUSED";

    return NextResponse.json({
      success: true,
      data: {
        session: {
          guild_id: guildId,
          channel_id: session?.channel_id || null,
          channel_name: session?.channel_name || "Voice Room",
          is_playing: isPlaying,
          is_paused: isPaused,
          volume: session?.volume ?? (settings?.default_volume || 80),
          loop_mode: session?.loop_mode || "off",
          twenty_four_seven: Boolean(
            session?.twenty_four_seven ?? settings?.twenty_four_seven_enabled
          ),
          shuffle: Boolean(session?.shuffle || false),
          elapsed_seconds: session?.elapsed_seconds || 0,
          duration_seconds: session?.duration || 0,
          current_track: currentTrack,
          queue_length: queueCount,
          dj_enabled: Boolean(settings?.autodj_enabled || false),
          active_filter: session?.active_filter || "flat",
          state: session?.state || "IDLE",
        },
      },
    });
  } catch (err: any) {
    return NextResponse.json({
      success: false,
      error: err.message,
    });
  }
}
