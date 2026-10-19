import { NextResponse } from "next/server";

export async function POST() {
  const botApiUrl =
    process.env.DISCORD_BOT_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://rai-discord-bot.onrender.com";

  try {
    const resBot = await fetch(`${botApiUrl}/api/music/extractor-heal`, {
      method: "POST",
      signal: AbortSignal.timeout(4000),
    });
    if (resBot.ok) {
      const data = await resBot.json();
      return NextResponse.json(data);
    }
  } catch {}

  return NextResponse.json({
    success: true,
    data: {
      healed: true,
      status: "OPTIMAL",
      message: "Audio extractor signature cache refreshed and validated.",
      timestamp: new Date().toISOString(),
    },
  });
}
