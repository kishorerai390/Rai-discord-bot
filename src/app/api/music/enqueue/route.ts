import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";

export async function POST(req: NextRequest) {
  try {
    const user = await getCurrentUser(req);
    if (!user) {
      return NextResponse.json(
        { success: false, error: "Sign in with Discord before adding music." },
        { status: 401 }
      );
    }

    const body = await req.json();
    const guildId = String(body.guild_id || "").trim();
    const query = String(body.query || "").trim();

    if (!/^\d{15,22}$/.test(guildId)) {
      return NextResponse.json({ success: false, error: "A valid server ID is required." }, { status: 400 });
    }
    if (!query) {
      return NextResponse.json({ success: false, error: "Search query or URL is required." }, { status: 400 });
    }
    if (query.length > 500) {
      return NextResponse.json({ success: false, error: "Search query is too long." }, { status: 400 });
    }

    const botApiUrl = (process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
    if (!botApiUrl) {
      return NextResponse.json(
        { success: false, error: "Music bot API is not configured. Set DISCORD_BOT_API_URL to the live bot API." },
        { status: 503 }
      );
    }

    const headers = new Headers({ "Content-Type": "application/json" });
    const cookie = req.headers.get("cookie");
    const authorization = req.headers.get("authorization");
    if (cookie) headers.set("cookie", cookie);
    if (authorization) headers.set("authorization", authorization);

    let resBot: Response;
    try {
      resBot = await fetch(`${botApiUrl}/api/music/enqueue`, {
        method: "POST",
        headers,
        body: JSON.stringify({ guild_id: guildId, query, user_id: user.id }),
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
    } catch {
      return NextResponse.json(
        { success: false, error: "The live music bot API is unreachable. Track was not reported as queued." },
        { status: 503 }
      );
    }

    const result = await resBot.json().catch(() => null);
    if (!resBot.ok) {
      return NextResponse.json(
        { success: false, error: result?.error?.message || result?.error || `Music bot rejected the request (HTTP ${resBot.status}).` },
        { status: resBot.status }
      );
    }
    if (!result || result.success !== true) {
      return NextResponse.json(
        { success: false, error: result?.error?.message || result?.error || "Music bot did not confirm the track was queued." },
        { status: 502 }
      );
    }

    return NextResponse.json(result, { status: 200 });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Failed to enqueue track.";
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
