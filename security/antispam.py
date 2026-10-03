"""
Anti-Spam Filter and Content Inspector for Rai.
Provides regex scanning, sliding windows, and escalating penalty evaluation.
"""

from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Tuple

INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/[a-zA-Z0-9]+",
    re.IGNORECASE,
)
SUSPICIOUS_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:[a-zA-Z0-9-]+\.)*(?:steamcomm[a-z0-9-]*\.com|discorcd[a-z0-9-]*\.com|dlscord[a-z0-9-]*\.com|discord-nitro[a-z0-9-]*\.[a-z]+|gift-nitro[a-z0-9-]*\.[a-z]+|free-nitro[a-z0-9-]*\.[a-z]+)",
    re.IGNORECASE,
)
EMOJI_REGEX = re.compile(r"<a?:[a-zA-Z0-9_]+:[0-9]+>")
UNICODE_EMOJI_REGEX = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50\u2b55]"
)


class ContentInspector:
    """Synchronous, non-blocking string inspection methods."""

    @staticmethod
    def contains_invite(text: str) -> bool:
        return bool(INVITE_REGEX.search(text))

    @staticmethod
    def contains_phishing(text: str) -> bool:
        return bool(SUSPICIOUS_REGEX.search(text))

    @staticmethod
    def count_emojis(text: str) -> int:
        return len(EMOJI_REGEX.findall(text)) + len(UNICODE_EMOJI_REGEX.findall(text))

    @staticmethod
    def calculate_caps_ratio(text: str) -> float:
        letters = [c for c in text if c.isalpha()]
        if not letters or len(letters) < 12:
            return 0.0
        return sum(1 for c in letters if c.isupper()) / len(letters)

    @staticmethod
    def matches_banned_words(text: str, banned_list: List[str]) -> Optional[str]:
        lower_content = text.lower()
        for word in banned_list:
            if word and re.search(rf"\b{re.escape(word)}\b", lower_content):
                return word
        return None
