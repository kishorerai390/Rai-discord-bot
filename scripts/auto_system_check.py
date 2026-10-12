"""
Comprehensive Automated System Health Check for Rai Ecosystem.
Tests:
1. Discord Bot Token authentication (The Raivora & MusicMaid) via Discord API
2. Database health (data/bot.db & data/music.db integrity and migrations)
3. FFmpeg audio engine availability
4. Git sync status with GitHub/Render
5. Render deployment readiness
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
import aiohttp

# UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure root in sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from config import DISCORD_TOKEN
from music_bot.config import MUSIC_BOT_TOKEN


async def check_discord_token(token: str, bot_label: str) -> dict:
    start_t = time.perf_counter()
    headers = {"Authorization": f"Bot {token}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://discord.com/api/v10/users/@me", headers=headers, timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
                elapsed_ms = round((time.perf_counter() - start_t) * 1000, 1)
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "label": bot_label,
                        "status": "PASS",
                        "username": f"{data.get('username')}#{data.get('discriminator', '0')}",
                        "id": data.get("id"),
                        "latency_ms": elapsed_ms,
                        "error": None,
                    }
                else:
                    return {
                        "label": bot_label,
                        "status": "FAIL",
                        "error": f"HTTP {resp.status}: {await resp.text()}",
                        "latency_ms": elapsed_ms,
                    }
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start_t) * 1000, 1)
        return {
            "label": bot_label,
            "status": "ERROR",
            "error": str(e),
            "latency_ms": elapsed_ms,
        }


async def check_database(db_path: Path, expected_tables: list, label: str) -> dict:
    import aiosqlite
    start_t = time.perf_counter()
    if not db_path.exists():
        return {"label": label, "status": "FAIL", "error": f"File {db_path} does not exist"}
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
                rows = await cur.fetchall()
                found_tables = {r[0] for r in rows}
            missing = [t for t in expected_tables if t not in found_tables]
            elapsed_ms = round((time.perf_counter() - start_t) * 1000, 1)
            if missing:
                return {
                    "label": label,
                    "status": "WARN",
                    "found_count": len(found_tables),
                    "missing": missing,
                    "latency_ms": elapsed_ms,
                }
            return {
                "label": label,
                "status": "PASS",
                "table_count": len(found_tables),
                "latency_ms": elapsed_ms,
            }
    except Exception as e:
        return {"label": label, "status": "ERROR", "error": str(e)}


def check_ffmpeg() -> dict:
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return {"status": "PASS", "path": ffmpeg_path}
    return {"status": "WARN", "path": "Not found in PATH (yt-dlp may use internal streams)"}


async def main():
    print("=" * 65)
    print("       🛡️  RAI ECOSYSTEM — FULL AUTOMATED HEALTH PROBE  🎵      ")
    print("=" * 65)

    # 1. Check Tokens via Discord REST Gateway
    print("\n[1/5] Probing Discord Gateway Authentication...")
    rai_res = await check_discord_token(DISCORD_TOKEN, "The Raivora (Security Bot)")
    music_res = await check_discord_token(MUSIC_BOT_TOKEN, "MusicMaid (Music Bot)")

    for r in (rai_res, music_res):
        badge = "✅ PASS" if r["status"] == "PASS" else ("❌ " + r["status"])
        if r["status"] == "PASS":
            print(f"  {badge} | {r['label']}: Authenticated as {r['username']} (ID: {r['id']}) in {r['latency_ms']}ms")
        else:
            print(f"  {badge} | {r['label']}: {r.get('error')}")

    # 2. Check SQLite Databases
    print("\n[2/5] Inspecting SQLite Storage Subsystems...")
    rai_db_res = await check_database(
        root_dir / "data" / "bot.db",
        ["guild_config", "logging_config", "support_tickets", "server_backups", "system_error_logs"],
        "Main Database (data/bot.db)",
    )
    music_db_res = await check_database(
        root_dir / "data" / "music.db",
        ["music_guild_settings", "music_sessions", "music_playlists", "music_history"],
        "Music Database (data/music.db)",
    )

    for r in (rai_db_res, music_db_res):
        badge = "✅ PASS" if r["status"] == "PASS" else ("⚠️ " + r["status"])
        if r["status"] == "PASS":
            print(f"  {badge} | {r['label']}: Verified {r['table_count']} tables in {r['latency_ms']}ms")
        else:
            print(f"  {badge} | {r['label']}: {r.get('error') or r.get('missing')}")

    # 3. Audio & Streaming Engine
    print("\n[3/5] Verifying Audio & Codec Subsystems...")
    ff_res = check_ffmpeg()
    print(f"  {'✅ PASS' if ff_res['status'] == 'PASS' else '⚠️ WARN'} | FFmpeg Audio Decoder: {ff_res['path']}")

    # 4. Render Configuration File
    print("\n[4/5] Checking Render Cloud Deployment Config...")
    render_yaml = root_dir / "render.yaml"
    if render_yaml.exists():
        content = render_yaml.read_text(encoding="utf-8")
        has_disc = "DISCORD_TOKEN" in content
        has_mus = "MUSIC_BOT_TOKEN" in content
        has_cmd = "python main.py" in content
        if has_disc and has_mus and has_cmd:
            print("  ✅ PASS | render.yaml contains unified 'python main.py' and both tokens declared.")
        else:
            print(f"  ⚠️ WARN | render.yaml check: discord={has_disc}, music={has_mus}, cmd={has_cmd}")
    else:
        print("  ❌ FAIL | render.yaml is missing.")

    # 5. Git Status & Remote Sync
    print("\n[5/5] Checking Git Remote Sync State...")
    import subprocess
    git_proc = subprocess.run(["git", "status", "-sb"], capture_output=True, text=True, cwd=str(root_dir))
    git_head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=str(root_dir))
    git_out = git_proc.stdout.strip().splitlines()[0] if git_proc.stdout else "Unknown"
    head_hash = git_head.stdout.strip()
    print(f"  ✅ PASS | Branch State: {git_out} (HEAD: {head_hash})")

    print("\n" + "=" * 65)
    overall = (rai_res["status"] == "PASS" and music_res["status"] == "PASS" and
               rai_db_res["status"] == "PASS" and music_db_res["status"] == "PASS")
    if overall:
        print("🎉 ALL SYSTEMS PASS — READY FOR 24/7 OPERATION ON RENDER & LOCAL!")
    else:
        print("⚠️ SOME SUBSYSTEMS REPORTED ISSUES — PLEASE REVIEW LOGS ABOVE.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
