"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useMusic } from "@/context/MusicContext";
import { StatsView } from "@/components/views/StatsView";
import { ShieldAlert } from "lucide-react";

export default function StatsPage() {
  const router = useRouter();
  const { currentUser, showToast } = useMusic();

  if (currentUser && !currentUser.is_owner) {
    return (
      <div className="glass-card rounded-2xl border border-rose-500/30 bg-[var(--bg-card)] p-8 max-w-lg mx-auto text-center flex flex-col items-center gap-3 my-12 backdrop-blur-xl">
        <ShieldAlert className="w-12 h-12 text-rose-400" />
        <h2 className="text-xl font-bold text-white">Owner Access Restricted</h2>
        <p className="text-xs text-[var(--text-muted)] leading-relaxed">
          The SERVER management section is restricted exclusively to the bot owner.
        </p>
        <button onClick={() => router.push("/dashboard")} className="btn btn-secondary btn-sm mt-2">
          Return to Dashboard
        </button>
      </div>
    );
  }

  return <StatsView onShowToast={showToast} />;
}
