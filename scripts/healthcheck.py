"""
System and Bot Runtime Health Check.
Checks Python version, package dependencies, environment, SQLite integrity,
table schema, and system tools (FFmpeg).
Exit codes:
0 = healthy
1 = warning/non-critical issue (e.g. FFmpeg missing, unconfigured token)
2 = critical failure
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import aiosqlite
import config
from config import DATABASE_PATH, is_token_valid, get_masked_token


async def run_health_checks() -> int:
    print("=" * 45)
    print("          RAI HEALTH CHECK")
    print("=" * 45)

    has_warning = False
    has_critical = False

    # 1. Python version check
    py_ver = sys.version_info
    if py_ver >= (3, 11):
        print(f"[OK] Python Version: {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    else:
        print(f"[CRITICAL] Python Version {py_ver.major}.{py_ver.minor} < 3.11")
        has_critical = True

    # 2. Package Dependencies Check
    required_packages = ["discord", "aiosqlite", "dotenv", "nacl", "yt_dlp"]
    for pkg in required_packages:
        try:
            __import__(pkg)
            print(f"[OK] Python Package: {pkg}")
        except ImportError:
            print(f"[CRITICAL] Missing Python Package: {pkg}")
            has_critical = True

    # 3. Environment & Token Check
    if (BASE_DIR / ".env").exists():
        print("[OK] Environment File: .env found")
    else:
        print("[WARNING] Environment File: .env missing (will use defaults or .env.example)")
        has_warning = True

    if is_token_valid():
        print(f"[OK] Discord Token: Configured ({get_masked_token()})")
    else:
        print(f"[WARNING] Discord Token: Not configured ({get_masked_token()})")
        has_warning = True

    # 4. Directories Check
    for d in (config.DATA_DIR, config.BACKUPS_DIR, config.LOGS_DIR, config.TRANSCRIPTS_DIR):
        if d.exists() and os.access(d, os.W_OK):
            print(f"[OK] Directory Writable: {d.relative_to(BASE_DIR)}")
        else:
            print(f"[CRITICAL] Directory Unwritable or Missing: {d.relative_to(BASE_DIR)}")
            has_critical = True

    # 5. Database & SQLite Integrity
    if not DATABASE_PATH.exists():
        print(f"[WARNING] Database does not exist yet at {DATABASE_PATH.name} (run init.py to create)")
        has_warning = True
    else:
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                db.row_factory = aiosqlite.Row
                # Integrity check
                async with db.execute("PRAGMA integrity_check;") as cur:
                    rows = await cur.fetchall()
                    if all(r[0] == "ok" for r in rows):
                        print("[OK] SQLite Database Integrity: OK")
                    else:
                        print(f"[CRITICAL] SQLite Integrity Issues: {rows}")
                        has_critical = True

                # Foreign keys
                async with db.execute("PRAGMA foreign_key_check;") as cur:
                    fk_rows = await cur.fetchall()
                    if not fk_rows:
                        print("[OK] SQLite Foreign Keys: OK")
                    else:
                        print(f"[CRITICAL] Foreign key violations: {len(fk_rows)}")
                        has_critical = True

                # Required tables check
                required_tables = [
                    "schema_version",
                    "guild_config",
                    "security_config",
                    "security_whitelist",
                    "security_incidents",
                    "security_state",
                    "rate_limit_config",
                    "persistent_cooldowns",
                    "violation_history",
                    "moderation_warnings",
                    "welcome_config",
                    "logging_config",
                    "ticket_config",
                    "tickets",
                    "bot_config",
                    "automod_config",
                    "fun_config",
                    "fun_user_stats",
                ]
                async with db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table';"
                ) as cur:
                    existing = [r[0] for r in await cur.fetchall()]
                    missing_tables = [t for t in required_tables if t not in existing]
                    if not missing_tables:
                        print(f"[OK] Database Schema: All {len(required_tables)} tables present")
                    else:
                        print(f"[CRITICAL] Missing Database Tables: {missing_tables}")
                        has_critical = True
        except Exception as e:
            print(f"[CRITICAL] Database connection error: {e}")
            has_critical = True

    # 6. FFmpeg availability
    if shutil.which("ffmpeg"):
        print("[OK] FFmpeg: Installed and accessible on PATH")
    else:
        print("[WARNING] FFmpeg: Not found on system PATH (Music playback will be unavailable until installed)")
        has_warning = True

    print("=" * 45)
    if has_critical:
        print("HEALTH STATUS: CRITICAL (Exit Code 2)")
        return 2
    elif has_warning:
        print("HEALTH STATUS: WARNING (Exit Code 1)")
        return 1
    else:
        print("HEALTH STATUS: HEALTHY (Exit Code 0)")
        return 0


def main():
    code = asyncio.run(run_health_checks())
    sys.exit(code)


if __name__ == "__main__":
    main()
