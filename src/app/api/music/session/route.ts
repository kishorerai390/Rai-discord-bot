import { NextRequest, NextResponse } from "next/server";
import { getMusicDb, getActiveSession } from "@/lib/db";
import { DEFAULT_TRACK_ARTWORK } from "@/lib/utils";

export async function GET(req: NextRequest) {
  const guildId = req.nextUrl.searchParams.get("guild_id") || "1457382179981099090";

  // Try fetching live state directly from backend Python bot if running
  const botApiUrl = process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "https://rai-discord-bot.onrender.com";
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

    let queueCount = 0;
    try {
      queueCount = (
        db
          .prepare("SELECT COUNT(*) as count FROM music_queues WHERE guild_id = ?")
          .get(guildId) as any
      )?.count || 0;
    } catch {
      queueCount = 0;
    }

    let currentTrack: any = null;
    if (session) {
      if (session.current_track_json) {
        try {
          const parsed = typeof session.current_track_json === "string" 
            ? JSON.parse(session.current_track_json) 
            : session.current_track_json;
          if (parsed && typeof parsed === "object") {
            currentTrack = {
              title: parsed.title || "Unknown Track",
              url: parsed.url || parsed.webpage_url || "",
              artist: parsed.artist || parsed.author || parsed.uploader || "Unknown Artist",
              author: parsed.author || parsed.artist || "Unknown Artist",
              duration: Number(parsed.duration || 0),
              thumbnail: parsed.thumbnail || DEFAULT_TRACK_ARTWORK,
              requested_by: parsed.requester_name || parsed.requested_by || "Discord User",
            };
          }
        } catch {
          // fallback to flat columns
        }
      }

      if (!currentTrack && (session.track_title || session.current_track_title)) {
        currentTrack = {
          title: session.track_title || session.current_track_title,
          url: session.track_url || session.current_track_url || "",
          artist: session.track_author || session.current_track_author || "Unknown Artist",
          author: session.track_author || session.current_track_author || "Unknown Artist",
          duration: Number(session.duration || session.current_track_duration || 0),
          thumbnail: session.track_thumbnail || session.current_track_thumbnail || DEFAULT_TRACK_ARTWORK,
          requested_by: session.requested_by || "Discord User",
        };
      }
    }

    const state = String(session?.state || "IDLE").toUpperCase();
    const isPlaying = state === "PLAYING";
    const isPaused = Boolean(session?.is_paused) || state === "PAUSED";
    const voiceChannelId = session?.voice_channel_id || session?.channel_id;
    const isVoiceConnected = Boolean(voiceChannelId);
    const channelName = session?.voice_channel_name || session?.channel_name || (isVoiceConnected ? "Voice Channel" : null);

    const positionSeconds = Number(
      session?.position_seconds ?? session?.elapsed_seconds ?? 0
    );
    const durationSeconds = currentTrack?.duration || Number(session?.duration || 0);

    return NextResponse.json({
      success: true,
      data: {
        session: {
          guild_id: guildId,
          channel_id: voiceChannelId ? String(voiceChannelId) : null,
          channel_name: channelName,
          voice_channel_name: channelName,
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
          elapsed_seconds: positionSeconds,
          position_seconds: positionSeconds,
          duration_seconds: durationSeconds,
          current_track: currentTrack,
          queue_length: queueCount,
          dj_enabled: Boolean(settings?.autodj_enabled || false),
          active_filter: session?.active_filter || "flat",
          state: state,
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
