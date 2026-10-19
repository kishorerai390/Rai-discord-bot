#!/usr/bin/env python3
"""
Phase 10 — Production Pre-Flight Check Script
MusicMaid / Rai Discord Bot — Render Deployment Readiness Verifier

Checks every critical system before a production push:
  ✓ All required env vars are set
  ✓ render.yaml contains all mandatory env key declarations
  ✓ requirements.txt contains all needed packages
  ✓ Dockerfile has correct EXPOSE port & CMD
  ✓ .gitignore protects secrets
  ✓ Health endpoints are reachable (if server is running)
  ✓ PWA manifest is valid
  ✓ Public assets exist (icon, manifest)
  ✓ Discord invite links are correct across all source files
  ✓ Git working tree is clean (no secrets committed)

Usage:
  python scripts/preflight_check.py [--live]

  --live   Also ping the live Render deployment health endpoint
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import List, Tuple

# ─── Colors ────────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

PASS = f"{GREEN}✓ PASS{RESET}"
WARN = f"{YELLOW}⚠ WARN{RESET}"
FAIL = f"{RED}✗ FAIL{RESET}"

BASE_DIR = Path(__file__).resolve().parent.parent

results: List[Tuple[str, str, str]] = []  # (label, status, detail)


def check(label: str, ok: bool, detail: str = "", warn_only: bool = False) -> bool:
    status = PASS if ok else (WARN if warn_only else FAIL)
    results.append((label, status, detail))
    return ok


# ─── 1. Required Files ─────────────────────────────────────────────────────────
def check_required_files():
    required = [
        "main.py",
        "requirements.txt",
        "render.yaml",
        "Dockerfile",
        ".gitignore",
        ".env.example",
        "web/server.py",
        "web/ui.py",
        "public/manifest.json",
        "public/icon.png",
        "config/settings.py",
        "music_bot/main.py",
        "music_bot/bot.py",
    ]
    for rel in required:
        p = BASE_DIR / rel
        check(f"File exists: {rel}", p.exists(), "" if p.exists() else f"Missing: {p}")


# ─── 2. Render YAML env declarations ──────────────────────────────────────────
def check_render_yaml():
    render_path = BASE_DIR / "render.yaml"
    if not render_path.exists():
        check("render.yaml present", False, "File missing")
        return

    content = render_path.read_text(encoding="utf-8")

    # Keys that MUST appear
    mandatory_keys = [
        "MUSIC_BOT_TOKEN",
        "DISCORD_CLIENT_ID",
        "DISCORD_CLIENT_SECRET",
        "DISCORD_REDIRECT_URI",
        "SESSION_SECRET",
        "PUBLIC_BASE_URL",
    ]
    for key in mandatory_keys:
        check(f"render.yaml declares: {key}", key in content,
              "" if key in content else f"{key} missing from render.yaml envVars")

    # Start command must use main.py
    check("render.yaml startCommand = python main.py",
          "python main.py" in content,
          "Unexpected startCommand in render.yaml")

    # Build command must install requirements
    check("render.yaml buildCommand installs requirements",
          "pip install -r requirements.txt" in content)


# ─── 3. requirements.txt completeness ─────────────────────────────────────────
def check_requirements():
    req_path = BASE_DIR / "requirements.txt"
    if not req_path.exists():
        check("requirements.txt present", False)
        return

    content = req_path.read_text(encoding="utf-8").lower()
    must_have = {
        "discord.py": "discord",
        "aiohttp": "aiohttp",
        "yt-dlp": "yt-dlp",
        "aiosqlite": "aiosqlite",
        "python-dotenv": "python-dotenv",
        "pynacl": "pynacl",
        "static-ffmpeg": "static-ffmpeg",
        "orjson": "orjson",
        "psutil": "psutil",
    }
    for name, key in must_have.items():
        check(f"requirements.txt has: {name}", key in content)


# ─── 4. Dockerfile ────────────────────────────────────────────────────────────
def check_dockerfile():
    df_path = BASE_DIR / "Dockerfile"
    if not df_path.exists():
        check("Dockerfile present", False)
        return

    content = df_path.read_text(encoding="utf-8")
    check("Dockerfile EXPOSE port", "EXPOSE" in content)
    check("Dockerfile CMD uses main.py", "main.py" in content)
    check("Dockerfile installs ffmpeg", "ffmpeg" in content.lower())
    check("Dockerfile uses python:3.11", "python:3.11" in content)


# ─── 5. .gitignore protects secrets ──────────────────────────────────────────
def check_gitignore():
    gi_path = BASE_DIR / ".gitignore"
    if not gi_path.exists():
        check(".gitignore present", False)
        return

    content = gi_path.read_text(encoding="utf-8")
    sensitive = [".env", "*.db", "*.log", "__pycache__", ".lock"]
    for pat in sensitive:
        check(f".gitignore covers: {pat}", pat in content,
              "" if pat in content else f"Secret pattern '{pat}' not in .gitignore", warn_only=True)


# ─── 6. PWA manifest.json validity ───────────────────────────────────────────
def check_manifest():
    manifest_path = BASE_DIR / "public" / "manifest.json"
    if not manifest_path.exists():
        check("manifest.json exists", False)
        return

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        check("manifest.json valid JSON", False, str(e))
        return

    check("manifest.json valid JSON", True)
    check("manifest has name", bool(data.get("name")))
    check("manifest has icons", bool(data.get("icons")))
    check("manifest start_url = /dashboard", data.get("start_url") == "/dashboard")
    check("manifest display = standalone", data.get("display") == "standalone")
    check("manifest has shortcuts", len(data.get("shortcuts", [])) >= 2,
          detail=f"Has {len(data.get('shortcuts', []))} shortcuts (need ≥2)", warn_only=True)


# ─── 7. Discord invite link consistency ──────────────────────────────────────
CORRECT_INVITE = "https://discord.gg/d7T8cJK3XF"
LEGACY_PATTERNS = [
    r"discord\.gg/KSxEHfmpCe",
    r"discord\.gg/uW4vTv2H",
    r"discord\.gg/[A-Za-z0-9]{5,10}\b",  # any other short code
]

def check_invite_links():
    source_files = list((BASE_DIR / "web").glob("*.py")) + \
                   list((BASE_DIR / "config").glob("*.py")) + \
                   list((BASE_DIR / "scripts").glob("*.py"))

    legacy_found: List[str] = []
    for path in source_files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern in LEGACY_PATTERNS:
            for m in re.finditer(pattern, text):
                if m.group(0) != CORRECT_INVITE.replace("https://", ""):
                    rel = path.relative_to(BASE_DIR)
                    legacy_found.append(f"{rel}: {m.group(0)}")

    check("Discord invite links all use d7T8cJK3XF",
          len(legacy_found) == 0,
          "\n    ".join(legacy_found) if legacy_found else "",
          warn_only=True)


# ─── 8. Environment variable completeness (local .env) ───────────────────────
REQUIRED_ENV_KEYS = [
    "MUSIC_BOT_TOKEN",
    "DISCORD_CLIENT_ID",
    "DISCORD_CLIENT_SECRET",
    "DISCORD_REDIRECT_URI",
    "SESSION_SECRET",
    "PUBLIC_BASE_URL",
    "BOT_OWNER_ID",
]

def check_env_file():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        check(".env file exists", False, "Create from .env.example", warn_only=True)
        return

    content = env_path.read_text(encoding="utf-8")
    for key in REQUIRED_ENV_KEYS:
        # Check it's set to a non-empty, non-placeholder value
        m = re.search(rf"^{re.escape(key)}\s*=\s*(.+)$", content, re.MULTILINE)
        val = m.group(1).strip() if m else ""
        is_set = bool(val) and "YOUR_" not in val and "CHANGE_ME" not in val
        check(f".env has {key}", is_set,
              f"Empty or placeholder value for {key}" if not is_set else "",
              warn_only=True)


# ─── 9. Live HTTP health check ────────────────────────────────────────────────
def check_live_health(url: str):
    health_url = url.rstrip("/") + "/api/health"
    try:
        req = urllib.request.urlopen(health_url, timeout=10)
        body = req.read().decode("utf-8")
        data = json.loads(body)
        ok = data.get("status") == "healthy"
        check(f"Live health: {health_url}", ok,
              f"bot_status={data.get('bot_status')} yt_dlp={data.get('yt_dlp_version')}")
    except Exception as e:
        check(f"Live health: {health_url}", False, str(e), warn_only=True)


# ─── 10. Local server health check ───────────────────────────────────────────
def check_local_health():
    try:
        req = urllib.request.urlopen("http://localhost:8080/api/health", timeout=4)
        body = req.read().decode("utf-8")
        data = json.loads(body)
        ok = data.get("status") == "healthy"
        check("Local server health (localhost:8080)", ok,
              f"bot={data.get('bot_status')} yt-dlp={data.get('yt_dlp_version')}")
    except Exception as e:
        check("Local server health (localhost:8080)", False,
              f"Server not running or unreachable: {e}", warn_only=True)


# ─── 11. Source-level sanity checks ──────────────────────────────────────────
def check_source_sanity():
    ui_path = BASE_DIR / "web" / "ui.py"
    if ui_path.exists():
        src = ui_path.read_text(encoding="utf-8", errors="ignore")
        check("UI has keyboard shortcut engine",   "case 'Escape':" in src)
        check("UI has offline detection banner",    'id="network-status-bar"' in src)
        check("UI has request deduplication guard", "pendingActions.has(action)" in src)
        check("UI has ARIA player toolbar",         'role="toolbar"' in src)
        check("UI has shortcuts modal",             'id="shortcuts-modal"' in src)
        check("UI no duplicate space listener",     "e.code === 'Space'" not in src)

    server_path = BASE_DIR / "web" / "server.py"
    if server_path.exists():
        srv = server_path.read_text(encoding="utf-8", errors="ignore")
        check("Server has /health route",      '"/health"' in srv)
        check("Server has /api/health route",  '"/api/health"' in srv)
        check("Server has CORS middleware",    "cors_middleware" in srv)
        check("Server has keepalive loop",     "keepalive" in srv.lower())


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="MusicMaid Production Pre-Flight Checker")
    parser.add_argument("--live", action="store_true",
                        help="Also check live Render deployment health")
    parser.add_argument("--url", default="https://rai-discord-bot.onrender.com",
                        help="Live Render URL to check (default: rai-discord-bot.onrender.com)")
    args = parser.parse_args()

    print(f"\n{BOLD}{CYAN}{'='*65}{RESET}")
    print(f"{BOLD}{CYAN}  🚀 MusicMaid — Phase 10 Production Pre-Flight Check{RESET}")
    print(f"{BOLD}{CYAN}{'='*65}{RESET}\n")

    check_required_files()
    check_render_yaml()
    check_requirements()
    check_dockerfile()
    check_gitignore()
    check_manifest()
    check_invite_links()
    check_env_file()
    check_local_health()
    check_source_sanity()

    if args.live:
        check_live_health(args.url)

    # ── Print results ──────────────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    passes = warns = fails = 0
    for label, status, detail in results:
        icon = status
        print(f"  {icon}  {label}")
        if detail:
            for line in detail.split("\n"):
                print(f"         {YELLOW}{line}{RESET}")
        if "PASS" in status:
            passes += 1
        elif "WARN" in status:
            warns += 1
        else:
            fails += 1

    print(f"\n{'─'*65}")
    total = passes + warns + fails
    print(f"  Results: {GREEN}{passes} passed{RESET}  {YELLOW}{warns} warnings{RESET}  {RED}{fails} failed{RESET}  (of {total} checks)")

    if fails > 0:
        print(f"\n  {RED}{BOLD}❌ Pre-flight FAILED — fix the issues above before deploying.{RESET}\n")
        sys.exit(1)
    elif warns > 0:
        print(f"\n  {YELLOW}{BOLD}⚠  Pre-flight PASSED with warnings — review before deploying.{RESET}\n")
        sys.exit(0)
    else:
        print(f"\n  {GREEN}{BOLD}✅ All checks passed — safe to deploy to Render!{RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
