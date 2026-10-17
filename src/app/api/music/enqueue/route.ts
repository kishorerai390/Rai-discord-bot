import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { submitWebAction } from "@/lib/db";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const guildId = String(body.guild_id || "1525030316845301781");
    const query = String(body.query || "").trim();

    if (!query) {
      return NextResponse.json(
        { success: false, error: "Search query or URL is required" },
        { status: 400 }
      );
    }

    const user = await getCurrentUser(req);
    const userId = user?.id || "1457382179981099090";

    const actionId = submitWebAction(guildId, "ENQUEUE", { query }, userId);

    return NextResponse.json({
      success: true,
      data: { action_id: actionId, status: "ENQUEUE_QUEUED" },
    });
  } catch (error: any) {
    return NextResponse.json(
      { success: false, error: error.message || "Failed to enqueue track" },
      { status: 500 }
    );
  }
}
