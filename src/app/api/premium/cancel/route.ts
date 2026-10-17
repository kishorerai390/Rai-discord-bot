import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getMusicDb } from "@/lib/db";

export async function POST(req: NextRequest) {
  const user = await getCurrentUser(req);
  if (!user) {
    return NextResponse.json(
      { success: false, error: "Authentication required" },
      { status: 401 }
    );
  }

  try {
    const db = getMusicDb();
    db.prepare("UPDATE music_premium SET is_premium = 0 WHERE entity_id = ?").run(user.id);
    return NextResponse.json({
      success: true,
      data: {
        cancelled: true,
        message: "Your subscription has been cancelled.",
      },
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
