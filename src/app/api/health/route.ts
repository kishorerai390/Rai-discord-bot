import { NextResponse } from "next/server";

export async function GET() {
  const commit = process.env.RENDER_GIT_COMMIT || "nextjs-ts";
  return NextResponse.json({
    status: "healthy",
    bot_name: "MusicMaid",
    platform: "Next.js 15 TypeScript Platform",
    timestamp: Math.floor(Date.now() / 1000),
    commit: commit.slice(0, 8),
    git_commit: commit,
    architecture: {
      frontend: "Next.js 15 App Router (React 19, TypeScript, Tailwind CSS)",
      backend: "Next.js Server Route Handlers",
      database: "SQLite 3 WAL (data/music.db & data/bot.db)",
      payments: "Razorpay & Student Demo Mode",
    },
    voice_engine: {
      status: "online",
      bitrate: "320kbps Lossless Opus",
      dave_e2ee: true,
      ready: true,
    },
  });
}
