"""Utilities for validating and preparing user-selected Discord emoji packs.

The project does not redistribute third-party emoji artwork. Users download a pack
from its publisher and explicitly choose which files to upload to their own server.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Iterable

SUPPORTED_SUFFIXES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
DISCORD_EMOJI_MAX_BYTES = 256 * 1024


def emoji_name(filename: str, *, max_length: int = 32) -> str:
    """Convert a filename to a Discord-compatible emoji name."""
    stem = Path(filename).stem.lower()
    normalized = re.sub(r"[^a-z0-9_]+", "_", stem).strip("_")
    normalized = re.sub(r"_+", "_", normalized)[:max_length].strip("_")
    if len(normalized) < 2:
        normalized = (normalized + "_emoji")[:max_length]
    return normalized


def image_data_uri(filename: str, data: bytes) -> str:
    """Validate an emoji image and return the data URI expected by Discord's API."""
    mime = SUPPORTED_SUFFIXES.get(Path(filename).suffix.lower())
    if mime is None:
        raise ValueError(f"Unsupported emoji image format: {Path(filename).suffix or '(none)'}")
    if not data:
        raise ValueError("Emoji image is empty")
    if len(data) >= DISCORD_EMOJI_MAX_BYTES:
        raise ValueError("Emoji image must be smaller than 256 KiB")
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def eligible_images(paths: Iterable[Path]) -> list[Path]:
    """Return supported image files in deterministic order; ignore hidden files."""
    return sorted(
        (p for p in paths if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in SUPPORTED_SUFFIXES),
        key=lambda p: p.name.lower(),
    )
