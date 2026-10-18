import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDuration(seconds: number): string {
  if (!seconds || isNaN(seconds) || seconds < 0) return "00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m < 10 ? "0" + m : m}:${s < 10 ? "0" + s : s}`;
}

export const DEFAULT_TRACK_ARTWORK = "data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300' viewBox='0 0 300 300'%3E%3Cdefs%3E%3ClinearGradient id='neonG' x1='0%25' y1='0%25' x2='100%25' y2='100%25'%3E%3Cstop offset='0%25' stop-color='%2312131C'/%3E%3Cstop offset='100%25' stop-color='%2308090D'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='100%25' height='100%25' fill='url(%23neonG)'/%3E%3Ccircle cx='150' cy='150' r='75' fill='none' stroke='%2300E5FF' stroke-width='4' opacity='0.35'/%3E%3Ccircle cx='150' cy='150' r='30' fill='%23FF0055' opacity='0.55'/%3E%3Ctext x='150' y='162' fill='%2300E5FF' font-family='system-ui, sans-serif' font-size='36' text-anchor='middle'%3E%E2%99%AA%3C/text%3E%3C/svg%3E";
