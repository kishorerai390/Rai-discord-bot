"""
Raivora Music Maid (MusicMaid / Neko Songs) - Primary Discord Music Bot.
Dedicated 24/7 Hi-Fi Lossless Music Engine with Smart Auto-DJ, DSP Equalizer,
and Policy-Compliant Spotify Integration.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

# Windows console UTF-8 safety
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _ensure_ytdlp_javascript_runtime() -> None:
    """Best-effort Deno bootstrap for native Render deployments.

    yt-dlp's EJS challenge solver needs a supported JavaScript runtime.
    Render Blueprint/Docker installs are preferred; this fallback lets an
    existing native-Python service bootstrap Deno without a dashboard change.
    The bot still starts if installation is unavailable.
    """
    if shutil.which("deno"):
        print("[Runtime] Deno JavaScript runtime available.", flush=True)
        return
    if os.getenv("YTDLP_BOOTSTRAP_DENO", "1").strip().lower() in {"0", "false", "no", "off"}:
        print("[Runtime] Deno bootstrap disabled; yt-dlp EJS challenge solving may be limited.", flush=True)
        return
    install_dir = Path(__file__).resolve().parent / ".deno"
    deno_bin = install_dir / "bin" / "deno"
    if deno_bin.is_file():
        os.environ["DENO_INSTALL"] = str(install_dir)
        os.environ["PATH"] = f"{deno_bin.parent}{os.pathsep}{os.environ.get('PATH', '')}"
        print("[Runtime] Using project-local Deno runtime.", flush=True)
        return
    if sys.platform == "win32":
        print("[Runtime] Deno auto-install skipped on Windows; install Deno separately for EJS support.", flush=True)
        return
    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["DENO_INSTALL"] = str(install_dir)
        print("[Runtime] Deno not found; attempting Deno 2.9.4 install (JukeBot-aligned) for yt-dlp EJS.", flush=True)
        result = subprocess.run(
            ["bash", "-lc", "curl -fsSL https://deno.land/install.sh | sh -s v2.9.4"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=90,
            check=False,
        )
        if result.returncode == 0 and deno_bin.is_file():
            os.environ["DENO_INSTALL"] = str(install_dir)
            os.environ["PATH"] = f"{deno_bin.parent}{os.pathsep}{os.environ.get('PATH', '')}"
            print("[Runtime] Deno installed; yt-dlp EJS runtime enabled.", flush=True)
        else:
            print(f"[Runtime] Deno bootstrap unavailable (exit={result.returncode}); continuing without it.", flush=True)
            if result.stdout:
                print(result.stdout[-1500:], flush=True)
    except Exception as exc:
        print(f"[Runtime] Deno bootstrap failed ({type(exc).__name__}); continuing without it.", flush=True)


_ensure_ytdlp_javascript_runtime()

# Initialize static FFmpeg binaries if available
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass

from music_bot.main import main

if __name__ == "__main__":
    main()
