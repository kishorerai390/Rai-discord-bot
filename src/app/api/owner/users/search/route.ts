import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getUserEntitlement } from "@/lib/db";

export async function GET(req: NextRequest) {
  const user = await getCurrentUser(req);
  if (!user || !user.is_owner) {
    return NextResponse.json(
      { success: false, error: { code: "FORBIDDEN", message: "Bot Owner privileges required" } },
      { status: 403 }
    );
  }

  const query = req.nextUrl.searchParams.get("user_id") || "";
  const cleanedId = query.replace(/[<@!>]/g, "").trim();

  if (!cleanedId) {
    return NextResponse.json(
      { success: false, error: { code: "INVALID_USER_ID", message: "User ID is required" } },
      { status: 400 }
    );
  }

  const botApiUrl =
    process.env.DISCORD_BOT_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://rai-discord-bot.onrender.com";

  try {
    const cookieHeader = req.headers.get("cookie") || "";
    const resBot = await fetch(
      `${botApiUrl}/api/owner/users/search?user_id=${encodeURIComponent(cleanedId)}`,
      {
        headers: { cookie: cookieHeader },
        signal: AbortSignal.timeout(3000),
      }
    );
    if (resBot.ok) {
      const data = await resBot.json();
      return NextResponse.json(data);
    }
  } catch {}

  const entitlements = getUserEntitlement(cleanedId);
  return NextResponse.json({
    success: true,
    data: {
      user_id: cleanedId,
      username: cleanedId === "1457380609641938981" ? "kishorerai" : `User#${cleanedId.slice(-4)}`,
      display_name: cleanedId === "1457380609641938981" ? "✦ ʀᴀɪ ʀᴀᴍ ✦" : `User ${cleanedId.slice(-4)}`,
      avatar_url: null,
      entitlements,
      subscription: {
        plan: entitlements.plan,
        status: entitlements.status,
        expires_at: entitlements.current_period_end,
      },
      audit_logs: [],
    },
  });
}
