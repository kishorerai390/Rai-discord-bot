import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";

export async function GET(req: NextRequest) {
  const user = await getCurrentUser(req);
  if (!user || !user.is_owner) {
    return NextResponse.json(
      { success: false, error: { code: "FORBIDDEN", message: "Bot Owner privileges required" } },
      { status: 403 }
    );
  }

  const botApiUrl =
    process.env.DISCORD_BOT_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://rai-discord-bot.onrender.com";

  try {
    const cookieHeader = req.headers.get("cookie") || "";
    const resBot = await fetch(`${botApiUrl}/api/owner/incidents`, {
      headers: { cookie: cookieHeader },
      signal: AbortSignal.timeout(3000),
    });
    if (resBot.ok) {
      const data = await resBot.json();
      return NextResponse.json(data);
    }
  } catch {}

  return NextResponse.json({
    success: true,
    data: {
      total: 0,
      incidents: [],
    },
  });
}

export async function POST(req: NextRequest) {
  const user = await getCurrentUser(req);
  if (!user || !user.is_owner) {
    return NextResponse.json(
      { success: false, error: { code: "FORBIDDEN", message: "Bot Owner privileges required" } },
      { status: 403 }
    );
  }

  try {
    const body = await req.json();
    const botApiUrl =
      process.env.DISCORD_BOT_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "https://rai-discord-bot.onrender.com";

    const cookieHeader = req.headers.get("cookie") || "";
    const resBot = await fetch(`${botApiUrl}/api/owner/incidents/acknowledge`, {
      method: "POST",
      headers: { "Content-Type": "application/json", cookie: cookieHeader },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(3000),
    });
    if (resBot.ok) {
      const data = await resBot.json();
      return NextResponse.json(data);
    }
  } catch {}

  return NextResponse.json({ success: true, data: { acknowledged: true } });
}
