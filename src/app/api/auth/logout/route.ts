import { NextRequest, NextResponse } from "next/server";
import { getBotDb } from "@/lib/db";
import { getPublicBaseUrl } from "@/lib/auth";

export async function POST(req: NextRequest) {
  const token = req.cookies.get("session_id")?.value;
  if (token) {
    try {
      const db = getBotDb();
      db.prepare("UPDATE web_sessions SET is_active = 0 WHERE session_id = ?").run(token);
    } catch {}
  }

  const res = NextResponse.json({ success: true });
  res.cookies.delete("session_id");
  return res;
}

export async function GET(req: NextRequest) {
  const baseUrl = getPublicBaseUrl(req);
  const token = req.cookies.get("session_id")?.value;
  if (token) {
    try {
      const db = getBotDb();
      db.prepare("UPDATE web_sessions SET is_active = 0 WHERE session_id = ?").run(token);
    } catch {}
  }

  const res = NextResponse.redirect(`${baseUrl}/`);
  res.cookies.delete("session_id");
  return res;
}
