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

def clear_stale_instance(port: int, name: str):
    """Checks if a stale bot instance holds the lock port and terminates it."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                print(f"[RECOVERY] Found stale {name} holding port {port}. Clearing process...")
                if sys.platform == "win32":
                    try:
                        out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
                        for line in out.strip().splitlines():
                            parts = line.split()
                            if len(parts) >= 5 and "LISTENING" in parts:
                                pid = parts[-1]
                                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                                print(f"  • Terminated stale process PID {pid}.")
                                time.sleep(0.5)
                    except Exception:
                        pass
    except Exception:
        pass


def run():
    print("=" * 65)
    print("        ✦ RAI ECOSYSTEM — UNIFIED PROCESS ORCHESTRATOR ✦        ")
    print("   Starting The Raivora (Main Bot) & Neko Songs (Audio Bot)...  ")
    print("=" * 65)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_py = os.path.join(base_dir, ".venv", "Scripts", "python.exe")
    python_executable = venv_py if os.path.exists(venv_py) else sys.executable

    # Pre-flight: Clear any stale orphan processes on dedicated lock ports
    clear_stale_instance(49451, "The Raivora")
    clear_stale_instance(49452, "Neko Songs")

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

    print("\n✅ Both bot processes running concurrently! Press Ctrl+C to stop both.\n")

    try:
        while True:
            # Check if any process terminated unexpectedly
            ret_main = proc_main.poll()
            ret_music = proc_music.poll()

            if ret_main is not None:
                print(f"\n⚠️ The Raivora exited with code {ret_main}.")
                break
            if ret_music is not None:
                print(f"\n⚠️ Neko Songs exited with code {ret_music}.")
                break

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Shutting down Rai Ecosystem processes...")
    finally:
        for name, p in [("Neko Songs", proc_music), ("The Raivora", proc_main)]:
            if p.poll() is None:
                print(f"Terminating {name} (PID: {p.pid})...")
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        print("✦ Rai Ecosystem gracefully stopped.")

if __name__ == "__main__":
    run()
