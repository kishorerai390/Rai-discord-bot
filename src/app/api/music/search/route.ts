import { NextRequest, NextResponse } from "next/server";
import { DEFAULT_TRACK_ARTWORK } from "@/lib/utils";

function extractYouTubeId(urlOrText: string): string | null {
  const match = urlOrText.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/))([a-zA-Z0-9_-]{11})/);
  return match ? match[1] : null;
}

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const query = searchParams.get("q")?.trim() || "";

    if (!query) {
      return NextResponse.json({ success: true, data: [] });
    }

    // Attempt to proxy to the backend python bot API if reachable
    const botApiUrl = process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "https://rai-discord-bot.onrender.com";
    try {
      const resBot = await fetch(`${botApiUrl}/api/music/search?q=${encodeURIComponent(query)}`, {
        signal: AbortSignal.timeout(2500),
      });
      if (resBot.ok) {
        const botJson = await resBot.json();
        if (botJson.success && Array.isArray(botJson.data) && botJson.data.length > 0) {
          return NextResponse.json(botJson);
        }
      }
    } catch {
      // Backend bot is running in standalone mode or initializing; proceed to direct resolution
    }

    // Direct stream or YouTube URL
    const ytId = extractYouTubeId(query);
    if (ytId) {
      return NextResponse.json({
        success: true,
        data: [
          {
            id: `yt_${ytId}`,
            title: query,
            artist: "YouTube Audio",
            url: query,
            duration: 0,
            duration_fmt: "Direct Link",
            thumbnail: `https://i.ytimg.com/vi/${ytId}/hqdefault.jpg`,
            provider: "youtube",
            source: "youtube",
          },
        ],
      });
    }

    if (query.startsWith("http://") || query.startsWith("https://")) {
      return NextResponse.json({
        success: true,
        data: [
          {
            id: `stream_${Math.random().toString(36).slice(2, 9)}`,
            title: query,
            artist: "Direct Stream URL",
            url: query,
            duration: 0,
            duration_fmt: "Direct Link",
            thumbnail: DEFAULT_TRACK_ARTWORK,
            provider: "direct",
            source: "direct",
          },
        ],
      });
    }

    // Search iTunes API for rich metadata (fast, lossless cover arts, high reliability)
    try {
      const itunesUrl = `https://itunes.apple.com/search?term=${encodeURIComponent(
        query
      )}&entity=song&limit=10`;
      const res = await fetch(itunesUrl, { next: { revalidate: 60 } });

      if (res.ok) {
        const data = await res.json();
        if (data.results && data.results.length > 0) {
          const results = data.results.map((item: any, idx: number) => {
            const durationSec = Math.round((item.trackTimeMillis || 0) / 1000);
            const mins = Math.floor(durationSec / 60);
            const secs = String(durationSec % 60).padStart(2, "0");
            const art = item.artworkUrl100
              ? item.artworkUrl100.replace("100x100bb", "600x600bb")
              : DEFAULT_TRACK_ARTWORK;

            return {
              id: item.trackId ? `itunes_${item.trackId}` : `itunes_${idx}_${Math.random().toString(36).slice(2, 6)}`,
              title: item.trackName || "Unknown Track",
              artist: item.artistName || "Unknown Artist",
              url: `https://www.youtube.com/results?search_query=${encodeURIComponent(
                `${item.trackName} ${item.artistName} audio`
              )}`,
              duration: durationSec,
              duration_fmt: `${mins}:${secs}`,
              thumbnail: art,
              provider: "itunes",
              source: "engine",
            };
          });

          return NextResponse.json({ success: true, data: results });
        }
      }
    } catch (e) {
      console.warn("Search metadata fetch warning:", e);
    }

    // Fallback: Return clean structured query candidate without hardcoded placeholder images
    return NextResponse.json({
      success: true,
      data: [
        {
          id: `search_${Math.random().toString(36).slice(2, 9)}`,
          title: query,
          artist: "YouTube Audio Resolution",
          url: `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`,
          duration: 210,
          duration_fmt: "03:30",
          thumbnail: DEFAULT_TRACK_ARTWORK,
          provider: "youtube",
          source: "youtube",
        },
      ],
    });
  } catch (error: any) {
    return NextResponse.json(
      { success: false, error: error.message || "Failed to search tracks" },
      { status: 500 }
    );
  }
}
