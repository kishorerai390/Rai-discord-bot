import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";
import {
  DISCORD_CLIENT_ID,
  DISCORD_CLIENT_SECRET,
  getPublicBaseUrl,
} from "@/lib/auth";
import { getBotDb } from "@/lib/db";

export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get("code");
  const baseUrl = getPublicBaseUrl(req);
  const redirectUri = `${baseUrl}/api/auth/callback`;

  if (!code) {
    return NextResponse.redirect(`${baseUrl}/?auth_error=missing_code`);
  }

  try {
    // 1. Exchange code for access token
    const tokenRes = await fetch("https://discord.com/api/oauth2/token", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        client_id: DISCORD_CLIENT_ID,
        client_secret: DISCORD_CLIENT_SECRET,
        grant_type: "authorization_code",
        code,
        redirect_uri: redirectUri,
      }),
    });

    if (!tokenRes.ok) {
      const errText = await tokenRes.text();
      console.error("Discord token exchange error:", errText);
      return NextResponse.redirect(`${baseUrl}/?auth_error=token_exchange_failed`);
    }

    const tokenData = await tokenRes.json();
    const accessToken = tokenData.access_token;
    const refreshToken = tokenData.refresh_token || "";
    const expiresIn = tokenData.expires_in || 604800;

    // 2. Fetch User Profile
    const userRes = await fetch("https://discord.com/api/users/@me", {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!userRes.ok) {
      return NextResponse.redirect(`${baseUrl}/?auth_error=profile_fetch_failed`);
    }

    const discordUser = await userRes.json();
    const userId = discordUser.id;
    const username = discordUser.username;
    const discriminator = discordUser.discriminator || "0";
    const avatar = discordUser.avatar;

    // 3. Create Session in SQLite web_sessions
    const sessionId = crypto.randomBytes(32).toString("base64url");
    const expiresAt = new Date(Date.now() + expiresIn * 1000).toISOString();
    const nowIso = new Date().toISOString();

    const db = getBotDb();
    try {
      db.prepare(
        `INSERT INTO web_sessions (session_id, user_id, discord_user_id, username, discriminator, avatar, access_token, refresh_token, expires_at, created_at, is_active)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
         ON CONFLICT(session_id) DO UPDATE SET
           access_token = excluded.access_token,
           refresh_token = excluded.refresh_token,
           expires_at = excluded.expires_at,
           is_active = 1`
      ).run(
        sessionId,
        userId,
        userId,
        username,
        discriminator,
        avatar,
        accessToken,
        refreshToken,
        expiresAt,
        nowIso
      );
    } catch (dbErr) {
      console.error("Discord OAuth session persistence failed:", dbErr);
      return NextResponse.redirect(`${baseUrl}/?auth_error=session_store_failed`);
    }

    // 4. Redirect with Cookie — set BOTH cookie names so both auth systems accept the session:
    // - "session_id" is read by Next.js API routes (src/lib/auth.ts)
    // - "rai_session" is read by Python backend routes (/api/realtime/ws, /api/owner/*, etc.)
    const res = NextResponse.redirect(`${baseUrl}/?auth_success=1`);
    const cookieOpts = {
      httpOnly: true,
      secure: baseUrl.startsWith("https"),
      sameSite: "lax" as const,
      maxAge: expiresIn,
      path: "/",
    };
    res.cookies.set("session_id", sessionId, cookieOpts);
    res.cookies.set("rai_session", sessionId, cookieOpts);

    return res;
  } catch (err: any) {
    console.error("OAuth callback error:", err);
    return NextResponse.redirect(`${baseUrl}/?auth_error=${encodeURIComponent(err.message)}`);
  }
}
