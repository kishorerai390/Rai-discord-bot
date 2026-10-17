import { NextRequest, NextResponse } from "next/server";
import { getPublicBaseUrl, getDiscordAuthUrl } from "@/lib/auth";

export async function GET(req: NextRequest) {
  const baseUrl = getPublicBaseUrl(req);
  const authUrl = getDiscordAuthUrl(baseUrl);
  return NextResponse.redirect(authUrl);
}
