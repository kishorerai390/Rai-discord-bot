import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getMusicDb } from "@/lib/db";

export async function POST(req: NextRequest) {
  const user = await getCurrentUser(req);
  if (!user) {
    return NextResponse.json({
      success: false,
      error: "Authentication required to manage favorites",
    }, { status: 401 });
  }

  try {
    const body = await req.json();
    const { url, title, author, duration } = body;
    if (!url || !title) {
      return NextResponse.json({ success: false, error: "Missing track metadata" }, { status: 400 });
    }

    const db = getMusicDb();
    const existing = db
      .prepare("SELECT id FROM music_favorites WHERE user_id = ? AND url = ?")
      .get(user.id, url);

    if (existing) {
      db.prepare("DELETE FROM music_favorites WHERE user_id = ? AND url = ?").run(user.id, url);
      return NextResponse.json({ success: true, data: { action: "removed", favorited: false } });
    } else {
      const now = new Date().toISOString();
      db.prepare(
        "INSERT INTO music_favorites (user_id, title, url, author, duration, added_at) VALUES (?, ?, ?, ?, ?, ?)"
      ).run(user.id, title, url, author || "Unknown", duration || 0, now);
      return NextResponse.json({ success: true, data: { action: "added", favorited: true } });
    }
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
