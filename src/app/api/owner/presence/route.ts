import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import fs from "fs";
import path from "path";

const PRESENCE_FILE = path.join(process.cwd(), "data", "bot_presence.json");

const ALLOWED_SIGNATURE_SYMBOLS = [
  "vr_headset",
  "music_note",
  "soundwave",
  "radio",
  "vinyl",
  "energy_core",
] as const;

type SignatureSymbol = typeof ALLOWED_SIGNATURE_SYMBOLS[number];

interface BotPresence {
  mode: "dynamic" | "manual";
  status: "online" | "idle" | "dnd" | "invisible";
  activity_type: "listening" | "playing" | "watching" | "competing" | "custom";
  activity_text: string;
  idle_text: string;
  signature_symbol?: SignatureSymbol;
  updated_at?: string;
}

const DEFAULT_PRESENCE: BotPresence = {
  mode: "dynamic",
  status: "online",
  activity_type: "listening",
  activity_text: "Rem 🎧💜 | /play",
  idle_text: "24/7 high-fidelity lossless music player.",
  signature_symbol: "vr_headset",
};

function readPresence(): BotPresence {
  try {
    if (fs.existsSync(PRESENCE_FILE)) {
      const data = JSON.parse(fs.readFileSync(PRESENCE_FILE, "utf-8"));
      return { ...DEFAULT_PRESENCE, ...data };
    }
  } catch {}
  return { ...DEFAULT_PRESENCE };
}

function writePresence(data: BotPresence) {
  try {
    fs.mkdirSync(path.dirname(PRESENCE_FILE), { recursive: true });
    fs.writeFileSync(PRESENCE_FILE, JSON.stringify(data, null, 2), "utf-8");
  } catch (e) {
    console.warn("Failed to write presence file:", e);
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
    const resBot = await fetch(`${botApiUrl}/api/owner/presence`, {
      headers: { cookie: cookieHeader },
      signal: AbortSignal.timeout(3000),
    });
    if (resBot.ok) {
      const data = await resBot.json();
      return NextResponse.json(data);
    }
  } catch {}

  const current = readPresence();
  return NextResponse.json({
    success: true,
    data: {
      presence: current,
      mode: current.mode,
      status: current.status,
      configured_status: current.status,
      gateway_connected: false,
      discord_presence: current.status,
      voice_connected: false,
      playback_state: "unavailable",
      live_status: current.status,
      live_activity: current.activity_text,
      signature_symbol: current.signature_symbol || "vr_headset",
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

    try {
      const cookieHeader = req.headers.get("cookie") || "";
      const resBot = await fetch(`${botApiUrl}/api/owner/presence`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          cookie: cookieHeader,
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(3000),
      });
      if (resBot.ok) {
        const botData = await resBot.json();
        if (botData.success) {
          writePresence({ ...readPresence(), ...body, updated_at: new Date().toISOString() });
          return NextResponse.json(botData);
        }
      }
    } catch {}

    const updated: BotPresence = {
      mode: body.mode === "manual" ? "manual" : "dynamic",
      status: ["online", "idle", "dnd", "invisible"].includes(body.status) ? body.status : "online",
      activity_type: body.activity_type || "listening",
      activity_text: String(body.activity_text || ""),
      idle_text: String(body.idle_text || "24/7 lossless audio player."),
      signature_symbol: ALLOWED_SIGNATURE_SYMBOLS.includes(body.signature_symbol)
        ? body.signature_symbol
        : readPresence().signature_symbol || "vr_headset",
      updated_at: new Date().toISOString(),
    };

    writePresence(updated);

    return NextResponse.json({
      success: true,
      data: {
        message: "Bot presence updated successfully",
        presence: updated,
      },
    });
  } catch (err: any) {
    return NextResponse.json(
      { success: false, error: { message: err.message || "Failed to update presence" } },
      { status: 500 }
    );
  }
}
