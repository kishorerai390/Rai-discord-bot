import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const query = searchParams.get("q")?.trim() || "";

    if (!query) {
      return NextResponse.json({ success: true, data: [] });
    }

    // If query is a direct URL
    if (query.startsWith("http://") || query.startsWith("https://")) {
      return NextResponse.json({
        success: true,
        data: [
          {
            title: query,
            artist: "Direct Stream URL",
            url: query,
            duration: 0,
            duration_fmt: "Direct Link",
            thumbnail: "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=120",
            source: "direct",
          },
        ],
      });
    }

    // 1. Search iTunes API for rich metadata (fast, reliable, lossless cover arts, multi-lingual)
    try {
      const itunesUrl = `https://itunes.apple.com/search?term=${encodeURIComponent(
        query
      )}&entity=song&limit=8`;
      const res = await fetch(itunesUrl, { next: { revalidate: 60 } });

      if (res.ok) {
        const data = await res.json();
        if (data.results && data.results.length > 0) {
          const results = data.results.map((item: any) => {
            const durationSec = Math.round((item.trackTimeMillis || 0) / 1000);
            const mins = Math.floor(durationSec / 60);
            const secs = String(durationSec % 60).padStart(2, "0");
            return {
              title: item.trackName || "Unknown Track",
              artist: item.artistName || "Unknown Artist",
              url: `https://www.youtube.com/results?search_query=${encodeURIComponent(
                `${item.trackName} ${item.artistName} audio`
              )}`,
              duration: durationSec,
              duration_fmt: `${mins}:${secs}`,
              thumbnail:
                item.artworkUrl100?.replace("100x100bb", "300x300bb") ||
                "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=120",
              source: "engine",
            };
          });

          return NextResponse.json({ success: true, data: results });
        }
      }
    } catch (e) {
      console.warn("Search metadata fetch warning:", e);
    }

    // Fallback: Return structured candidate for YouTube playback
    return NextResponse.json({
      success: true,
      data: [
        {
          title: query,
          artist: "YouTube Audio Resolution",
          url: `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`,
          duration: 210,
          duration_fmt: "03:30",
          thumbnail: "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=120",
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
