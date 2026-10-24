"""
Utility script to trigger a fresh Render deployment via the configured Deploy Hook.
Reads RENDER_DEPLOY_HOOK_URL from .env without exposing credentials in code.
"""

import os
import sys
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

hook_url = os.getenv("RENDER_DEPLOY_HOOK_URL")
if not hook_url:
    print("[ERROR] RENDER_DEPLOY_HOOK_URL is not set in .env")
    sys.exit(1)

try:
    req = urllib.request.Request(hook_url, method="POST")
    with urllib.request.urlopen(req, timeout=15) as response:
        status = response.status
        body = response.read().decode("utf-8", errors="replace")
        print(f"[SUCCESS] Render deployment triggered successfully! (HTTP {status})")
        if body:
            print(f"Response: {body.strip()}")
except Exception as e:
    print(f"[ERROR] Failed to trigger Render deploy hook: {e}")
    sys.exit(1)
