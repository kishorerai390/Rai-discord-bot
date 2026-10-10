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

    # Pre-flight: Clear any stale orphan processes on dedicated bot ports
    clear_stale_instance(DEFAULT_LOCK_PORT, "The Raivora")
    clear_stale_instance(MUSIC_LOCK_PORT, "Neko Songs")

    # 1. Spawn Main Bot (The Raivora)
    print("[1/2] 🚀 Spawning The Raivora (Core, Security, Moderation)...")
    proc_main = subprocess.Popen(
        [python_executable, "main.py"],
        cwd=base_dir,
    )

    # 2. Short pause to allow main bot DB migrations to settle
    time.sleep(2)

    # 3. Spawn Music Bot (Neko Songs)
    print("[2/2] 🐱 Spawning Neko Songs (Dedicated Audio Companion)...")
    proc_music = subprocess.Popen(
        [python_executable, "music_main.py"],
        cwd=base_dir,
    )

    print(f"\n✅ Both bot processes running! (Raivora PID: {proc_main.pid}, Neko Songs PID: {proc_music.pid})")
    print("Press Ctrl+C to gracefully stop the entire ecosystem.\n")

    main_restarts: list[float] = []
    music_restarts: list[float] = []

    try:
        while True:
            now = time.time()
            ret_main = proc_main.poll()
            ret_music = proc_music.poll()

            if ret_main is not None:
                main_restarts = [t for t in main_restarts if now - t < 60]
                backoff = 15 if len(main_restarts) >= 3 else 3
                print(f"\n⚠️ The Raivora exited (code {ret_main}). Auto-recovering in {backoff}s...")
                time.sleep(backoff)
                clear_stale_instance(DEFAULT_LOCK_PORT, "The Raivora", exclude_pids={proc_music.pid})
                proc_main = subprocess.Popen([python_executable, "main.py"], cwd=base_dir)
                main_restarts.append(time.time())
                print(f"🚀 The Raivora respawned successfully (PID: {proc_main.pid}).")

            if ret_music is not None:
                music_restarts = [t for t in music_restarts if now - t < 60]
                backoff = 15 if len(music_restarts) >= 3 else 3
                print(f"\n⚠️ Neko Songs exited (code {ret_music}). Auto-recovering in {backoff}s...")
                time.sleep(backoff)
                clear_stale_instance(MUSIC_LOCK_PORT, "Neko Songs", exclude_pids={proc_main.pid})
                proc_music = subprocess.Popen([python_executable, "music_main.py"], cwd=base_dir)
                music_restarts.append(time.time())
                print(f"🐱 Neko Songs respawned successfully (PID: {proc_music.pid}).")

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n🛑 Stopping Rai Ecosystem...")
    finally:
        for name, p in [("Neko Songs", proc_music), ("The Raivora", proc_main)]:
            if p and p.poll() is None:
                print(f"Terminating {name} (PID: {p.pid})...")
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        orchestrator_lock.release()
        print("✦ Rai Ecosystem stopped cleanly.")


if __name__ == "__main__":
    run()
