import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { getUserEntitlement } from "@/lib/db";

export async function GET(req: NextRequest) {
  const user = await getCurrentUser(req);
  const userId = user?.id || "guest";
  const entitlement = getUserEntitlement(userId);

  return NextResponse.json({
    success: true,
    data: {
      entitlement,
    },
  });
}
