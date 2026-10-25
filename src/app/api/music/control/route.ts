import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";

export async function POST(req: NextRequest) {
  try {
    const user = await getCurrentUser(req);
    if (!user) {
      return NextResponse.json(
        { success: false, error: "Sign in with Discord before controlling music." },
        { status: 401 }
      );
    }

    const body = await req.json();
    const guildId = String(body.guild_id || "").trim();
    const action = String(body.action || "").toUpperCase().trim();
    const payload = body.payload && typeof body.payload === "object" ? body.payload : {};

    if (!/^\d{15,22}$/.test(guildId)) {
      return NextResponse.json({ success: false, error: "A valid server ID is required." }, { status: 400 });
    }
    if (!action) {
      return NextResponse.json({ success: false, error: "Action is required." }, { status: 400 });
    }

    const botApiUrl = (process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
    if (!botApiUrl) {
      return NextResponse.json(
        { success: false, error: "Music bot API is not configured. Set DISCORD_BOT_API_URL to the live bot API." },
        { status: 503 }
      );
    }

    // Forward the existing session so the bot API can perform its own authorization.
    const headers = new Headers({ "Content-Type": "application/json" });
    const cookie = req.headers.get("cookie");
    const authorization = req.headers.get("authorization");
    if (cookie) headers.set("cookie", cookie);
    if (authorization) headers.set("authorization", authorization);

    let resBot: Response;
    try {
      resBot = await fetch(`${botApiUrl}/api/music/control`, {
        method: "POST",
        headers,
        body: JSON.stringify({ guild_id: guildId, action, payload, user_id: user.id }),
        cache: "no-store",
        signal: AbortSignal.timeout(8000),
      });
    } catch {
      return NextResponse.json(
        { success: false, error: "The live music bot API is unreachable. No action was queued or faked." },
        { status: 503 }
      );
    }

    const result = await resBot.json().catch(() => null);
    if (!resBot.ok) {
      return NextResponse.json(
        { success: false, error: result?.error?.message || result?.error || `Music bot rejected the action (HTTP ${resBot.status}).` },
        { status: resBot.status }
      );
    }
    if (!result || result.success !== true) {
      return NextResponse.json(
        { success: false, error: result?.error?.message || result?.error || "Music bot did not confirm the action." },
        { status: 502 }
      );
    }

    return NextResponse.json(result, { status: 200 });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Failed to dispatch music action.";
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
