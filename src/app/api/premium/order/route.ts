import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import {
  createRazorpayOrder,
  PAYMENTS_ENABLED,
  PRICING_PLANS,
} from "@/lib/razorpay";

export async function POST(req: NextRequest) {
  const user = await getCurrentUser(req);
  if (!user) {
    return NextResponse.json(
      { success: false, error: "Please sign in with Discord first to subscribe!" },
      { status: 401 }
    );
  }

  try {
    const body = await req.json();
    let planId = (body.plan_id || body.plan || "monthly").toLowerCase();
    if (planId === "pro_monthly") planId = "monthly";
    if (planId === "vip_yearly") planId = "yearly";

    if (!(planId in PRICING_PLANS)) {
      return NextResponse.json(
        { success: false, error: `Invalid plan: ${planId}` },
        { status: 400 }
      );
    }

    if (!PAYMENTS_ENABLED) {
      return NextResponse.json({
        success: false,
        error:
          "Payment processing is currently in demonstration mode (PAYMENTS_ENABLED=false). Real checkouts and billing are disabled.",
        is_demo: true,
      }, { status: 400 });
    }

    const order = await createRazorpayOrder(
      planId as "monthly" | "yearly" | "lifetime",
      user.id,
      body.guild_id
    );

    return NextResponse.json({
      success: true,
      data: order,
    });
  } catch (err: any) {
    return NextResponse.json(
      { success: false, error: err.message },
      { status: 500 }
    );
  }
}
