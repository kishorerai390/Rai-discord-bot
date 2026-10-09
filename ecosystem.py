"""
Unified Dual-Bot Ecosystem Launcher for Rai.
Spawns both The Raivora (Security/Moderation) and Neko Songs (Music Bot)
as concurrent subprocesses with synchronized logging and graceful shutdown.
Run with: python ecosystem.py (or npm start)
"""

import os
import signal
import subprocess
import sys
import time

def run():
    print("=" * 65)
    print("        ✦ RAI ECOSYSTEM — UNIFIED PROCESS ORCHESTRATOR ✦        ")
    print("   Starting The Raivora (Main Bot) & Neko Songs (Audio Bot)...  ")
    print("=" * 65)

    python_executable = sys.executable

    # 1. Spawn Main Bot (The Raivora)
    print("[1/2] 🚀 Spawning The Raivora (Core, Security, Moderation)...")
    proc_main = subprocess.Popen(
        [python_executable, "main.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    # 2. Short pause to allow main bot DB migrations to settle
    time.sleep(2)

    # 3. Spawn Music Bot (Neko Songs)
    print("[2/2] 🐱 Spawning Neko Songs (Dedicated Audio Companion)...")
    proc_music = subprocess.Popen(
        [python_executable, "music_main.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
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
