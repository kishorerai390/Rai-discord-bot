import crypto from "crypto";

export const RAZORPAY_KEY_ID = process.env.RAZORPAY_KEY_ID || "";
export const RAZORPAY_KEY_SECRET = process.env.RAZORPAY_KEY_SECRET || "";
export const RAZORPAY_WEBHOOK_SECRET = process.env.RAZORPAY_WEBHOOK_SECRET || "";

export const PAYMENTS_ENABLED =
  process.env.PAYMENTS_ENABLED === "true" ||
  Boolean(RAZORPAY_KEY_ID && RAZORPAY_KEY_SECRET && process.env.PAYMENTS_ENABLED !== "false");

export const PRICING_PLANS = {
  monthly: {
    id: "monthly",
    name: "MusicMaid Monthly VIP",
    amount: 199,
    amount_paise: 19900,
    interval: "monthly" as const,
    currency: "INR",
    description: "Full access to 320kbps Lossless, 150% volume boost, and 24/7 staying mode.",
    features: [
      "150% Boosted Master Volume Cap",
      "24/7 Voice Channel Staying Mode (/247)",
      "Studio DSP Equalizer Presets (Bass Boost, 8D, Nightcore)",
      "Smart Auto-DJ Endless Mix",
      "Gapless Audio Pre-resolver",
    ],
  },
  yearly: {
    id: "yearly",
    name: "MusicMaid Annual Pro",
    amount: 1499,
    amount_paise: 149900,
    interval: "yearly" as const,
    currency: "INR",
    description: "Best value for dedicated Discord servers and community creators (save 37%).",
    popular: true,
    features: [
      "All Monthly VIP Features Included",
      "Unlimited Server-Wide Playlists",
      "Priority Audio Decoding Headroom",
      "Custom Server Bass EQ Memory",
      "VIP Guild Badge & Role Sync",
    ],
  },
  lifetime: {
    id: "lifetime",
    name: "MusicMaid Lifetime VIP",
    amount: 3999,
    amount_paise: 399900,
    interval: "lifetime" as const,
    currency: "INR",
    description: "Permanent lifetime VIP pass with all present and future music perks.",
    features: [
      "Permanent Lifetime Unlocked Access",
      "Unlimited Discord Servers & Channels",
      "Community Early Access",
      "Zero Renewal Fees Ever",
      "Direct Priority Support Channel",
    ],
  },
};

export function verifyPaymentSignature(
  orderId: string,
  paymentId: string,
  signature: string
): boolean {
  if (!RAZORPAY_KEY_SECRET || !signature) return false;
  const payload = `${orderId}|${paymentId}`;
  const expected = crypto
    .createHmac("sha256", RAZORPAY_KEY_SECRET)
    .update(payload)
    .digest("hex");
  const expectedBuf = Buffer.from(expected);
  const signatureBuf = Buffer.from(signature);
  if (expectedBuf.length !== signatureBuf.length) return false;
  return crypto.timingSafeEqual(expectedBuf, signatureBuf);
}

export function verifyWebhookSignature(
  rawBody: string,
  signature: string
): boolean {
  if (!RAZORPAY_WEBHOOK_SECRET || !signature) return false;
  const expected = crypto
    .createHmac("sha256", RAZORPAY_WEBHOOK_SECRET)
    .update(rawBody)
    .digest("hex");
  const expectedBuf = Buffer.from(expected);
  const signatureBuf = Buffer.from(signature);
  if (expectedBuf.length !== signatureBuf.length) return false;
  return crypto.timingSafeEqual(expectedBuf, signatureBuf);
}

export async function createRazorpayOrder(
  planId: "monthly" | "yearly" | "lifetime",
  userId: string,
  guildId?: string
) {
  const plan = PRICING_PLANS[planId];
  if (!plan) {
    throw new Error(`Invalid plan: ${planId}`);
  }

  if (!PAYMENTS_ENABLED || !RAZORPAY_KEY_ID || !RAZORPAY_KEY_SECRET) {
    throw new Error(
      "Payment processing is currently in demonstration mode (PAYMENTS_ENABLED=false). Real checkouts are disabled."
    );
  }

  const receipt = `rcpt_${userId.slice(-6)}_${Date.now().toString().slice(-6)}`;
  const authHeader = Buffer.from(
    `${RAZORPAY_KEY_ID}:${RAZORPAY_KEY_SECRET}`
  ).toString("base64");

  const res = await fetch("https://api.razorpay.com/v1/orders", {
    method: "POST",
    headers: {
      Authorization: `Basic ${authHeader}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      amount: plan.amount_paise,
      currency: plan.currency,
      receipt: receipt,
      notes: {
        user_id: userId,
        guild_id: guildId || "global",
        plan_id: planId,
        platform: "MusicMaid_Web",
      },
    }),
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(
      `Razorpay order creation failed: ${errData.error?.description || res.statusText}`
    );
  }

  const orderData = await res.json();
  return {
    id: orderData.id,
    amount: orderData.amount,
    currency: orderData.currency,
    receipt: orderData.receipt,
    key_id: RAZORPAY_KEY_ID,
    plan_id: planId,
  };
}
