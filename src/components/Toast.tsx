"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, Info, X } from "lucide-react";

export interface ToastMessage {
  id: string;
  text: string;
  type: "success" | "danger" | "info";
}

interface ToastContainerProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-24 right-6 z-50 flex flex-col gap-2 max-w-sm pointer-events-none">
      {toasts.map((toast) => {
        let borderClass = "border-purple-500/40";
        let icon = <Info className="w-4 h-4 text-cyan-400 shrink-0" />;

        if (toast.type === "success") {
          borderClass = "border-emerald-500/40";
          icon = <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />;
        } else if (toast.type === "danger") {
          borderClass = "border-rose-500/40";
          icon = <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />;
        }

        return (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-center justify-between gap-3 p-3.5 rounded-xl bg-[#0f1422]/95 backdrop-blur-md border ${borderClass} shadow-2xl text-xs text-white animate-in slide-in-from-bottom-2 duration-200`}
          >
            <div className="flex items-center gap-2.5 min-w-0">
              {icon}
              <span className="truncate">{toast.text}</span>
            </div>
            <button
              onClick={() => onDismiss(toast.id)}
              className="text-(--text-dim) hover:text-white transition-colors ml-2"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
