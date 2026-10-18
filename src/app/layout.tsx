import type { Metadata, Viewport } from "next";
import { Outfit, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { MusicProvider } from "@/context/MusicContext";
import { AppShell } from "@/components/AppShell";

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-outfit",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const viewport: Viewport = {
  themeColor: "#8b5cf6",
};

export const metadata: Metadata = {
  title: "MusicMaid ✦ Discord Music Engine & Master Control Panel",
  description:
    "Dedicated 24/7 Lossless 320kbps Discord Music Bot Control Panel. Control queues, DSP equalizer, Smart Auto-DJ, and synchronized playback.",
  keywords: [
    "Discord music bot",
    "MusicMaid",
    "320kbps Lossless audio",
    "Auto-DJ",
    "Equalizer DSP",
    "Discord bot control panel",
  ],
  manifest: "/manifest.json",
  icons: {
    icon: "/icon.png",
    apple: "/icon.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${outfit.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-[var(--bg-dark)] text-[var(--text)] min-h-screen antialiased selection:bg-purple-600 selection:text-white">
        <MusicProvider>
          <AppShell>{children}</AppShell>
        </MusicProvider>
      </body>
    </html>
  );
}

