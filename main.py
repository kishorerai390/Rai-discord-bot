"""
Raivora Music Maid (MusicMaid / Neko Songs) - Primary Discord Music Bot.
Dedicated 24/7 Hi-Fi Lossless Music Engine with Smart Auto-DJ, DSP Equalizer,
and Policy-Compliant Spotify Integration.
"""

from __future__ import annotations

import sys

# Windows console UTF-8 safety
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Initialize static FFmpeg binaries if available
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass

from music_bot.main import main

if __name__ == "__main__":
    main()
