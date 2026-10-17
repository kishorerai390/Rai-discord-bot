import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth";
import { verifyPaymentSignature } from "@/lib/razorpay";
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
    const body = await req.json();
    const orderId = body.razorpay_order_id;
    const paymentId = body.razorpay_payment_id;
    const signature = body.razorpay_signature;
    const planId = body.plan_id || "monthly";

    if (!orderId || !paymentId || !signature) {
      return NextResponse.json(
        { success: false, error: "Missing cryptographic payment credentials" },
        { status: 400 }
      );
    }

    const isValid = verifyPaymentSignature(orderId, paymentId, signature);
    if (!isValid) {
      return NextResponse.json(
        { success: false, error: "Invalid payment cryptographic signature" },
        { status: 400 }
      );
    }

    // Provision entitlement in SQLite
    const db = getMusicDb();
    const nowIso = new Date().toISOString();
    const durationDays = planId === "yearly" ? 365 : planId === "lifetime" ? 36500 : 30;
    const expiresAt = new Date(Date.now() + durationDays * 86400 * 1000).toISOString();

    db.prepare(
      `INSERT INTO music_premium (entity_id, entity_type, is_premium, tier, activated_by, created_at, expires_at)
       VALUES (?, 'user', 1, ?, ?, ?, ?)
       ON CONFLICT(entity_id) DO UPDATE SET
         is_premium = 1,
         tier = excluded.tier,
         expires_at = excluded.expires_at`
    ).run(user.id, planId, user.id, nowIso, expiresAt);

    return NextResponse.json({
      success: true,
      data: {
        verified: true,
        plan: planId,
        expires_at: expiresAt,
        message: "Premium perks successfully unlocked for your account!",
      },
    });
  } catch (err: any) {
    return NextResponse.json(
      { success: false, error: err.message },
      { status: 500 }
    );
  }
}
