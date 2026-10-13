"""
Unified Dual-Bot Ecosystem Launcher for Rai.
Spawns both The Raivora (Security/Moderation) and Neko Songs (Music Bot)
as concurrent subprocesses with synchronized logging and graceful shutdown.
Run with: python ecosystem.py (or npm start)
"""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from utils.instance_lock import (
    SingleInstanceLock,
    InstanceAlreadyRunningError,
    ECOSYSTEM_LOCK_PORT,
    ECOSYSTEM_LOCK_FILE,
    DEFAULT_LOCK_PORT,
    MUSIC_LOCK_PORT,
)


def clear_stale_instance(port: int, name: str, exclude_pids: set[int] | None = None):
    """Checks if a stale bot instance holds the lock port and terminates it if not in exclude_pids."""
    if exclude_pids is None:
        exclude_pids = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                if sys.platform == "win32":
                    try:
                        out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
                        for line in out.strip().splitlines():
                            parts = line.split()
                            if len(parts) >= 5 and "LISTENING" in parts:
                                pid = int(parts[-1])
                                if pid in exclude_pids:
                                    continue
                                print(f"[RECOVERY] Found stale {name} holding port {port} (PID: {pid}). Clearing process...")
                                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                                print(f"  • Terminated stale process PID {pid}.")
                                time.sleep(0.5)
                    except Exception:
                        pass
    except Exception:
        pass


def auto_heal_dependencies(base_dir: str, python_executable: str) -> None:
    """Computes requirements checksum and auto-installs dependencies on changes with zero manual work."""
    req_path = Path(base_dir) / "requirements-music.txt"
    if not req_path.exists():
        return
    import hashlib
    content = req_path.read_bytes()
    current_hash = hashlib.sha256(content).hexdigest()
    hash_file = Path(base_dir) / "data" / ".req_music_hash"

    saved_hash = ""
    if hash_file.exists():
        try:
            saved_hash = hash_file.read_text().strip()
        except Exception:
            pass

    if current_hash != saved_hash:
        print("[AUTO-HEAL] requirements-music.txt changed or initial run. Synchronizing dependencies...")
        try:
            res = subprocess.run(
                [python_executable, "-m", "pip", "install", "--no-cache-dir", "-q", "-r", "requirements-music.txt"],
                cwd=base_dir,
                capture_output=True,
                timeout=120,
            )
            if res.returncode == 0:
                hash_file.parent.mkdir(parents=True, exist_ok=True)
                hash_file.write_text(current_hash)
                print("  • Virtual environment dependencies verified & synchronized.")
            else:
                print(f"  • Pip note: {res.stderr.decode()[:150]}")
        except Exception as e:
            print(f"  • Pip self-healing notice: {e}")


def run():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    lock_path = Path(base_dir) / ECOSYSTEM_LOCK_FILE

    # Enforce single orchestrator instance
    orchestrator_lock = SingleInstanceLock(port=ECOSYSTEM_LOCK_PORT, lock_file=lock_path)
    try:
        orchestrator_lock.acquire()
    except InstanceAlreadyRunningError as e:
        print("=" * 65)
        print("✦ RAI ECOSYSTEM IS ALREADY RUNNING ✦")
        print(f"A master orchestrator is already active: {e}")
        print("Both The Raivora and Neko Songs are actively running in the background.")
        print("=" * 65)
        sys.exit(0)

    print("=" * 65)
    print("        ✦ RAI ECOSYSTEM — UNIFIED PROCESS ORCHESTRATOR ✦        ")
    print("   Starting The Raivora (Main Bot) & Neko Songs (Audio Bot)...  ")
    print("=" * 65)

    venv_py = os.path.join(base_dir, ".venv", "Scripts", "python.exe")
    python_executable = venv_py if os.path.exists(venv_py) else sys.executable

    # Pre-flight: Self-heal dependencies & clean stale lock artifacts
    auto_heal_dependencies(base_dir, python_executable)
    for lock_name in (".bot.lock", ".music_bot.lock"):
        lp = Path(base_dir) / lock_name
        if lp.exists():
            try:
                lp.unlink()
            except Exception:
                pass

    clear_stale_instance(MUSIC_LOCK_PORT, "MusicMaid")

    # 1. Spawn Primary Music Bot (MusicMaid)
    print("[1/1] 🐱 Spawning Raivora Music Maid (Primary Audio Engine)...")
    proc_music = subprocess.Popen(
        [python_executable, "main.py"],
        cwd=base_dir,
    )

    print(f"\n✅ MusicMaid running! (PID: {proc_music.pid})")
    print("Press Ctrl+C to gracefully stop.\n")

    music_restarts: list[float] = []

    try:
        MAX_BURST_RESTARTS = 5
        while True:
            now = time.time()
            ret_music = proc_music.poll()

            if ret_music is not None:
                music_restarts = [t for t in music_restarts if now - t < 60]
                if len(music_restarts) >= MAX_BURST_RESTARTS:
                    print(f"\n🛑 [BOUNDED RECOVERY] MusicMaid crashed {len(music_restarts)} times in 60s. Pausing 45s cooldown to prevent restart loop...")
                    time.sleep(45)
                    music_restarts.clear()
                backoff = 15 if len(music_restarts) >= 3 else 3
                print(f"\n⚠️ MusicMaid exited (code {ret_music}). Auto-recovering in {backoff}s...")
                time.sleep(backoff)
                clear_stale_instance(MUSIC_LOCK_PORT, "MusicMaid")
                proc_music = subprocess.Popen([python_executable, "main.py"], cwd=base_dir)
                music_restarts.append(time.time())
                print(f"🐱 MusicMaid respawned successfully (PID: {proc_music.pid}).")

            time.sleep(2)

            if ret_music is not None:
                music_restarts = [t for t in music_restarts if now - t < 60]
                if len(music_restarts) >= MAX_BURST_RESTARTS:
                    print(f"\n🛑 [BOUNDED RECOVERY] Neko Songs crashed {len(music_restarts)} times in 60s. Pausing 45s cooldown to prevent restart loop...")
                    time.sleep(45)
                    music_restarts.clear()
                backoff = 15 if len(music_restarts) >= 3 else 3
                print(f"\n⚠️ Neko Songs exited (code {ret_music}). Auto-recovering in {backoff}s...")
                time.sleep(backoff)
    except KeyboardInterrupt:
        print("\n🛑 Stopping Rai Ecosystem...")
    finally:
        if proc_music and proc_music.poll() is None:
            print(f"Terminating MusicMaid (PID: {proc_music.pid})...")
            proc_music.terminate()
            try:
                proc_music.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc_music.kill()
        orchestrator_lock.release()
        print("✦ Rai Ecosystem stopped cleanly.")


if __name__ == "__main__":
    run()
