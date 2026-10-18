import { NextRequest, NextResponse } from "next/server";
import { getMusicDb, getActiveSession } from "@/lib/db";
import { DEFAULT_TRACK_ARTWORK } from "@/lib/utils";

export async function GET(req: NextRequest) {
  const guildId = req.nextUrl.searchParams.get("guild_id") || "1457382179981099090";

  // Try fetching live state directly from backend Python bot if running
  const botApiUrl = process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  try {
    const resBot = await fetch(`${botApiUrl}/api/music/session?guild_id=${encodeURIComponent(guildId)}`, {
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
    // Bot is offline/reconnecting or Next.js standalone mode; fallback to SQLite session
  }

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
        artist: session.track_author || "Unknown Artist",
        author: session.track_author || "Unknown Artist",
        duration: session.duration || 0,
        thumbnail: session.track_thumbnail || DEFAULT_TRACK_ARTWORK,
        requested_by: session.requested_by || "Discord User",
      };
    }

    const isPlaying = session?.state === "PLAYING";
    const isPaused = session?.state === "PAUSED";
    const isVoiceConnected = Boolean(session?.channel_id);

    return NextResponse.json({
      success: true,
      data: {
        session: {
          guild_id: guildId,
          channel_id: session?.channel_id || null,
          channel_name: session?.channel_name || null,
          voice_channel_name: session?.channel_name || null,
          voice_status: isVoiceConnected ? "Connected" : "Disconnected",
          is_voice_connected: isVoiceConnected,
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
          state: session?.state || (isVoiceConnected ? "IDLE" : "DISCONNECTED"),
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
