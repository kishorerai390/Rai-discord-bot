import { NextResponse } from "next/server";
import {
  PRICING_PLANS,
  PAYMENTS_ENABLED,
  RAZORPAY_KEY_ID,
} from "@/lib/razorpay";

export async function GET() {
  return NextResponse.json({
    success: true,
    data: {
      configured: Boolean(RAZORPAY_KEY_ID),
      payments_enabled: PAYMENTS_ENABLED,
      currency: "INR",
      plans: PRICING_PLANS,
      features: [
        {
          name: "320kbps Lossless Opus",
          description: "Studio-grade audio fidelity with zero distortion or downsampling.",
        },
        {
          name: "150% Volume Booster",
          description: "Extra audio headroom beyond Discord's standard 100% volume ceiling.",
        },
        {
          name: "24/7 Voice Channel Staying",
          description: "Bot remains in your voice room non-stop without timeout disconnects.",
        },
        {
          name: "Studio DSP Equalizer Presets",
          description: "Instant Bass Boost, Nightcore, 8D Audio, Lo-Fi, and Vaporwave acoustics.",
        },
        {
          name: "Smart Auto-DJ Mix",
          description: "Endless intelligent music recommendations when your queue ends.",
        },
      ],
      faqs: [
        {
          q: "What payment methods are supported?",
          a: "All major Credit/Debit Cards, UPI (Google Pay, PhonePe, Paytm), and Net Banking via Razorpay.",
        },
        {
          q: "Does 24/7 staying mode work across restarts?",
          a: "Yes! 24/7 persistence is stored in the persistent database and reconnects automatically.",
        },
        {
          q: "What is Student Developer Showcase Mode?",
          a: "When PAYMENTS_ENABLED=false, features and audio comparisons are previewed without live transactions.",
        },
      ],
    },
  });
}
