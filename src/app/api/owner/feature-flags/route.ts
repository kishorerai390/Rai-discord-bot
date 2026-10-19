import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import fs from "fs";
import path from "path";

const FLAGS_FILE = path.join(process.cwd(), "data", "feature_flags.json");

const DEFAULT_FLAGS: Record<string, { enabled: boolean; label: string; category: string }> = {
  smart_autodj: { enabled: true, label: "Smart Auto-DJ Queue Flow", category: "audio" },
  lossless_dsp: { enabled: true, label: "320kbps Lossless DSP Engine", category: "audio" },
  canvas_visualizer: { enabled: true, label: "Holographic Audio Canvas", category: "ui" },
  instant_tickets: { enabled: true, label: "Ephemeral Support Tickets", category: "community" },
  emergency_safe_mode: { enabled: false, label: "Emergency Safe Mode (Pause Cluster)", category: "system" },
};

function readFlags() {
  try {
    if (fs.existsSync(FLAGS_FILE)) {
      const saved = JSON.parse(fs.readFileSync(FLAGS_FILE, "utf-8"));
      return { ...DEFAULT_FLAGS, ...saved };
    }
  } catch {}
  return { ...DEFAULT_FLAGS };
}

function writeFlags(flags: any) {
  try {
    fs.mkdirSync(path.dirname(FLAGS_FILE), { recursive: true });
    fs.writeFileSync(FLAGS_FILE, JSON.stringify(flags, null, 2), "utf-8");
  } catch (e) {
    console.warn("Failed to write feature flags file:", e);
  }
}

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
    const resBot = await fetch(`${botApiUrl}/api/owner/feature-flags`, {
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
    data: { flags: readFlags() },
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
    const flagKey = String(body.flag || "").trim();
    const enabled = Boolean(body.enabled);

    const botApiUrl =
      process.env.DISCORD_BOT_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "https://rai-discord-bot.onrender.com";

    try {
      const cookieHeader = req.headers.get("cookie") || "";
      const resBot = await fetch(`${botApiUrl}/api/owner/feature-flags`, {
        method: "POST",
        headers: { "Content-Type": "application/json", cookie: cookieHeader },
        body: JSON.stringify({ flag: flagKey, enabled }),
        signal: AbortSignal.timeout(3000),
      });
      if (resBot.ok) {
        const data = await resBot.json();
        return NextResponse.json(data);
      }
    } catch {}

    const flags = readFlags();
    if (flags[flagKey]) {
      flags[flagKey].enabled = enabled;
      writeFlags(flags);
    }

    return NextResponse.json({
      success: true,
      data: { flag: flagKey, enabled, flags },
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
