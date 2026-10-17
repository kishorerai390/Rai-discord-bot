"use client";

import React, { useEffect, useState } from "react";
import { Crown, Sparkles, Check, Zap, ShieldCheck, AlertCircle, Loader2 } from "lucide-react";
import type { DiscordUser } from "@/types/auth";
import type { UserEntitlement, PricingPlan } from "@/types/premium";

declare global {
  interface Window {
    Razorpay: any;
  }
}

interface PremiumViewProps {
  user: DiscordUser | null;
  onShowToast: (msg: string, type?: "success" | "danger" | "info") => void;
  onRefreshUser: () => Promise<void>;
}

export function PremiumView({ user, onShowToast, onRefreshUser }: PremiumViewProps) {
  const [plans, setPlans] = useState<PricingPlan[]>([]);
  const [entitlement, setEntitlement] = useState<UserEntitlement | null>(null);
  const [loading, setLoading] = useState(true);
  const [processingPlan, setProcessingPlan] = useState<string | null>(null);
  const [paymentNotice, setPaymentNotice] = useState<string | null>(null);

  const fetchPremiumStatus = async () => {
    setLoading(true);
    try {
      const [plansRes, statusRes] = await Promise.all([
        fetch("/api/premium/plans"),
        fetch("/api/premium/status"),
      ]);

      const plansData = await plansRes.json();
      const statusData = await statusRes.json();

      if (plansData.success && Array.isArray(plansData.plans)) {
        setPlans(plansData.plans);
      }
      if (statusData.success && statusData.entitlement) {
        setEntitlement(statusData.entitlement);
      }
      if (plansData.message) {
        setPaymentNotice(plansData.message);
      }
    } catch (e: any) {
      console.warn("Premium fetch error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPremiumStatus();
  }, []);

  const handleSubscribe = async (planId: string) => {
    if (!user) {
      onShowToast("Please log in with Discord first to subscribe ✦", "info");
      window.location.href = "/api/auth/login";
      return;
    }

    setProcessingPlan(planId);
    try {
      const res = await fetch("/api/premium/create-order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_id: planId }),
      });
      const data = await res.json();

      if (!data.success) {
        if (data.mode === "STUDENT_SHOWCASE_MODE" || data.mode === "DISABLED") {
          onShowToast(
            data.error || "Portfolio Showcase: Payment processing is in demonstration mode.",
            "info"
          );
        } else {
          onShowToast(data.error || "Failed to initialize checkout", "danger");
        }
        setProcessingPlan(null);
        return;
      }

      // If Razorpay order created and key_id available
      if (data.order && data.key_id) {
        // Load Razorpay checkout script if needed
        if (!window.Razorpay) {
          const script = document.createElement("script");
          script.src = "https://checkout.razorpay.com/v1/checkout.js";
          script.async = true;
          document.body.appendChild(script);
          await new Promise((resolve) => (script.onload = resolve));
        }

        const options = {
          key: data.key_id,
          amount: data.order.amount,
          currency: data.order.currency,
          name: "MusicMaid Pro",
          description: `${planId.toUpperCase()} Subscription Grant`,
          order_id: data.order.id,
          prefill: {
            name: user.username,
            email: user.email || `${user.username}@discord.user`,
          },
          theme: { color: "#9333ea" },
          handler: async function (response: any) {
            onShowToast("Verifying payment with gateway...", "info");
            const verifyRes = await fetch("/api/premium/verify", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(response),
            });
            const verifyData = await verifyRes.json();
            if (verifyData.success) {
              onShowToast("🎉 Premium unlocked successfully! Welcome to Pro!", "success");
              await fetchPremiumStatus();
              await onRefreshUser();
            } else {
              onShowToast("Verification failed: " + (verifyData.error || "Unknown error"), "danger");
            }
          },
        };

        const rzp = new window.Razorpay(options);
        rzp.open();
      } else {
        onShowToast("Portfolio Preview: Live orders simulated cleanly.", "info");
      }
    } catch (e: any) {
      onShowToast(`Checkout notice: ${e.message}`, "danger");
    } finally {
      setProcessingPlan(null);
    }
  };

  const isOwner = Boolean(user?.is_owner || entitlement?.plan === "owner");
  const isPremium = Boolean(isOwner || entitlement?.is_premium);

  return (
    <div className="flex flex-col gap-6">
      {/* CREATOR VIP / ACTIVE STATUS BANNER */}
      {isOwner ? (
        <div className="rounded-2xl p-6 bg-gradient-to-r from-amber-500/20 via-purple-900/30 to-cyan-500/20 border-2 border-amber-500/50 shadow-xl shadow-amber-900/20 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4 text-center md:text-left">
            <div className="w-14 h-14 rounded-2xl bg-amber-500/30 border border-amber-500/60 flex items-center justify-center text-3xl shadow-lg shadow-amber-500/30">
              👑
            </div>
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-amber-300">
                Bot Creator & Architect VIP
              </span>
              <h2 className="text-2xl font-black text-white">Full Platform Master Access Granted</h2>
              <p className="text-xs text-amber-100/80 mt-1">
                You are recognized as the developer of MusicMaid. All 320kbps lossless features, 24/7 staying, DSP audio presets, and 150% volume boost are permanently active.
              </p>
            </div>
          </div>
          <span className="chip-pill bg-amber-500/30 text-amber-200 border border-amber-400 font-bold px-4 py-1.5 text-xs">
            PERMANENT VIP
          </span>
        </div>
      ) : isPremium ? (
        <div className="rounded-2xl p-6 bg-gradient-to-r from-purple-500/20 to-cyan-500/20 border border-purple-500/40 shadow-xl flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-purple-500/30 border border-purple-500/50 flex items-center justify-center text-2xl">
              💎
            </div>
            <div>
              <span className="text-xs font-bold uppercase text-purple-300">Active Membership</span>
              <h3 className="text-xl font-bold text-white">MusicMaid Pro Active</h3>
              <p className="text-xs text-[var(--text-muted)]">
                Enjoy lossless 320kbps streaming, DSP filters, and unlimited queue slots.
              </p>
            </div>
          </div>
          <span className="chip-pill active text-xs font-bold px-4 py-1.5">PRO ACTIVE ✅</span>
        </div>
      ) : null}

      {/* STUDENT SHOWCASE / PORTFOLIO BANNER */}
      <div className="rounded-2xl p-4 bg-purple-900/20 border border-purple-500/30 flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-[var(--cyan)] shrink-0 mt-0.5" />
        <div className="text-xs text-[var(--text-muted)] leading-relaxed">
          <strong className="text-white">Student Developer Portfolio & Preview Mode: </strong>
          Payments are managed safely with Razorpay integration and automated database entitlements. In demonstration mode, premium features can also be directly granted by bot administrators.
        </div>
      </div>

      {/* PRICING PLANS GRID */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* FREE TIER */}
        <div className="rounded-2xl p-6 bg-white/5 border border-white/10 flex flex-col justify-between">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-[var(--text-dim)]">Community</span>
            <h3 className="text-xl font-bold text-white mt-1">Free Tier</h3>
            <div className="text-3xl font-extrabold text-white mt-3">
              ₹0 <span className="text-sm font-normal text-[var(--text-muted)]">/ forever</span>
            </div>
            <p className="text-xs text-[var(--text-muted)] mt-2">
              Essential Discord audio streaming for casual gaming and small servers.
            </p>

            <ul className="mt-6 space-y-3 text-xs text-[var(--text-muted)]">
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-400" /> Standard 128kbps Opus Audio
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-400" /> Up to 50 Queued Songs
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-400" /> Basic Multi-lingual Search
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-400" /> Standard 80% Volume Ceiling
              </li>
            </ul>
          </div>

          <button disabled className="btn btn-secondary btn-sm w-full mt-6 text-xs opacity-60">
            Included by Default
          </button>
        </div>

        {/* MONTHLY PRO */}
        <div className="rounded-2xl p-6 bg-gradient-to-b from-purple-900/30 to-purple-950/20 border-2 border-[var(--primary)] shadow-xl shadow-purple-900/30 flex flex-col justify-between relative">
          <span className="absolute -top-3 right-6 bg-[var(--primary)] text-white text-[10px] font-extrabold px-3 py-0.5 rounded-full uppercase tracking-wider shadow-md">
            Most Popular
          </span>

          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-purple-300">Creator Pass</span>
            <h3 className="text-xl font-bold text-white mt-1">Monthly Pro</h3>
            <div className="text-3xl font-extrabold text-white mt-3">
              ₹99 <span className="text-sm font-normal text-[var(--text-muted)]">/ month</span>
            </div>
            <p className="text-xs text-[var(--text-muted)] mt-2">
              Lossless 320kbps audio, 24/7 staying, DSP equalizer filters, and volume boost.
            </p>

            <ul className="mt-6 space-y-3 text-xs text-white">
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-cyan-400" /> 320kbps Bit-Perfect Lossless Opus
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-cyan-400" /> 24/7 Voice Channel Staying
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-cyan-400" /> 150% Amplified Volume Boost
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-cyan-400" /> 8D, Bass Boost & Nightcore Filters
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-cyan-400" /> Unlimited Queue Capacity
              </li>
            </ul>
          </div>

          <button
            onClick={() => handleSubscribe("pro_monthly")}
            disabled={processingPlan === "pro_monthly" || isPremium}
            className="btn btn-primary btn-sm w-full mt-6 text-xs flex items-center justify-center gap-2"
          >
            {processingPlan === "pro_monthly" ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : isPremium ? (
              "Already Active"
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>Upgrade to Pro (₹99)</span>
              </>
            )}
          </button>
        </div>

        {/* YEARLY VIP */}
        <div className="rounded-2xl p-6 bg-white/5 border border-white/10 hover:border-cyan-500/40 transition-all flex flex-col justify-between">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-cyan-400">Lifetime Club</span>
            <h3 className="text-xl font-bold text-white mt-1">Yearly VIP</h3>
            <div className="text-3xl font-extrabold text-white mt-3">
              ₹799 <span className="text-sm font-normal text-[var(--text-muted)]">/ year</span>
            </div>
            <p className="text-xs text-[var(--text-muted)] mt-2">
              Save 33% annually. Includes exclusive Discord VIP role and dedicated server priority.
            </p>

            <ul className="mt-6 space-y-3 text-xs text-[var(--text-muted)]">
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-cyan-400" /> All Monthly Pro Features Included
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-cyan-400" /> Discord Server VIP Role & Color
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-cyan-400" /> Custom Bot Avatar & Nickname
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-cyan-400" /> 2 Months Free (Save ₹389/yr)
              </li>
            </ul>
          </div>

          <button
            onClick={() => handleSubscribe("vip_yearly")}
            disabled={processingPlan === "vip_yearly" || isPremium}
            className="btn btn-secondary btn-sm w-full mt-6 text-xs flex items-center justify-center gap-2 hover:border-cyan-500/40"
          >
            {processingPlan === "vip_yearly" ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : isPremium ? (
              "Already Active"
            ) : (
              <>
                <Crown className="w-4 h-4 text-cyan-400" />
                <span>Get Yearly VIP (₹799)</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
