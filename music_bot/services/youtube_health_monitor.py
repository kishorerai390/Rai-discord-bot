"""Safe health monitoring for YouTube cookies and upstream extraction failures.

This module never obtains, exports, or refreshes credentials. It only inspects the
configured cookie file's metadata and applies a process-local cooldown after
upstream failures so the resolver does not amplify rate limits.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("RaiMusic.YouTubeHealth")

_LOCK = threading.Lock()
_COOLDOWN_UNTIL = 0.0
_LAST_FAILURE = "none"
_LAST_FAILURE_AT = 0.0
_LAST_COOKIE_SIGNATURE: Optional[tuple] = None
_LAST_STATUS_LOGGED: Optional[str] = None
_RATE_LIMIT_COOLDOWN_SECONDS = max(60, int(os.getenv("YOUTUBE_RATE_LIMIT_COOLDOWN_SECONDS", "900")))
_ACCESS_COOLDOWN_SECONDS = max(30, int(os.getenv("YOUTUBE_ACCESS_COOLDOWN_SECONDS", "180")))
_TIMEOUT_COOLDOWN_SECONDS = max(30, int(os.getenv("YOUTUBE_TIMEOUT_COOLDOWN_SECONDS", "120")))


def inspect_cookie_file(path: Optional[str]) -> Dict[str, Any]:
    """Return safe cookie health metadata; never return cookie values."""
    global _LAST_COOKIE_SIGNATURE, _LAST_STATUS_LOGGED
    if not path:
        status = "missing"
        result = {"status": status, "present": False, "readable": False, "size_bytes": 0,
                  "expired_auth_tokens": 0, "summary": "No cookie file configured"}
    else:
        file_path = Path(path)
        try:
            if not file_path.is_file() or file_path.stat().st_size == 0:
                status = "missing"
                result = {"status": status, "present": False, "readable": False, "size_bytes": 0,
                          "expired_auth_tokens": 0, "summary": "Cookie file missing or empty"}
            else:
                size = file_path.stat().st_size
                content = file_path.read_text(encoding="utf-8", errors="replace")
                now = time.time()
                auth_names = {"SAPISID", "__Secure-3PSID", "__Secure-1PSID", "LOGIN_INFO", "SID", "HSID", "SSID"}
                auth_found = set()
                expired = set()
                netscape_rows = 0
                for line in content.splitlines():
                    if not line.strip() or line.lstrip().startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        netscape_rows += 1
                        name = parts[5]
                        if name in auth_names:
                            auth_found.add(name)
                            try:
                                expiry = float(parts[4])
                                if 0 < expiry < now:
                                    expired.add(name)
                            except (TypeError, ValueError):
                                pass
                if not content.strip() or netscape_rows == 0:
                    status = "malformed"
                    summary = "Cookie file is unreadable as a Netscape-format cookie file"
                elif expired and auth_found and expired == auth_found:
                    status = "expired"
                    summary = "All detected authentication cookies are expired"
                elif expired:
                    status = "partially_expired"
                    summary = "Some detected authentication cookies are expired"
                elif not auth_found:
                    status = "present_unverified"
                    summary = "Cookie file exists; no common authentication cookies could be verified"
                else:
                    status = "present_unverified"
                    summary = "Cookie file structure looks readable; YouTube session acceptance is not verified"
                result = {"status": status, "present": True, "readable": True, "size_bytes": size,
                          "expired_auth_tokens": len(expired), "summary": summary}
        except OSError:
            status = "unreadable"
            result = {"status": status, "present": True, "readable": False, "size_bytes": 0,
                      "expired_auth_tokens": 0, "summary": "Cookie file exists but cannot be read"}
    signature = (result["status"], result["present"], result["readable"], result["size_bytes"],
                 result["expired_auth_tokens"])
    with _LOCK:
        changed = signature != _LAST_COOKIE_SIGNATURE
        _LAST_COOKIE_SIGNATURE = signature
    if changed:
        logger.info("[YouTubeHealth] cookie_status=%s present=%s readable=%s size_bytes=%s expired_auth_tokens=%s summary=%s",
                    result["status"], result["present"], result["readable"], result["size_bytes"],
                    result["expired_auth_tokens"], result["summary"])
    return result


def record_failure(error: str) -> str:
    """Classify an upstream failure and start a bounded cooldown when appropriate."""
    global _COOLDOWN_UNTIL, _LAST_FAILURE, _LAST_FAILURE_AT, _LAST_STATUS_LOGGED
    lower = (error or "").lower()
    if "429" in lower or "too many requests" in lower or "rate limit" in lower:
        category, cooldown = "rate_limited", _RATE_LIMIT_COOLDOWN_SECONDS
    elif "403" in lower or "forbidden" in lower or "sign in" in lower or "captcha" in lower or "bot" in lower:
        category, cooldown = "access_denied", _ACCESS_COOLDOWN_SECONDS
    elif "timeout" in lower or "timed out" in lower:
        category, cooldown = "timeout", _TIMEOUT_COOLDOWN_SECONDS
    else:
        category, cooldown = "resolution_error", 0
    now = time.monotonic()
    with _LOCK:
        _LAST_FAILURE = category
        _LAST_FAILURE_AT = time.time()
        if cooldown:
            _COOLDOWN_UNTIL = max(_COOLDOWN_UNTIL, now + cooldown)
        remaining = max(0, int(_COOLDOWN_UNTIL - now))
        status_key = f"{category}:{remaining > 0}"
        should_log = status_key != _LAST_STATUS_LOGGED
        _LAST_STATUS_LOGGED = status_key
    if should_log:
        logger.warning("[YouTubeHealth] failure_category=%s cooldown_seconds=%s; no automatic credential refresh attempted",
                       category, remaining)
    return category


def cooldown_status() -> Dict[str, Any]:
    """Snapshot current health without exposing any credential data."""
    now_mono = time.monotonic()
    with _LOCK:
        remaining = max(0, int(_COOLDOWN_UNTIL - now_mono))
        return {"last_failure": _LAST_FAILURE, "last_failure_at": _LAST_FAILURE_AT or None,
                "cooldown_active": remaining > 0, "cooldown_remaining_seconds": remaining}
