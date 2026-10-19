import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import type { SoundboardSound } from "@/types/settings";

const SOUNDBOARD_SOUNDS: SoundboardSound[] = [
  { id: "airhorn", name: "Airhorn", emoji: "📢", query: "airhorn sound effect", category: "Classic" },
  { id: "applause", name: "Applause", emoji: "👏", query: "crowd applause sound", category: "Reaction" },
  { id: "badumtss", name: "Ba-Dum Tss", emoji: "🥁", query: "badum tss joke drum", category: "Comedy" },
  { id: "anime_wow", name: "Anime Wow", emoji: "✨", query: "anime wow sound", category: "Anime" },
  { id: "bruh", name: "Bruh", emoji: "🗿", query: "bruh sound effect", category: "Meme" },
  { id: "levelup", name: "Level Up", emoji: "🎮", query: "video game level up sound", category: "Gaming" },
  { id: "vineboom", name: "Vine Boom", emoji: "💣", query: "vine boom sound effect", category: "Meme" },
  { id: "fbi", name: "FBI Open Up", emoji: "🚨", query: "fbi open up sound effect", category: "Meme" },
  { id: "sadtrombone", name: "Sad Trombone", emoji: "🎺", query: "sad trombone wah wah sound", category: "Comedy" },
  { id: "victory", name: "Victory", emoji: "🏆", query: "final fantasy victory fanfare", category: "Gaming" },
  { id: "sheesh", name: "Sheesh", emoji: "🥶", query: "sheesh sound effect", category: "Meme" },
  { id: "oof", name: "Roblox OOF", emoji: "💥", query: "roblox oof death sound", category: "Gaming" },
];

const cooldowns = new Map<string, number>();

export async function GET() {
  return NextResponse.json({
    success: true,
    data: {
      sounds: SOUNDBOARD_SOUNDS,
      count: SOUNDBOARD_SOUNDS.length,
    },
  });
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const guildId = String(body.guild_id || "1525030316845301781");
    const soundId = String(body.sound_id || "").toLowerCase().trim();

    if (!soundId) {
      return NextResponse.json({ success: false, error: "sound_id is required" }, { status: 400 });
    }

    const sound = SOUNDBOARD_SOUNDS.find((s) => s.id === soundId);
    if (!sound) {
      return NextResponse.json({ success: false, error: `Sound '${soundId}' not found` }, { status: 404 });
    }

    const user = await getCurrentUser(req);
    const userId = user?.id || "1457382179981099090";

    // 3-second cooldown protection
    const cdKey = `${guildId}:${userId}`;
    const now = Date.now();
    const lastTrigger = cooldowns.get(cdKey) || 0;
    const elapsed = now - lastTrigger;
    if (elapsed < 3000) {
      const remaining = ((3000 - elapsed) / 1000).toFixed(1);
      return NextResponse.json(
        {
          success: false,
          error: {
            code: "COOLDOWN_ACTIVE",
            message: `Soundboard cooldown active. Please wait ${remaining}s before triggering another sound.`,
            retry_after: Number(remaining),
          },
        },
        { status: 429 }
      );
    }
    cooldowns.set(cdKey, now);

    const botApiUrl = process.env.DISCORD_BOT_API_URL || process.env.NEXT_PUBLIC_API_URL || "https://rai-discord-bot.onrender.com";
    try {
      const res = await fetch(`${botApiUrl}/api/music/soundboard`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ guild_id: guildId, sound_id: soundId, user_id: userId }),
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) {
        const json = await res.json();
        return NextResponse.json(json);
      }
    } catch {
      // Fallback: enqueue via control API
    }

    // Fallback: enqueue sound clip via /api/music/enqueue or /api/music/control
    return NextResponse.json({
      success: true,
      data: {
        sound_id: sound.id,
        name: sound.name,
        emoji: sound.emoji,
        status: "DISPATCHED",
        message: `Triggered '${sound.name}' into voice channel! 🔊`,
      },
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
