"use client";

import React, { useState } from "react";
import { ShieldCheck, FileText, RefreshCw, Mail, MessageSquare } from "lucide-react";

interface LegalViewProps {
  initialTab?: "terms" | "privacy" | "refund" | "contact";
}

export function LegalView({ initialTab = "terms" }: LegalViewProps) {
  const [tab, setTab] = useState<"terms" | "privacy" | "refund" | "contact">(initialTab);

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto">
      {/* NAVIGATION TABS */}
      <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-4 backdrop-blur-xl">
        <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
          <button
            onClick={() => setTab("terms")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs md:text-sm font-semibold transition-all shrink-0 ${
              tab === "terms"
                ? "bg-[var(--primary)] text-white shadow-md shadow-purple-900/30"
                : "text-[var(--text-muted)] hover:text-white hover:bg-white/5"
            }`}
          >
            <FileText className="w-4 h-4" />
            <span>Terms of Service</span>
          </button>

          <button
            onClick={() => setTab("privacy")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs md:text-sm font-semibold transition-all shrink-0 ${
              tab === "privacy"
                ? "bg-[var(--primary)] text-white shadow-md shadow-purple-900/30"
                : "text-[var(--text-muted)] hover:text-white hover:bg-white/5"
            }`}
          >
            <ShieldCheck className="w-4 h-4 text-cyan-400" />
            <span>Privacy Policy</span>
          </button>

          <button
            onClick={() => setTab("refund")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs md:text-sm font-semibold transition-all shrink-0 ${
              tab === "refund"
                ? "bg-[var(--primary)] text-white shadow-md shadow-purple-900/30"
                : "text-[var(--text-muted)] hover:text-white hover:bg-white/5"
            }`}
          >
            <RefreshCw className="w-4 h-4 text-amber-400" />
            <span>Refund Policy</span>
          </button>

          <button
            onClick={() => setTab("contact")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs md:text-sm font-semibold transition-all shrink-0 ${
              tab === "contact"
                ? "bg-[var(--primary)] text-white shadow-md shadow-purple-900/30"
                : "text-[var(--text-muted)] hover:text-white hover:bg-white/5"
            }`}
          >
            <Mail className="w-4 h-4 text-emerald-400" />
            <span>Contact & Support</span>
          </button>
        </div>
      </div>

      {/* DOCUMENT BODY */}
      <div className="glass-card rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] p-8 backdrop-blur-xl text-white">
        {tab === "terms" && (
          <div className="space-y-6 text-sm text-[var(--text-muted)] leading-relaxed">
            <div className="border-b border-white/10 pb-4">
              <span className="chip-pill active text-xs font-bold mb-2">Legal Compliance</span>
              <h2 className="text-2xl font-black text-white mt-1">Terms of Service</h2>
              <p className="text-xs text-[var(--text-dim)]">Last updated: April 2026</p>
            </div>

            <div>
              <h3 className="text-base font-bold text-white mb-2">1. Agreement to Terms</h3>
              <p>
                By adding MusicMaid (&quot;the Bot&quot;) to your Discord guild, accessing the web dashboard, or interacting with our services, you agree to comply with and be bound by these Terms of Service.
              </p>
            </div>

            <div>
              <h3 className="text-base font-bold text-white mb-2">2. Description of Service</h3>
              <p>
                MusicMaid is an automated 24/7 Discord music bot providing lossless audio streaming, DSP filters, synchronized playback, and web control panels. We do not host or store copyrighted audio content; the service resolves publicly accessible streams requested by users.
              </p>
            </div>

            <div>
              <h3 className="text-base font-bold text-white mb-2">3. Acceptable Use</h3>
              <p>
                Users agree not to exploit, stress-test, spam commands, bypass rate limits, or reverse-engineer the bot or its infrastructure. Violations may result in blacklisting from the service.
              </p>
            </div>

            <div>
              <h3 className="text-base font-bold text-white mb-2">4. Subscriptions and Payments</h3>
              <p>
                Premium subscriptions unlock cosmetic and enhanced streaming perks. Subscriptions are billed through compliant gateways such as Razorpay. All fees are clearly stated prior to confirmation.
              </p>
            </div>
          </div>
        )}

        {tab === "privacy" && (
          <div className="space-y-6 text-sm text-[var(--text-muted)] leading-relaxed">
            <div className="border-b border-white/10 pb-4">
              <span className="chip-pill active text-xs font-bold mb-2">Data Privacy & GDPR</span>
              <h2 className="text-2xl font-black text-white mt-1">Privacy Policy</h2>
              <p className="text-xs text-[var(--text-dim)]">Last updated: April 2026</p>
            </div>

            <div>
              <h3 className="text-base font-bold text-white mb-2">1. Information We Collect</h3>
              <p>
                We adhere to strict data minimization. We collect your Discord User ID, username, server IDs where the bot is added, and anonymous playback queue titles to facilitate streaming and personal playlists.
              </p>
            </div>

            <div>
              <h3 className="text-base font-bold text-white mb-2">2. Voice Privacy</h3>
              <p>
                MusicMaid does NOT record, eavesdrop on, or transcribe voice communications. Audio streaming is strictly unidirectional (bot to voice channel).
              </p>
            </div>

            <div>
              <h3 className="text-base font-bold text-white mb-2">3. Data Retention and Deletion</h3>
              <p>
                Temporary playback history is purged periodically. Users may request full erasure of their saved playlists and favorites at any time via support.
              </p>
            </div>
          </div>
        )}

        {tab === "refund" && (
          <div className="space-y-6 text-sm text-[var(--text-muted)] leading-relaxed">
            <div className="border-b border-white/10 pb-4">
              <span className="chip-pill active text-xs font-bold mb-2">Consumer Protection</span>
              <h2 className="text-2xl font-black text-white mt-1">Cancellation & Refund Policy</h2>
              <p className="text-xs text-[var(--text-dim)]">Last updated: April 2026</p>
            </div>

            <div>
              <h3 className="text-base font-bold text-white mb-2">1. 7-Day Refund Window</h3>
              <p>
                If you encounter technical issues with MusicMaid Pro within 7 days of purchase that our team cannot resolve, you are entitled to a full refund.
              </p>
            </div>

            <div>
              <h3 className="text-base font-bold text-white mb-2">2. How to Request a Refund</h3>
              <p>
                Contact support via Discord or email with your Payment ID (e.g. Razorpay payment ID) and Discord User ID. Refunds are typically processed back to the original payment method within 5-7 business days.
              </p>
            </div>
          </div>
        )}

        {tab === "contact" && (
          <div className="space-y-6 text-sm text-[var(--text-muted)] leading-relaxed">
            <div className="border-b border-white/10 pb-4">
              <span className="chip-pill active text-xs font-bold mb-2">Get in Touch</span>
              <h2 className="text-2xl font-black text-white mt-1">Contact Us & Support</h2>
              <p className="text-xs text-[var(--text-dim)]">Support hours: 24/7 community response</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-5 rounded-2xl bg-white/5 border border-white/10 flex flex-col justify-between">
                <div>
                  <div className="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400 mb-3">
                    <MessageSquare className="w-5 h-5" />
                  </div>
                  <h4 className="font-bold text-white text-base">Official Discord Server</h4>
                  <p className="text-xs text-[var(--text-muted)] mt-1">
                    Join our developer community for real-time announcements, bot status updates, and support.
                  </p>
                </div>
                <a
                  href="https://discord.gg"
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-primary btn-sm mt-4 text-xs flex items-center justify-center gap-2"
                >
                  Join Discord Community ↗
                </a>
              </div>

              <div className="p-5 rounded-2xl bg-white/5 border border-white/10 flex flex-col justify-between">
                <div>
                  <div className="w-10 h-10 rounded-xl bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400 mb-3">
                    <Mail className="w-5 h-5" />
                  </div>
                  <h4 className="font-bold text-white text-base">Direct Developer Email</h4>
                  <p className="text-xs text-[var(--text-muted)] mt-1">
                    For billing inquiries, partnership requests, or security disclosures, reach out directly.
                  </p>
                </div>
                <a
                  href="mailto:support@musicmaid.bot"
                  className="btn btn-secondary btn-sm mt-4 text-xs flex items-center justify-center gap-2 hover:border-cyan-500/40"
                >
                  support@musicmaid.bot ✉
                </a>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
