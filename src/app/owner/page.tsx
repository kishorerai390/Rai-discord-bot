"use client";

import React from "react";
import Link from "next/link";
import { ShieldAlert, LogIn, Lock } from "lucide-react";
import { useMusic } from "@/context/MusicContext";
import { OwnerView } from "@/components/views/OwnerView";

export default function OwnerPage() {
  const { currentUser, showToast } = useMusic();

  if (!currentUser) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-6">
        <div className="w-16 h-16 rounded-3xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 mb-4 shadow-xl shadow-amber-500/10">
          <Lock className="w-8 h-8" />
        </div>
        <h2 className="text-xl font-bold text-white mb-2">Authentication Required</h2>
        <p className="text-xs text-[var(--text-muted)] max-w-md mb-6 leading-relaxed">
          The Creator Operations Control Room is restricted. Please sign in with your verified Discord account to verify owner entitlements.
        </p>
        <Link
          href="/api/auth/login"
          className="btn btn-primary flex items-center gap-2 py-2.5 px-6 font-bold text-sm bg-gradient-to-r from-amber-500 to-orange-500 text-black shadow-lg shadow-amber-500/20"
        >
          <LogIn className="w-4 h-4" />
          <span>Sign In With Discord</span>
        </Link>
      </div>
    );
  }

  if (!currentUser.is_owner) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-6">
        <div className="w-16 h-16 rounded-3xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 mb-4 shadow-xl shadow-rose-500/10">
          <ShieldAlert className="w-8 h-8" />
        </div>
        <h2 className="text-xl font-bold text-white mb-2">Access Restricted (403 Forbidden)</h2>
        <p className="text-xs text-[var(--text-muted)] max-w-md mb-6 leading-relaxed">
          Your account (<span className="text-white font-mono">{currentUser.display_name}</span>) is authenticated, but does not possess root Bot Creator privileges.
        </p>
        <Link href="/" className="btn btn-secondary btn-sm text-xs">
          Return to Dashboard
        </Link>
      </div>
    );
  }

  return <OwnerView onShowToast={showToast} />;
}
