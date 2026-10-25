import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";

export async function GET(req: NextRequest) {
  const user = await getCurrentUser(req);
  if (!user) {
    return NextResponse.json(
      { success: false, error: "Sign in with Discord to view your servers.", data: { guilds: [] } },
      { status: 401 }
    );
  }

  const botApiUrl = (process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
  if (!botApiUrl) {
    return NextResponse.json(
      { success: false, error: "Music bot API is not configured.", data: { guilds: [] } },
      { status: 503 }
    );
  }

  const headers = new Headers({ "Accept": "application/json" });
  const cookie = req.headers.get("cookie");
  const authorization = req.headers.get("authorization");
  if (cookie) headers.set("cookie", cookie);
  if (authorization) headers.set("authorization", authorization);

  try {
    const response = await fetch(`${botApiUrl}/api/music/guilds`, {
      headers,
      signal: AbortSignal.timeout(8000),
      cache: "no-store",
    });
    const result = await response.json().catch(() => null);
    if (!response.ok || !result || result.success !== true) {
      return NextResponse.json(
        { success: false, error: result?.error?.message || result?.error || "Bot API could not verify your servers.", data: { guilds: [] } },
        { status: response.ok ? 502 : response.status }
      );
    }
    return NextResponse.json(result, { status: 200 });
  } catch {
    return NextResponse.json(
      { success: false, error: "The live music bot API is unreachable.", data: { guilds: [] } },
      { status: 503 }
    );
  }
}
