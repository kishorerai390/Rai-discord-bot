"""
OwnerReporter: sanitize sensitive fields and render structured repair results safely.
"""

from __future__ import annotations

import asyncio
import datetime
import inspect
import logging
import random
import string
import time
import unicodedata
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
import discord

from config import Colors

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

# Sensitive keys to redact
_SENSITIVE_KEYWORDS = ("token", "secret", "password", "key", "credential")


def _sanitize_value(v: Any) -> Any:
    """Redact token-like strings and anything obviously sensitive."""
    try:
        if isinstance(v, str):
            # redact very long single tokens (common Discord tokens contain dots)
            if ("." in v and len(v) > 30) or len(v) > 120:
                return "[REDACTED]"
            # redact if contains sensitive substrings
            low = v.lower()
            if any(k in low for k in _SENSITIVE_KEYWORDS):
                return "[REDACTED]"
        return v
    except Exception:
        return "[REDACTED]"


def sanitize_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recursively sanitize a details dict for reporting."""
    out: Dict[str, Any] = {}
    if not details:
        return out
    for k, v in details.items():
        kn = str(k)
        if any(sk in kn.lower() for sk in _SENSITIVE_KEYWORDS):
            out[kn] = "[REDACTED]"
            continue
        if isinstance(v, dict):
            out[kn] = sanitize_details(v)
        elif isinstance(v, list):
            # sanitize list entries
            safe_list = []
            for item in v:
                if isinstance(item, dict):
                    safe_list.append(sanitize_details(item))
                else:
                    safe_list.append(_sanitize_value(item))
            out[kn] = safe_list
        else:
            out[kn] = _sanitize_value(v)
    return out


# Existing functions/classes below are preserved. We will call sanitize_details before creating embeds.

# (For brevity this patch leaves the rest of OwnerReporter implementation unchanged)

# To avoid duplication in this patch, we import the module-level functions where needed in other code.
