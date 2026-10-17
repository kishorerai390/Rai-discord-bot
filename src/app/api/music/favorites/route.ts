import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getFavorites } from "@/lib/db";

export async function GET(req: NextRequest) {
  const user = await getCurrentUser(req);
  if (!user) {
    return NextResponse.json({
      success: true,
      data: { favorites: [] },
    });
  }

  const favorites = getFavorites(user.id);
  return NextResponse.json({
    success: true,
    data: {
      favorites: favorites.map((f) => ({
        id: String(f.id),
        title: f.title,
        url: f.url,
        author: f.author,
        duration: f.duration,
        added_at: f.added_at,
      })),
    },
  });
}
