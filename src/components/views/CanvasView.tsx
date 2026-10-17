"use client";

import React, { useEffect, useRef, useState } from "react";
import { Sparkles, Maximize2, Minimize2, Radio } from "lucide-react";
import type { MusicSession } from "@/types/music";

interface CanvasViewProps {
  session: MusicSession | null;
  playbackSeconds: number;
}

export function CanvasView({ session, playbackSeconds }: CanvasViewProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [mode, setMode] = useState<"bars" | "wave" | "radial">("bars");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const isPlaying = session?.state === "PLAYING" && !session?.is_paused;
  const currentTrack = session?.current_track;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let tick = 0;

    const resize = () => {
      if (canvas.parentElement) {
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight || 450;
      }
    };
    resize();
    window.addEventListener("resize", resize);

    const render = () => {
      tick += 0.04;
      const width = canvas.width;
      const height = canvas.height;

      // Dark background clear with subtle decay for trail
      ctx.fillStyle = "rgba(7, 9, 14, 0.28)";
      ctx.fillRect(0, 0, width, height);

      const barCount = 48;
      const step = width / barCount;

      if (mode === "bars") {
        for (let i = 0; i < barCount; i++) {
          const factor = isPlaying
            ? Math.abs(Math.sin(tick + i * 0.25) * Math.cos(tick * 0.5 + i * 0.1))
            : 0.05 + Math.sin(tick * 0.3 + i * 0.1) * 0.02;

          const barH = factor * (height * 0.75);
          const x = i * step + step * 0.15;
          const y = height - barH;

          // Gradient for neon cyberpunk bars
          const grad = ctx.createLinearGradient(0, height, 0, y);
          grad.addColorStop(0, "rgba(147, 51, 234, 0.8)");
          grad.addColorStop(0.5, "rgba(0, 229, 255, 0.9)");
          grad.addColorStop(1, "rgba(236, 72, 153, 0.95)");

          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.roundRect(x, y, step * 0.7, barH, [4, 4, 0, 0]);
          ctx.fill();

          // Cap reflection
          ctx.fillStyle = "rgba(255, 255, 255, 0.75)";
          ctx.fillRect(x, y - 3, step * 0.7, 2);
        }
      } else if (mode === "wave") {
        ctx.beginPath();
        ctx.lineWidth = 3;
        ctx.strokeStyle = "rgba(0, 229, 255, 0.85)";

        for (let x = 0; x < width; x += 4) {
          const normX = x / width;
          const amp = isPlaying ? height * 0.28 : 10;
          const y =
            height / 2 +
            Math.sin(normX * 12 + tick * 3) * amp * Math.sin(normX * Math.PI) +
            Math.cos(normX * 24 - tick * 2) * (amp * 0.4);

          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.shadowColor = "rgba(0, 229, 255, 0.8)";
        ctx.shadowBlur = 12;
        ctx.stroke();
        ctx.shadowBlur = 0;
      } else if (mode === "radial") {
        const cx = width / 2;
        const cy = height / 2;
        const radius = Math.min(width, height) * 0.25;

        for (let i = 0; i < 64; i++) {
          const angle = (i / 64) * Math.PI * 2;
          const factor = isPlaying
            ? Math.abs(Math.sin(tick * 2 + i * 0.3)) * 0.8
            : 0.1;
          const r2 = radius + factor * (radius * 0.7);

          const x1 = cx + Math.cos(angle) * radius;
          const y1 = cy + Math.sin(angle) * radius;
          const x2 = cx + Math.cos(angle) * r2;
          const y2 = cy + Math.sin(angle) * r2;

          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.strokeStyle = `hsl(${(i * 5 + tick * 20) % 360}, 90%, 65%)`;
          ctx.lineWidth = 3;
          ctx.stroke();
        }
      }

      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
    };
  }, [mode, isPlaying]);

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  return (
    <div
      ref={containerRef}
      className={`glass-card relative rounded-2xl border border-[var(--card-border)] bg-[var(--bg-card)] overflow-hidden flex flex-col ${
        isFullscreen ? "h-screen w-screen p-6" : "h-[540px] p-4"
      }`}
    >
      {/* CANVAS CONTROLS HEADER */}
      <div className="absolute top-4 left-4 right-4 z-10 flex items-center justify-between pointer-events-auto">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-[var(--cyan)]">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white">Stage Visualizer</h2>
            <p className="text-[10px] text-[var(--text-muted)]">Live Lossless Frequency Spectrum</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {(["bars", "wave", "radial"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`chip-pill capitalize text-xs cursor-pointer ${
                mode === m ? "active border-[var(--primary)] text-white" : ""
              }`}
            >
              {m}
            </button>
          ))}

          <button
            onClick={toggleFullscreen}
            className="p-2 rounded-xl bg-white/10 hover:bg-white/20 text-white transition-all ml-2"
            title="Toggle Fullscreen"
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* CANVAS ELEMENT */}
      <canvas ref={canvasRef} className="w-full h-full flex-1 rounded-xl block" />

      {/* BOTTOM TRACK OVERLAY */}
      <div className="absolute bottom-6 left-6 right-6 z-10 flex items-center justify-between pointer-events-none">
        <div className="flex items-center gap-3 bg-black/60 backdrop-blur-md px-4 py-2.5 rounded-2xl border border-white/10 max-w-md">
          <img
            src={currentTrack?.thumbnail || "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=120"}
            alt="Track"
            className="w-10 h-10 rounded-lg object-cover"
          />
          <div className="min-w-0">
            <p className="text-xs font-bold text-white truncate">{currentTrack?.title || "No Track Active"}</p>
            <p className="text-[11px] text-[var(--cyan)] truncate">{currentTrack?.artist || "Rai Lossless Opus Engine"}</p>
          </div>
        </div>

        <span className="chip-pill bg-purple-500/20 text-purple-300 border border-purple-500/40 text-xs">
          {isPlaying ? "LIVE ANALYZER ACTIVE" : "ENGINE IDLE"}
        </span>
      </div>
    </div>
  );
}
