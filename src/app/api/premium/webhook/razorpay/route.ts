import { NextRequest, NextResponse } from "next/server";
import { verifyWebhookSignature } from "@/lib/razorpay";
import { getMusicDb } from "@/lib/db";

export async function POST(req: NextRequest) {
  try {
    const rawBody = await req.text();
    const signature = req.headers.get("x-razorpay-signature");

    if (!signature || !verifyWebhookSignature(rawBody, signature)) {
      return NextResponse.json(
        { success: false, error: "Invalid webhook signature" },
        { status: 400 }
      );
    }

    const event = JSON.parse(rawBody);
    const eventType = event.event;
    const db = getMusicDb();

    // Idempotency check via payment_webhook_events
    try {
      const eventId = event.payload?.payment?.entity?.id || event.created_at;
      const existing = db
        .prepare("SELECT id FROM payment_webhook_events WHERE event_id = ?")
        .get(eventId);
      if (existing) {
        return NextResponse.json({ success: true, status: "already_processed" });
      }
      db.prepare(
        "INSERT INTO payment_webhook_events (event_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)"
      ).run(eventId, eventType, rawBody, new Date().toISOString());
    } catch {}

    if (eventType === "payment.captured" || eventType === "order.paid") {
      const payment = event.payload?.payment?.entity;
      const notes = payment?.notes || {};
      const userId = notes.user_id;
      const planId = notes.plan_id || "monthly";

      if (userId) {
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
        ).run(userId, planId, userId, nowIso, expiresAt);
      }
    }

    return NextResponse.json({ success: true, received: true });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
