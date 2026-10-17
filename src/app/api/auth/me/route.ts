import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";

export async function GET(req: NextRequest) {
  const user = await getCurrentUser(req);
  if (!user) {
    return NextResponse.json({
      success: true,
      data: {
        authenticated: false,
        user: null,
      },
    });
  }

  return NextResponse.json({
    success: true,
    data: {
      authenticated: true,
      user,
    },
  });
}
