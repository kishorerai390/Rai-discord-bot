import { NextRequest, NextResponse } from "next/server";
import { getBotDb } from "@/lib/db";
import { getPublicBaseUrl, SESSION_COOKIE_NAMES } from "@/lib/auth";

/** Clear all session cookies (both Next.js and Python auth flow cookies). */
function clearSessionCookies(res: NextResponse): void {
  for (const name of SESSION_COOKIE_NAMES) {
    res.cookies.delete(name);
  }
}

export async function POST(req: NextRequest) {
  // Invalidate whichever session cookie is present
  for (const name of SESSION_COOKIE_NAMES) {
    const token = req.cookies.get(name)?.value;
    if (token) {
      try {
        const db = getBotDb();
        db.prepare("UPDATE web_sessions SET is_active = 0 WHERE session_id = ?").run(token);
      } catch {}
      break; // both cookies share the same session_id value
    }
  }

  const res = NextResponse.json({ success: true });
  clearSessionCookies(res);
  return res;
}

export async function GET(req: NextRequest) {
  const baseUrl = getPublicBaseUrl(req);
  for (const name of SESSION_COOKIE_NAMES) {
    const token = req.cookies.get(name)?.value;
    if (token) {
      try {
        const db = getBotDb();
        db.prepare("UPDATE web_sessions SET is_active = 0 WHERE session_id = ?").run(token);
      } catch {}
      break;
    }
  }

  const res = NextResponse.redirect(`${baseUrl}/`);
  clearSessionCookies(res);
  return res;
}
