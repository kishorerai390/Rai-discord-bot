"""
Audio Track Search and Stream Resolution Engine for Rai Music Bot.
Operates asynchronously with yt-dlp in a thread pool to avoid blocking the event loop.
Engineered for YouTube-only audio resolution and Spotify metadata identification.
SoundCloud is completely disabled.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from difflib import SequenceMatcher
import functools
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import traceback
import urllib.parse
import uuid
import weakref
from typing import Any, Dict, List, Optional, Tuple

import yt_dlp

from music_bot.config import REDIS_URL
from music_bot.database.models import QueuedTrack
from music_bot.services.youtube_health_monitor import (
    cooldown_status as youtube_cooldown_status,
    inspect_cookie_file as inspect_youtube_cookie_file,
    record_failure as record_youtube_failure,
)

logger = logging.getLogger("RaiMusic.Resolver")

YOUTUBE_ACCESS_CHALLENGE_MARKERS = (
    "sign in to confirm",
    "not a bot",
    "confirm you're not a bot",
    "confirm you’re not a bot",
    "captcha",
    "consent required",
)


def _is_youtube_access_challenge(error_message: str) -> bool:
    """Return whether yt-dlp reported an explicit YouTube access challenge."""
    message = str(error_message or "").casefold()
    return any(marker in message for marker in YOUTUBE_ACCESS_CHALLENGE_MARKERS)


BASE_DIR = Path(__file__).resolve().parent.parent.parent
TOKENS_FILE = BASE_DIR / "data" / "tokens.json"

# Track cache TTL (1 hour)
CACHE_TTL = 3600

# Redis client singleton for optional distributed track caching
_redis_client: Any = None
_redis_init_attempted: bool = False

# Regex for detecting Tamil Unicode script (\u0B80-\u0BFF)
# Regexes for detecting regional and international Unicode scripts
TAMIL_SCRIPT_REGEX = re.compile(r"[\u0B80-\u0BFF]")
TELUGU_SCRIPT_REGEX = re.compile(r"[\u0C00-\u0C7F]")
DEVANAGARI_SCRIPT_REGEX = re.compile(r"[\u0900-\u097F]")
MALAYALAM_SCRIPT_REGEX = re.compile(r"[\u0D00-\u0D7F]")
KANNADA_SCRIPT_REGEX = re.compile(r"[\u0C80-\u0CFF]")
PUNJABI_SCRIPT_REGEX = re.compile(r"[\u0A00-\u0A7F]")
KOREAN_SCRIPT_REGEX = re.compile(r"[\uAC00-\uD7AF]")
JAPANESE_SCRIPT_REGEX = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF]")

# Explicit remix / DJ / electronic modifier keywords
REMIX_KEYWORDS = {
    "remix", "remixed", "rmx", "mashup", "bootleg", "rework", "dj remix",
    "dj mix", "club mix", "extended mix", "dance mix", "party mix", "techno edit",
    "hardstyle", "bass boosted", "8d audio", "dnb", "drum and bass", "flip"
}

# Speed, pitch, and mood alterations
SLOWED_KEYWORDS = {
    "slowed", "reverb", "slowed+reverb", "slowed reverb", "sped up", "speed up",
    "nightcore", "daycore", "lo-fi", "lofi", "lo-fi edit", "lofi edit", "lofi flip"
}

# Non-original recordings (covers, karaoke, reaction clips)
COVER_KEYWORDS = {
    "cover", "acoustic", "acoustic cover", "live cover", "karaoke", "instrumental",
    "piano cover", "guitar cover", "orchestral", "reaction", "reaction video"
}

# Social media edits, ringtones, and snippets
OTHER_MOD_KEYWORDS = {
    "fan edit", "fan video", "tiktok version", "ringtone", "status video", "short edit", "bgm mix"
}

NON_SONG_CONTENT_MARKERS = {
    "behind the scenes", "behind scenes", "first look", "instagram", "making of",
    "promo", "reels", "shorts", "snippet", "status", "teaser", "trailer",
    "trending", "whatsapp",
}

# Live concert and non-studio recording patterns
LIVE_PATTERNS = [
    re.compile(r"[\(\[\{]\s*live(\s+(at|in|from|session|performance|version|concert|acoustic))?[\)\]\}]", re.IGNORECASE),
    re.compile(r"\b(live at|live in|live from|live concert|live performance|live session|live acoustic|live version|live audio|live video)\b", re.IGNORECASE),
    re.compile(r"[-–|:]\s*live(\s+(at|in|from|session|performance|version|concert|acoustic))?\s*($|[-–|:(\[{])", re.IGNORECASE),
    re.compile(r"\b(concert|unplugged|world tour|stadium tour)\b", re.IGNORECASE),
]

# Amateur parodies, tributes, and reaction content
PARODY_TRIBUTE_KEYWORDS = {
    "parody", "tribute", "fanmade", "fan-made", "fan made", "reaction", "reacting", "review"
}

# Major verified record labels, publishers, and topic channels
MAJOR_RECORD_LABELS = {
    "vevo", "topic", "sony", "sonymusic", "universal", "universal music",
    "warner", "warner music", "t-series", "tseries", "zee music", "yrf",
    "saregama", "think music", "aditya music", "tips", "lahari music",
    "speed records", "geetha arts", "sun tv", "sun pictures", "anirudh",
    "atlantic", "interscope", "republic records", "def jam", "columbia records",
    "rca records", "epic records", "capitol records", "virgin music",
    "spinnin", "monstercat", "big hit", "hybe", "sm entertainment", "jyp", "yg"
}

# Explicit original song requests
ORIGINAL_KEYWORDS = {
    "original", "original song", "original version", "original audio", "original video",
    "official", "official song", "official version", "official audio", "official video",
    "official music video", "original track", "album version", "studio version"
}

ALL_ALT_VERSION_KEYWORDS = (
    REMIX_KEYWORDS | SLOWED_KEYWORDS | COVER_KEYWORDS | OTHER_MOD_KEYWORDS | PARODY_TRIBUTE_KEYWORDS
)

# Supported language markers and renowned regional artists/composers (no individual song names)
LANGUAGE_HINTS = {
    "tamil": [
        "tamil", "தமிழ்", "kollywood", "anirudh", "ilaiyaraaja", "ilayaraja", "ar rahman", "a.r. rahman",
        "harris jayaraj", "yuvan", "sid sriram", "dhanush", "vijay", "ajith", "spb", "s.p. balasubrahmanyam",
        "chithra", "santhosh narayanan", "d. imman", "gv prakash", "g.v. prakash", "u1", "vijay antony",
    ],
    "hindi": [
        "hindi", "हिंदी", "bollywood", "arijit", "badshah", "neha kakkar", "pritam",
        "atif aslam", "shreya ghoshal", "kumar sanu", "alka yagnik", "sonu nigam", "vishal-shekhar",
    ],
    "telugu": ["telugu", "తెలుగు", "tollywood", "dsp", "devi sri prasad", "keeravani", "thaman"],
    "malayalam": ["malayalam", "മലയാളം", "mollywood", "sushin shyam", "shaan rahman"],
    "kannada": ["kannada", "ಕನ್ನಡ", "sandalwood", "ravi basrur", "arjun janya"],
    "punjabi": ["punjabi", "ਪੰਜਾਬੀ", "diljit", "sidhu moose wala", "ap dhillon", "karan aujla"],
    "english": ["english"],
    "korean": ["korean", "k-pop", "kpop", "bts", "blackpink", "newjeans", "stray kids"],
    "japanese": ["japanese", "j-pop", "jpop", "anime"],
}


def analyze_query_intent(query: str) -> Dict[str, Any]:
    """
    Analyze user query intent:
    - Checks for explicit version requests (remix, slowed, cover, etc.).
    - Detects regional language scripts (Tamil, Telugu, Hindi, etc.) and language tokens.
    - Extracts clean core song title for accurate official version matching.
    """
    q_lower = query.lower().strip()

    # 1. Script and regional language detection
    has_tamil_script = bool(TAMIL_SCRIPT_REGEX.search(query))
    has_telugu_script = bool(TELUGU_SCRIPT_REGEX.search(query))
    has_devanagari_script = bool(DEVANAGARI_SCRIPT_REGEX.search(query))
    has_malayalam_script = bool(MALAYALAM_SCRIPT_REGEX.search(query))
    has_kannada_script = bool(KANNADA_SCRIPT_REGEX.search(query))
    has_punjabi_script = bool(PUNJABI_SCRIPT_REGEX.search(query))

    detected_language = None
    if has_tamil_script:
        detected_language = "tamil"
    elif has_telugu_script:
        detected_language = "telugu"
    elif has_devanagari_script:
        detected_language = "hindi"
    elif has_malayalam_script:
        detected_language = "malayalam"
    elif has_kannada_script:
        detected_language = "kannada"
    elif has_punjabi_script:
        detected_language = "punjabi"
    else:
        for lang, markers in LANGUAGE_HINTS.items():
            if any(re.search(rf"\b{re.escape(m)}\b", q_lower) for m in markers):
                detected_language = lang
                break

    # 2. Explicit alternate / remix version requests
    wants_remix = any(re.search(rf"\b{re.escape(k)}\b", q_lower) for k in REMIX_KEYWORDS)
    wants_slowed = any(re.search(rf"\b{re.escape(k)}\b", q_lower) for k in SLOWED_KEYWORDS)
    wants_cover = any(re.search(rf"\b{re.escape(k)}\b", q_lower) for k in COVER_KEYWORDS)
    wants_other_mod = any(re.search(rf"\b{re.escape(k)}\b", q_lower) for k in OTHER_MOD_KEYWORDS)
    wants_parody = any(re.search(rf"\b{re.escape(k)}\b", q_lower) for k in PARODY_TRIBUTE_KEYWORDS)
    wants_live = any(p.search(q_lower) for p in LIVE_PATTERNS) or bool(re.search(r"\b(live|concert|performance|unplugged)\b$", q_lower))

    user_requested_alternate = (
        wants_remix or wants_slowed or wants_cover or wants_other_mod or wants_parody or wants_live
    )

    # 3. Explicit original / official recording request
    wants_original = any(re.search(rf"\b{re.escape(k)}\b", q_lower) for k in ORIGINAL_KEYWORDS)

    # 4. Extract core title by peeling off version keywords for cleaner comparison
    core_title = q_lower
    for kw_set in (REMIX_KEYWORDS, SLOWED_KEYWORDS, COVER_KEYWORDS, OTHER_MOD_KEYWORDS, PARODY_TRIBUTE_KEYWORDS, ORIGINAL_KEYWORDS):
        for kw in sorted(kw_set, key=len, reverse=True):
            core_title = re.sub(rf"\b{re.escape(kw)}\b", "", core_title)
    for p in LIVE_PATTERNS:
        core_title = p.sub("", core_title)
    core_title = re.sub(r"\b(live|concert|performance|unplugged)\b$", "", core_title)
    # Strip standalone language keywords if specified at the end/beginning (e.g. 'tamil song title')
    if detected_language:
        core_title = re.sub(rf"\b{re.escape(detected_language)}\b", "", core_title)
    # Strip generic media descriptors (e.g. 'song', 'songs', 'audio', 'track', 'music', 'video')
    # only if meaningful core words remain
    stripped_media = re.sub(r"\b(songs?|audio|track|music|video)\b", "", core_title, flags=re.IGNORECASE)
    if stripped_media.strip():
        core_title = stripped_media
    core_title = " ".join(core_title.split())

    return {
        "raw_query": query,
        "clean_query": q_lower,
        "core_title": core_title or q_lower,
        "has_tamil_script": has_tamil_script,
        "detected_language": detected_language,
        "wants_remix": wants_remix,
        "wants_slowed": wants_slowed,
        "wants_cover": wants_cover,
        "wants_other_mod": wants_other_mod,
        "wants_parody": wants_parody,
        "wants_live": wants_live,
        "wants_original": wants_original,
        "user_requested_alternate": user_requested_alternate,
    }


def _video_id_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if host in {"youtu.be", "www.youtu.be"}:
            return parsed.path.strip("/").split("/", 1)[0] or None
        if host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
            video_id = urllib.parse.parse_qs(parsed.query).get("v", [None])[0]
            if video_id:
                return video_id
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live"}:
                return parts[1]
    except (TypeError, ValueError):
        return None
    return None


def _token_matches(query_token: str, candidate_tokens: set[str]) -> bool:
    return _token_similarity(query_token, candidate_tokens) >= 0.82


def _token_similarity(query_token: str, candidate_tokens: set[str]) -> float:
    if query_token in candidate_tokens:
        return 1.0
    if len(query_token) < 4:
        return 0.0
    return max(
        (
            SequenceMatcher(None, query_token, candidate_token).ratio()
            for candidate_token in candidate_tokens
            if len(candidate_token) >= 4
        ),
        default=0.0,
    )


def _candidate_match_metrics(
    candidate: Dict[str, Any],
    query_intent: Dict[str, Any],
) -> Tuple[float, float, float]:
    query_tokens = [
        token for token in re.findall(r"\w+", query_intent.get("core_title", "").lower())
        if len(token) > 1
    ]
    if not query_tokens:
        return 0.0, 0.0, 0.0

    title_tokens = set(re.findall(r"\w+", (candidate.get("title") or "").lower()))
    source_tokens = set(
        re.findall(
            r"\w+",
            " ".join(
                str(candidate.get(key) or "")
                for key in ("uploader", "channel", "artist")
            ).lower(),
        )
    )
    title_similarities = [_token_similarity(token, title_tokens) for token in query_tokens]
    combined_similarities = [
        _token_similarity(token, title_tokens | source_tokens)
        for token in query_tokens
    ]
    title_hits = sum(value >= 0.82 for value in title_similarities)
    combined_hits = sum(value >= 0.82 for value in combined_similarities)
    title_confidence = sum(title_similarities) / len(query_tokens)
    return title_hits / len(query_tokens), combined_hits / len(query_tokens), title_confidence


def score_candidate_detailed(
    candidate: Dict[str, Any],
    query_intent: Dict[str, Any],
    spotify_meta: Optional[Dict[str, Any]] = None,
    title_hint: Optional[str] = None,
    artist_hint: Optional[str] = None,
) -> Tuple[float, List[str]]:
    """
    Detailed candidate scoring with transparent reason tracking:
    - Base score = 100.0
    - Heavy penalty for unrequested remixes, slowed, reverb, mashups, live concerts, and fan edits.
    - Positive reward for user-requested remixes or alternate styles.
    - Official release preference (Topic channels, VEVO, verified labels, studio audio/video).
    - Title precision and language consistency scoring.
    """
    score = 100.0
    reasons: List[str] = []

    raw_title = candidate.get("title") or ""
    title = raw_title.lower()
    uploader = (candidate.get("uploader") or candidate.get("channel") or candidate.get("artist") or "").lower()
    duration = candidate.get("duration") or 0
    combined_text = f"{title} {uploader}"

    # 1. Alternative Version & Live / Remix Evaluation
    cand_has_remix = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in REMIX_KEYWORDS)
    cand_has_slowed = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in SLOWED_KEYWORDS)
    cand_has_cover = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in COVER_KEYWORDS)
    cand_has_mod = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in OTHER_MOD_KEYWORDS)
    cand_has_live = any(p.search(combined_text) for p in LIVE_PATTERNS)
    cand_has_parody = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in PARODY_TRIBUTE_KEYWORDS)

    cand_is_alt = (
        cand_has_remix
        or cand_has_slowed
        or cand_has_cover
        or cand_has_mod
        or cand_has_live
        or cand_has_parody
    )

    if not query_intent["user_requested_alternate"]:
        # User requested an ORIGINAL / standard recording
        if cand_has_remix:
            score -= 85.0
            reasons.append("unrequested_remix_penalty(-85)")
        if cand_has_slowed:
            score -= 80.0
            reasons.append("unrequested_slowed_penalty(-80)")
        if cand_has_cover:
            score -= 75.0
            reasons.append("unrequested_cover_penalty(-75)")
        if cand_has_mod:
            score -= 60.0
            reasons.append("unrequested_mod_penalty(-60)")
        if cand_has_live:
            score -= 70.0
            reasons.append("unrequested_live_penalty(-70)")
        if cand_has_parody:
            score -= 90.0
            reasons.append("unrequested_parody_penalty(-90)")

        if query_intent.get("wants_original"):
            if cand_is_alt:
                score -= 50.0
                reasons.append("strict_original_enforcement(-50)")
            else:
                score += 35.0
                reasons.append("explicit_original_match(+35)")
    else:
        # User explicitly requested a remix or alternate version
        if query_intent.get("wants_remix") and cand_has_remix:
            score += 55.0
            reasons.append("requested_remix_boost(+55)")
        elif query_intent.get("wants_slowed") and cand_has_slowed:
            score += 55.0
            reasons.append("requested_slowed_boost(+55)")
        elif query_intent.get("wants_cover") and cand_has_cover:
            score += 55.0
            reasons.append("requested_cover_boost(+55)")
        elif query_intent.get("wants_live") and cand_has_live:
            score += 55.0
            reasons.append("requested_live_boost(+55)")

        if not cand_is_alt:
            score -= 40.0
            reasons.append("original_penalized_for_explicit_remix_request(-40)")

    # 2. Official Audio / Video & Authentic Publisher Badges
    is_topic_channel = uploader.endswith(" - topic") or " - topic" in uploader or uploader.endswith("- topic")
    is_verified_channel = bool(candidate.get("channel_is_verified"))
    is_vevo = "vevo" in uploader
    is_major_label = any(lbl in uploader for lbl in MAJOR_RECORD_LABELS)
    is_official_uploader = (
        is_topic_channel
        or is_verified_channel
        or is_vevo
        or is_major_label
        or any(k in uploader for k in ["official", "records", "music", "audio", "entertainment"])
    )

    has_official_title = (
        "official music video" in title
        or "official video" in title
        or "official audio" in title
        or "original soundtrack" in title
        or "original mix" in title
        or "lyric video" in title
        or "official lyric" in title
    )

    if not query_intent["user_requested_alternate"]:
        if not cand_is_alt:
            if is_topic_channel:
                score += 45.0
                reasons.append("youtube_topic_channel(+45)")
            elif is_vevo:
                score += 40.0
                reasons.append("vevo_official(+40)")
            elif is_major_label:
                score += 35.0
                reasons.append("major_record_label(+35)")
            elif is_official_uploader:
                score += 25.0
                reasons.append("official_label_uploader(+25)")

            if has_official_title:
                score += 30.0
                reasons.append("official_title_badge(+30)")
            elif "remastered" in title or "original mix" in title or "original soundtrack" in title:
                score += 15.0
                reasons.append("remastered_or_original_mix(+15)")

            # Studio Audio preference
            if "official audio" in title or is_topic_channel or "original audio" in title:
                score += 15.0
                reasons.append("studio_audio_bonus(+15)")

            # Unverified fan upload penalty when no official badge is present
            if not is_official_uploader and not has_official_title:
                score -= 20.0
                reasons.append("unverified_fan_upload_penalty(-20)")
    else:
        if is_official_uploader:
            score += 10.0
            reasons.append("official_uploader_remix(+10)")

    # 3. Clean Title & Token Overlap Matching
    core_title = query_intent.get("core_title", "").strip()
    clean_q = query_intent.get("clean_query", "").strip()

    cleaned_cand_title = re.sub(
        r"[\(\[\{](official\s+(music\s+)?(video|audio)|lyric\s+video|audio|lyrics|hd|4k|visualizer|full\s+song|video\s+song)[\)\]\}]",
        "",
        title,
        flags=re.IGNORECASE,
    )
    cleaned_cand_title = re.sub(r"\|\s*[\w\s\.\,\-]+$", "", cleaned_cand_title)
    cleaned_cand_title = " ".join(cleaned_cand_title.split())

    if core_title and (core_title == cleaned_cand_title or core_title in cleaned_cand_title):
        score += 35.0
        reasons.append("core_title_match(+35)")

    title_match_ratio, combined_match_ratio, title_confidence = _candidate_match_metrics(
        candidate,
        query_intent,
    )
    if core_title:
        title_match_points = title_confidence * 75.0
        source_match_points = max(0.0, combined_match_ratio - title_match_ratio) * 15.0
        mismatch_penalty = (1.0 - combined_match_ratio) * 100.0
        score += title_match_points + source_match_points
        reasons.append(f"title_match_{title_match_ratio:.2f}(+{title_match_points:.1f})")
        if source_match_points:
            reasons.append(f"source_match_bonus(+{source_match_points:.1f})")
        if mismatch_penalty:
            score -= mismatch_penalty
            reasons.append(f"query_term_mismatch(-{mismatch_penalty:.1f})")

    if query_intent.get("has_tamil_script") and DEVANAGARI_SCRIPT_REGEX.search(raw_title):
        score -= 100.0
        reasons.append("script_language_mismatch(-100)")
    elif query_intent.get("detected_language") == "hindi" and TAMIL_SCRIPT_REGEX.search(raw_title):
        score -= 100.0
        reasons.append("script_language_mismatch(-100)")

    # Penalty for social media junk filler words when looking for original track
    if not query_intent["user_requested_alternate"] and not cand_is_alt:
        extra_noise = {"status", "whatsapp", "shorts", "reels", "fullscreen", "trending"}
        if any(w in title for w in extra_noise):
            score -= 35.0
            reasons.append("social_media_clip_penalty(-35)")

    # 4. Language & Regional Accuracy
    det_lang = query_intent.get("detected_language")
    has_tamil_script = query_intent.get("has_tamil_script")

    if has_tamil_script:
        if TAMIL_SCRIPT_REGEX.search(raw_title):
            score += 50.0
            reasons.append("tamil_script_match(+50)")
        if "tamil" in combined_text:
            score += 35.0
            reasons.append("tamil_keyword_match(+35)")
        conflicting = ["hindi", "telugu", "punjabi", "bollywood", "bhojpuri"]
        if any(re.search(rf"\b{re.escape(c)}\b", combined_text) for c in conflicting) and "tamil" not in combined_text:
            score -= 70.0
            reasons.append("conflicting_language_penalty(-70)")
    elif det_lang:
        if re.search(rf"\b{re.escape(det_lang)}\b", combined_text):
            score += 35.0
            reasons.append(f"matched_language_{det_lang}(+35)")
        other_major_langs = [l for l in ["tamil", "hindi", "telugu", "malayalam", "kannada", "punjabi"] if l != det_lang]
        if any(re.search(rf"\b{re.escape(ol)}\b", combined_text) for ol in other_major_langs) and not re.search(rf"\b{re.escape(det_lang)}\b", combined_text):
            score -= 65.0
            reasons.append(f"conflicting_language_penalty(-65)")

    # 5. Spotify metadata and title/artist hints matching
    target_title = (title_hint or (spotify_meta.get("title") if spotify_meta else "") or "").lower().strip()
    target_artist = (artist_hint or (spotify_meta.get("artist") if spotify_meta else "") or "").lower().strip()
    target_dur = spotify_meta.get("duration") if spotify_meta else 0

    if target_title and target_title in title:
        score += 35.0
        reasons.append("spotify_title_match(+35)")
    if target_artist and target_artist not in ("unknown artist", "various artists"):
        if target_artist in uploader or target_artist in title:
            score += 30.0
            reasons.append("spotify_artist_match(+30)")

    if target_dur > 0 and duration > 0:
        dur_diff = abs(target_dur - duration)
        if dur_diff <= 5:
            score += 20.0
            reasons.append("spotify_duration_exact(+20)")
        elif dur_diff <= 15:
            score += 10.0
            reasons.append("spotify_duration_close(+10)")
        elif dur_diff > 60:
            score -= 30.0
            reasons.append("spotify_duration_mismatch(-30)")

    # 6. Reasonable duration checks (avoid 10-hour loops or 15s snippets)
    if 90 <= duration <= 360:
        score += 20.0
        reasons.append("ideal_song_duration(+20)")
    elif 60 <= duration <= 600:
        score += 10.0
        reasons.append("standard_duration_bonus(+10)")
    elif duration > 900:
        if not any(k in clean_q for k in ["full album", "compilation", "jukebox", "nonstop", "1 hour", "hour"]):
            score -= 55.0
            reasons.append("extended_duration_penalty(-55)")
    elif 0 < duration < 50:
        score -= 60.0
        reasons.append("short_snippet_penalty(-60)")

    return score, reasons


def score_candidate(
    candidate: Dict[str, Any],
    query_intent: Dict[str, Any],
    spotify_meta: Optional[Dict[str, Any]] = None,
    title_hint: Optional[str] = None,
    artist_hint: Optional[str] = None,
) -> float:
    """Public candidate scoring function returning scalar rank score."""
    score, _ = score_candidate_detailed(
        candidate, query_intent, spotify_meta=spotify_meta, title_hint=title_hint, artist_hint=artist_hint
    )
    return score


def is_original_recording_candidate(
    candidate: Dict[str, Any],
    query_intent: Dict[str, Any],
    spotify_meta: Optional[Dict[str, Any]] = None,
    title_hint: Optional[str] = None,
    artist_hint: Optional[str] = None,
) -> bool:
    """Accept well-matched original uploads or explicitly requested alternate versions."""

    _, reasons = score_candidate_detailed(
        candidate,
        query_intent,
        spotify_meta=spotify_meta,
        title_hint=title_hint,
        artist_hint=artist_hint,
    )
    if any(reason.startswith("unrequested_") for reason in reasons):
        return False

    title = (candidate.get("title") or "").lower()
    if any(re.search(rf"\b{re.escape(marker)}\b", title) for marker in NON_SONG_CONTENT_MARKERS):
        return False

    uploader = (candidate.get("uploader") or candidate.get("channel") or candidate.get("artist") or "").lower()
    combined_text = f"{title} {uploader}"
    cand_has_remix = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in REMIX_KEYWORDS)
    cand_has_slowed = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in SLOWED_KEYWORDS)
    cand_has_cover = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in COVER_KEYWORDS)
    cand_has_mod = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in OTHER_MOD_KEYWORDS)
    cand_has_live = any(p.search(combined_text) for p in LIVE_PATTERNS)
    cand_has_parody = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in PARODY_TRIBUTE_KEYWORDS)

    if query_intent.get("user_requested_alternate"):
        requested_alternate_match = (
            (query_intent.get("wants_remix") and cand_has_remix)
            or (query_intent.get("wants_slowed") and cand_has_slowed)
            or (query_intent.get("wants_cover") and cand_has_cover)
            or (query_intent.get("wants_other_mod") and cand_has_mod)
            or (query_intent.get("wants_parody") and cand_has_parody)
            or (query_intent.get("wants_live") and cand_has_live)
        )
        if not requested_alternate_match:
            return False
    elif cand_has_remix or cand_has_slowed or cand_has_cover or cand_has_mod or cand_has_live or cand_has_parody:
        return False

    title_match_ratio, combined_match_ratio, _ = _candidate_match_metrics(
        candidate,
        query_intent,
    )
    if title_match_ratio < 0.5 or combined_match_ratio < 0.75:
        return False

    if query_intent.get("user_requested_alternate"):
        return True


    title_has_official_marker = bool(
        re.search(
            r"\b(?:official\s+(?:music\s+)?(?:video|audio|song)|official\s+lyric(?:al)?(?:\s+video)?|original\s+soundtrack)\b",
            title,
        )
    )
    uploader_has_official_marker = (
        bool(candidate.get("channel_is_verified"))
        or " - topic" in uploader
        or "vevo" in uploader
        or any(label in uploader for label in MAJOR_RECORD_LABELS)
        or bool(re.search(r"\b(?:official|record(?:s| label)?|label)\b", uploader))
    )
    if not title_has_official_marker and not uploader_has_official_marker:
        # For short, single-word searches, official-upload metadata is often absent
        # from valid regional tracks. Accept only a strong title match in that case;
        # keep the stricter official-upload requirement for longer ambiguous queries.
        query_tokens = re.findall(r"\w+", str(query_intent.get("clean_query") or "").lower())
        title_match_ratio, combined_match_ratio, title_confidence = _candidate_match_metrics(
            candidate,
            query_intent,
        )
        if len(query_tokens) != 1 or title_match_ratio < 0.75 or combined_match_ratio < 0.75 or title_confidence < 0.75:
            return False

    return True


def is_alternative_provider_candidate(
    candidate: Dict[str, Any],
    query_intent: Dict[str, Any],
) -> bool:
    """Match Audius/Jamendo catalog entries without YouTube-specific official-upload rules.

    Alternative catalogs often lack VEVO, verified-channel, or official-release
    metadata. Keep title/artist matching and alternate-version safety checks,
    but do not reject a good catalog match solely because it is not marked
    as an official YouTube upload.
    """
    _, reasons = score_candidate_detailed(candidate, query_intent)
    if any(reason.startswith("unrequested_") for reason in reasons):
        return False

    title = (candidate.get("title") or "").lower()
    if any(re.search(rf"\b{re.escape(marker)}\b", title) for marker in NON_SONG_CONTENT_MARKERS):
        return False

    uploader = (candidate.get("uploader") or candidate.get("channel") or candidate.get("artist") or "").lower()
    combined_text = f"{title} {uploader}"
    cand_has_remix = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in REMIX_KEYWORDS)
    cand_has_slowed = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in SLOWED_KEYWORDS)
    cand_has_cover = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in COVER_KEYWORDS)
    cand_has_mod = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in OTHER_MOD_KEYWORDS)
    cand_has_live = any(p.search(combined_text) for p in LIVE_PATTERNS)
    cand_has_parody = any(re.search(rf"\b{re.escape(k)}\b", combined_text) for k in PARODY_TRIBUTE_KEYWORDS)

    if query_intent.get("user_requested_alternate"):
        requested_alternate_match = (
            (query_intent.get("wants_remix") and cand_has_remix)
            or (query_intent.get("wants_slowed") and cand_has_slowed)
            or (query_intent.get("wants_cover") and cand_has_cover)
            or (query_intent.get("wants_other_mod") and cand_has_mod)
            or (query_intent.get("wants_parody") and cand_has_parody)
            or (query_intent.get("wants_live") and cand_has_live)
        )
        if not requested_alternate_match:
            return False
    elif cand_has_remix or cand_has_slowed or cand_has_cover or cand_has_mod or cand_has_live or cand_has_parody:
        return False

    title_match_ratio, combined_match_ratio, _ = _candidate_match_metrics(candidate, query_intent)
    return title_match_ratio >= 0.5 and combined_match_ratio >= 0.75


def requires_candidate_confirmation(candidates: List[Dict[str, Any]]) -> bool:
    """Require a user choice when top results are weak or too close to distinguish."""
    if not candidates:
        return False
    if float(candidates[0].get("_title_match_confidence", 1.0)) < 0.96:
        return True
    top_ratio = float(candidates[0].get("_title_match_ratio", 1.0))
    if top_ratio < 0.75:
        return True
    if len(candidates) < 2:
        return False
    second_ratio = float(candidates[1].get("_title_match_ratio", 1.0))
    score_gap = float(candidates[0].get("_match_score", 0.0)) - float(
        candidates[1].get("_match_score", 0.0)
    )
    return second_ratio >= 0.75 and score_gap <= 18.0


def apply_resolved_track(track: QueuedTrack, resolved: QueuedTrack) -> bool:
    """Merge fresh stream metadata only when it belongs to the selected track."""
    expected_id = _video_id_from_url(track.url)
    resolved_id = _video_id_from_url(resolved.url)
    expected_url = urllib.parse.urlsplit(track.url) if track.url else None
    resolved_url = urllib.parse.urlsplit(resolved.url) if resolved.url else None
    expected_is_url = bool(expected_url and expected_url.scheme in {"http", "https"})
    resolved_is_url = bool(resolved_url and resolved_url.scheme in {"http", "https"})
    if expected_id:
        if expected_id != resolved_id:
            return False
    elif expected_is_url and resolved_is_url:
        if (expected_url.hostname, expected_url.path) != (resolved_url.hostname, resolved_url.path):
            return False
    elif SequenceMatcher(None, track.title.casefold(), resolved.title.casefold()).ratio() < 0.85:
        return False

    track.title = resolved.title
    track.url = resolved.url or track.url
    track.duration = resolved.duration or track.duration
    track.stream_url = resolved.stream_url
    track.artist = resolved.artist or track.artist
    track.thumbnail = resolved.thumbnail or track.thumbnail
    return True


async def get_redis_client() -> Any:
    """Retrieve or lazily connect to Redis client if REDIS_URL is configured."""
    global _redis_client, _redis_init_attempted
    if _redis_client is not None:
        return _redis_client
    if _redis_init_attempted:
        return None
    _redis_init_attempted = True
    if not REDIS_URL:
        return None
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await client.ping()
        _redis_client = client
        logger.info("[Resolver] Connected to Redis for persistent track caching.")
        return _redis_client
    except Exception as e:
        logger.warning(
            "[Resolver] Redis cache initialization failed (exception_type=%s). "
            "Using in-memory cache.",
            type(e).__name__,
        )
        return None


# Global executor for thread-safe asynchronous yt-dlp operations
_AUDIO_EXECUTOR_MAX_WORKERS = 20
_audio_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=_AUDIO_EXECUTOR_MAX_WORKERS, thread_name_prefix="AudioResolver"
)
_audio_executor_slots: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.Semaphore
] = weakref.WeakKeyDictionary()

# Writable temporary cookie file destination (yt-dlp requires write permissions)
WRITABLE_COOKIE_PATH = Path(tempfile.gettempdir()) / "musicmaid_cookies.txt"



def _format_error(e: BaseException) -> str:
    """Format exception details while redacting credentials and signed URLs."""
    if isinstance(e, asyncio.TimeoutError):
        return f"{type(e).__name__} (Network or resolution operation timed out)"
    err_str = str(e).strip()
    if not err_str:
        return f"{type(e).__name__}: no error details"
    err_str = re.sub(
        r"(?im)\b(cookie|set-cookie)\s*[:=]\s*[^\r\n]+",
        r"\1=[REDACTED]",
        err_str,
    )
    err_str = re.sub(
        r"(?i)\b(authorization|proxy-authorization|access[_-]?token|refresh[_-]?token|api[_-]?key|signature|sig|token|key)\b"
        r"(\s*[:=]\s*)(?:(?:bearer|basic)\s+)?[^\s,;]+",
        r"\1\2[REDACTED]",
        err_str,
    )
    err_str = re.sub(r"https?://[^\s'\"<>]+", "[URL redacted]", err_str)
    return f"{type(e).__name__}: {err_str}"


def _safe_query_for_log(query: str) -> str:
    if query.startswith(("http://", "https://")):
        video_id = _video_id_from_url(query)
        return f"[URL video_id={video_id}]" if video_id else "[URL]"
    formatted = _format_error(RuntimeError(query))
    return formatted.partition(": ")[2][:160]


def _get_audio_executor_slots(loop: asyncio.AbstractEventLoop) -> asyncio.Semaphore:
    slots = _audio_executor_slots.get(loop)
    if slots is None:
        max_workers = max(1, getattr(_audio_executor, "_max_workers", _AUDIO_EXECUTOR_MAX_WORKERS))
        slots = asyncio.Semaphore(max_workers)
        _audio_executor_slots[loop] = slots
    return slots


async def _run_ytdlp(
    call: Any,
    *,
    timeout: float,
    operation: str,
    correlation_id: str,
    provider: str = "youtube",
    retry_count: int = 0,
) -> Any:
    """Run yt-dlp with bounded submissions; keep a slot until timed-out worker threads exit."""
    loop = asyncio.get_running_loop()
    started_at = time.monotonic()
    slots = _get_audio_executor_slots(loop)
    try:
        await asyncio.wait_for(slots.acquire(), timeout=timeout)
    except asyncio.TimeoutError:
        elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.warning(
            "[Resolver] provider=%s operation=%s corr_id=%s duration_ms=%.1f "
            "exception_type=TimeoutError retry_count=%d outcome=capacity_timeout",
            provider, operation, correlation_id, elapsed_ms, retry_count,
        )
        raise

    try:
        worker_future = _audio_executor.submit(call)
    except Exception:
        slots.release()
        raise

    async_future = asyncio.wrap_future(worker_future, loop=loop)
    abandoned = False

    def _release_slot(_: concurrent.futures.Future[Any]) -> None:
        try:
            loop.call_soon_threadsafe(slots.release)
        except RuntimeError:
            logger.debug(
                "[Resolver] provider=%s operation=%s corr_id=%s outcome=loop_closed_before_slot_release",
                provider, operation, correlation_id,
            )

    def _consume_abandoned_result(future: asyncio.Future[Any]) -> None:
        if not abandoned or future.cancelled():
            return
        exc = future.exception()
        if exc is not None:
            elapsed_ms = (time.monotonic() - started_at) * 1000
            # A timed-out asyncio waiter cannot stop an already-running yt-dlp
            # worker thread. Capture its eventual upstream error too: otherwise
            # a late HTTP 429/403 is logged by yt-dlp but the health monitor only
            # sees the earlier outer timeout and starts an incorrectly short cooldown.
            if provider == "youtube":
                try:
                    record_youtube_failure(_format_error(exc))
                except Exception:
                    logger.debug(
                        "[Resolver] provider=%s operation=%s corr_id=%s "
                        "outcome=late_failure_health_update_failed",
                        provider, operation, correlation_id,
                    )
            logger.warning(
                "[Resolver] provider=%s operation=%s corr_id=%s duration_ms=%.1f "
                "exception_type=%s retry_count=%d outcome=late_worker_failure",
                provider, operation, correlation_id, elapsed_ms, type(exc).__name__, retry_count,
            )

    worker_future.add_done_callback(_release_slot)
    async_future.add_done_callback(_consume_abandoned_result)
    remaining = max(0.0, timeout - (time.monotonic() - started_at))
    try:
        result = await asyncio.wait_for(asyncio.shield(async_future), timeout=remaining)
    except asyncio.TimeoutError:
        abandoned = True
        cancelled_before_start = worker_future.cancel()
        if async_future.done():
            _consume_abandoned_result(async_future)
        elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.warning(
            "[Resolver] provider=%s operation=%s corr_id=%s duration_ms=%.1f "
            "exception_type=TimeoutError retry_count=%d outcome=timeout "
            "worker_cancelled_before_start=%s",
            provider, operation, correlation_id, elapsed_ms, retry_count, cancelled_before_start,
        )
        raise
    except asyncio.CancelledError:
        abandoned = True
        cancelled_before_start = worker_future.cancel()
        if async_future.done():
            _consume_abandoned_result(async_future)
        elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.info(
            "[Resolver] provider=%s operation=%s corr_id=%s duration_ms=%.1f "
            "exception_type=CancelledError retry_count=%d outcome=cancelled "
            "worker_cancelled_before_start=%s",
            provider, operation, correlation_id, elapsed_ms, retry_count, cancelled_before_start,
        )
        raise
    except Exception as exc:
        elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.warning(
            "[Resolver] provider=%s operation=%s corr_id=%s duration_ms=%.1f "
            "exception_type=%s retry_count=%d outcome=failed",
            provider, operation, correlation_id, elapsed_ms, type(exc).__name__, retry_count,
        )
        raise
    else:
        elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.debug(
            "[Resolver] provider=%s operation=%s corr_id=%s duration_ms=%.1f "
            "retry_count=%d outcome=success",
            provider, operation, correlation_id, elapsed_ms, retry_count,
        )
        return result


def get_ffmpeg_executable() -> str:
    """
    Resolve active FFmpeg binary path.
    Prioritizes system PATH, imageio-ffmpeg static binaries, static-ffmpeg, and common Linux paths.
    """
    # 1. System PATH
    found = shutil.which("ffmpeg")
    if found:
        return found

    # 2. imageio-ffmpeg wheel distribution
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:
        pass

    # 3. static-ffmpeg package
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        found = shutil.which("ffmpeg")
        if found:
            return found
    except Exception:
        pass

    # 4. Standard Linux / container binaries
    for candidate in [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/opt/render/project/src/.ffmpeg/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
    ]:
        if Path(candidate).exists():
            return candidate

    return "ffmpeg"


def _detect_js_runtimes() -> Dict[str, Any]:
    """Detect available JavaScript runtimes (Node.js or Deno) for yt-dlp EJS challenge solver."""
    runtimes: Dict[str, Any] = {}

    node_path = shutil.which("node")
    if not node_path:
        for candidate in [
            "/usr/bin/node",
            "/usr/local/bin/node",
            "/opt/render/project/.nvm/versions/node/default/bin/node",
        ]:
            if Path(candidate).exists():
                node_path = candidate
                break

    if node_path:
        runtimes["node"] = {"path": node_path}

    deno_path = shutil.which("deno")
    if not deno_path:
        deno_home = Path.home() / ".deno" / "bin" / "deno"
        if deno_home.exists():
            deno_path = str(deno_home)

    if deno_path:
        runtimes["deno"] = {"path": deno_path}

    return runtimes


def _validate_cookies_content(content: str) -> Tuple[bool, str]:
    """
    Validates Netscape cookie content and checks for expired YouTube authentication tokens.
    Returns (is_valid, diagnostic_message).
    """
    lines = content.strip().splitlines()
    if not lines:
        return False, "Cookies file is empty."

    now = time.time()
    found_keys: List[str] = []
    expired_keys: List[str] = []
    target_keys = {"SAPISID", "__Secure-3PSID", "__Secure-1PSID", "LOGIN_INFO", "SID", "HSID", "SSID"}

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            name = parts[5]
            expiry_str = parts[4]
            if name in target_keys:
                found_keys.append(name)
                try:
                    exp_val = float(expiry_str)
                    if 0 < exp_val < now:
                        expired_keys.append(name)
                except ValueError:
                    pass

    if not found_keys:
        return True, "No critical YouTube session tokens identified (generic or guest cookies)."

    if expired_keys:
        return False, (
            f"Expired YouTube authentication tokens detected: {', '.join(set(expired_keys))}. "
            f"YouTube will reject requests with HTTP 403 or SABR. Please export fresh cookies."
        )

    return True, f"Valid YouTube cookies present ({len(set(found_keys))} session tokens verified)."


def get_cookie_diagnostics() -> Dict[str, Any]:
    """
    Safely inspect configured YouTube cookie sources without exposing sensitive contents or values.
    Returns safe metadata: presence, source, file size, token counts, expired token names, and guidance.
    """
    secrets_dir = Path("/etc/secrets")
    render_secret_path = secrets_dir / "cookies.txt"
    render_secret_exists = render_secret_path.exists() and render_secret_path.stat().st_size > 0

    cookie_file = get_active_cookie_file()
    if not cookie_file or not Path(cookie_file).exists() or Path(cookie_file).stat().st_size == 0:
        return {
            "present": False,
            "source": "None",
            "size_bytes": 0,
            "token_count": 0,
            "expired_tokens": [],
            "is_valid": False,
            "status": "Missing",
            "summary": "No YouTube cookies configured",
            "guidance": "Add cookies.txt in Render Dashboard under Secret Files (/etc/secrets/cookies.txt) or set YOUTUBE_COOKIES.",
        }

    c_path = Path(cookie_file)
    c_size = c_path.stat().st_size
    try:
        content = c_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        content = ""

    is_valid, msg = _validate_cookies_content(content)

    if render_secret_exists:
        src = "/etc/secrets/cookies.txt (Render Secret File)"
    elif os.environ.get("YOUTUBE_COOKIES") or os.environ.get("YOUTUBE_COOKIES_BASE64"):
        src = "YOUTUBE_COOKIES Environment Variable"
    else:
        src = f"Local ({c_path.name})"

    now = time.time()
    found_keys: List[str] = []
    expired_keys: List[str] = []
    target_keys = {"SAPISID", "__Secure-3PSID", "__Secure-1PSID", "LOGIN_INFO", "SID", "HSID", "SSID"}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            name = parts[5]
            if name in target_keys:
                found_keys.append(name)
                try:
                    exp_val = float(parts[4])
                    if 0 < exp_val < now:
                        expired_keys.append(name)
                except ValueError:
                    pass

    unique_found = sorted(list(set(found_keys)))
    unique_expired = sorted(list(set(expired_keys)))

    status = "Valid" if is_valid else "Expired/Restricted"
    guidance = "Cookies active." if is_valid else f"Expired tokens: {', '.join(unique_expired)}. Fresh export required."

    return {
        "present": True,
        "source": src,
        "size_bytes": c_size,
        "token_count": len(unique_found),
        "tokens_found": unique_found,
        "expired_tokens": unique_expired,
        "is_valid": is_valid,
        "status": status,
        "summary": f"{status} ({len(unique_found)} tokens, {c_size} bytes)",
        "guidance": guidance,
    }


def sync_and_prepare_cookies() -> Optional[str]:
    """
    Discovers, validates, and prepares YouTube cookies in a writable temp location.
    Sources checked in priority order:
    1. Render Secret File: /etc/secrets/cookies.txt
    2. Environment Variable: YOUTUBE_COOKIES / YOUTUBE_COOKIES_BASE64
    3. Project Data Directory: data/cookies.txt (or local cookies.txt)
    """
    raw_content: Optional[str] = None
    source_name: Optional[str] = None

    # Source 1: Render Secret Files mount path (/etc/secrets/...)
    secrets_dir = Path("/etc/secrets")
    if secrets_dir.exists() and secrets_dir.is_dir():
        # Check standard cookies.txt first
        standard_secret = secrets_dir / "cookies.txt"
        if standard_secret.exists() and standard_secret.stat().st_size > 0:
            try:
                raw_content = standard_secret.read_text(encoding="utf-8", errors="replace")
                source_name = "/etc/secrets/cookies.txt (Render Secret File)"
            except Exception as e:
                logger.warning(f"[Cookies] Failed reading {standard_secret}: {_format_error(e)}")

        # If not standard name, scan all files in /etc/secrets for cookie content
        if not raw_content:
            try:
                for candidate in secrets_dir.iterdir():
                    if candidate.is_file() and candidate.stat().st_size > 0:
                        try:
                            cand_txt = candidate.read_text(encoding="utf-8", errors="replace")
                            if "youtube" in cand_txt.lower() or "\t" in cand_txt:
                                raw_content = cand_txt
                                source_name = f"{candidate} (Render Secret File)"
                                break
                        except Exception:
                            pass
            except Exception as scan_err:
                logger.debug(f"[Cookies] Error scanning /etc/secrets: {scan_err}")

    # Source 2: Environment variables
    if not raw_content:
        env_raw = os.environ.get("YOUTUBE_COOKIES") or os.environ.get("YOUTUBE_COOKIES_DATA") or os.environ.get("COOKIES")
        if env_raw and env_raw.strip():
            raw_content = env_raw.strip()
            source_name = "YOUTUBE_COOKIES environment variable"
        elif os.environ.get("YOUTUBE_COOKIES_BASE64"):
            try:
                import base64
                decoded = base64.b64decode(os.environ["YOUTUBE_COOKIES_BASE64"]).decode("utf-8", errors="replace")
                if decoded.strip():
                    raw_content = decoded.strip()
                    source_name = "YOUTUBE_COOKIES_BASE64 environment variable"
            except Exception as e:
                logger.warning(f"[Cookies] Failed decoding YOUTUBE_COOKIES_BASE64: {_format_error(e)}")

    # Source 3: Render app directory, project root, and local workspace fallback
    if not raw_content:
        candidate_paths = [
            Path("/opt/render/project/src/cookies.txt"),
            Path("/opt/render/project/src/youtube_cookies.txt"),
            BASE_DIR / "cookies.txt",
            BASE_DIR / "youtube_cookies.txt",
            BASE_DIR / "data" / "cookies.txt",
            BASE_DIR / "data" / "youtube_cookies.txt",
            Path.cwd() / "cookies.txt",
            Path.cwd() / "youtube_cookies.txt",
        ]
        for local_path in candidate_paths:
            if local_path.exists() and local_path.stat().st_size > 0:
                try:
                    raw_content = local_path.read_text(encoding="utf-8", errors="replace")
                    source_name = str(local_path)
                    break
                except Exception:
                    pass

    if not raw_content or not raw_content.strip():
        logger.debug(
            "[Cookies] Optional YouTube cookies not configured. Proceeding with public playback."
        )
        return None

    # Validate cookies integrity and expiration
    is_valid, diag = _validate_cookies_content(raw_content)
    if not is_valid:
        logger.warning(f"[Cookies] WARNING: {diag}")
    else:
        logger.info(f"[Cookies] Loaded cookies from {source_name}: {diag}")

    # Write to a guaranteed writable temporary path
    try:
        WRITABLE_COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
        WRITABLE_COOKIE_PATH.write_text(raw_content.strip(), encoding="utf-8")
        return str(WRITABLE_COOKIE_PATH)
    except Exception as write_err:
        logger.error(f"[Cookies] Could not write cookies to temp location: {_format_error(write_err)}")
        return None


def get_active_cookie_file() -> Optional[str]:
    """Returns the path to the verified, writable cookiefile if present and non-empty."""
    if WRITABLE_COOKIE_PATH.exists() and WRITABLE_COOKIE_PATH.stat().st_size > 0:
        return str(WRITABLE_COOKIE_PATH)
    return sync_and_prepare_cookies()


# Initial cookies synchronization on module import
sync_and_prepare_cookies()


def _load_po_tokens_and_cookies() -> Dict[str, Any]:
    """Load PO-Token and visitor data pool from data/tokens.json for automated rotation."""
    if not TOKENS_FILE.exists():
        try:
            TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
            default_data = {
                "active_po_token": "",
                "visitor_data": "",
                "tokens": [],
                "cookies": [],
                "last_rotated": 0.0,
            }
            TOKENS_FILE.write_text(json.dumps(default_data, indent=2))
        except Exception:
            pass
        return {}
    try:
        return json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_ytdl_options(
    player_clients: Optional[List[str]] = None,
    extract_flat: bool = False,
    use_cookies: bool = False,
) -> Dict[str, Any]:
    """
    Build yt-dlp extractor configuration options.
    Optimized strictly for authorized YouTube stream resolution.
    Cookies are strictly optional and only attached when use_cookies is True.
    """
    opts: Dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
        "restrictfilenames": True,
        "noplaylist": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "quiet": True,
        "default_search": "ytsearch",
        "socket_timeout": 8,
        "extractor_retries": 1,
        "retries": 1,
        # JukeBot's lean request profile: avoid playlist expansion and local cache I/O.
        # Keep stream extraction on the normal processing path; search callers use process=False.
        "source_address": "0.0.0.0",
        "cachedir": False,
        "extractor_args": {
            "youtube": {
                "skip": ["translated_subs"],
            }
        },
    }
    if player_clients:
        opts["extractor_args"]["youtube"]["player_client"] = player_clients
    if extract_flat:
        opts["extract_flat"] = True

    # Automatically attach JavaScript runtime for EJS challenge solving
    js_runtimes = _detect_js_runtimes()
    if js_runtimes:
        opts["js_runtimes"] = js_runtimes

    # Inject PO-Token if configured
    token_data = _load_po_tokens_and_cookies()
    po_token = os.environ.get("PO_TOKEN") or token_data.get("active_po_token")
    visitor_data = os.environ.get("VISITOR_DATA") or token_data.get("visitor_data")
    if po_token:
        opts["extractor_args"]["youtube"]["po_token"] = [f"web+{po_token}", f"mweb+{po_token}"]
    if visitor_data:
        opts["extractor_args"]["youtube"]["visitor_data"] = [visitor_data]

    # Attach verified writable cookiefile ONLY when explicitly requested as a fallback
    if use_cookies:
        cookie_path = get_active_cookie_file()
        if cookie_path:
            opts["cookiefile"] = cookie_path

    return opts


FFMPEG_OPTIONS = {
    "executable": get_ffmpeg_executable(),
    "before_options": (
        "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
        "-analyzeduration 1000000 -probesize 1000000 -loglevel warning "
        '-user_agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"'
    ),
    "options": "-vn -bufsize 4096k",
}

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 10,
    "extract_flat": False,
}



class AudioResolver:
    """Handles query searching, URL extraction, and stream link generation with ultra-low latency."""

    _search_cache: Dict[str, List[Dict[str, Any]]] = {}
    _track_cache: Dict[str, Tuple[QueuedTrack, float]] = {}  # cache_key -> (track, timestamp)
    _pending_tasks: Dict[str, asyncio.Task[Optional[QueuedTrack]]] = {}
    _pending_search_tasks: Dict[str, asyncio.Task[List[Dict[str, Any]]]] = {}

    PROFILE_PRESETS: List[List[str]] = [
        ["android", "web"],
        ["mweb", "web"],
        ["android"],
        ["web"],
    ]
    _active_profile_index: int = 0
    last_resolver_error: Optional[str] = None
    _last_probe_time: float = 0.0
    _last_probe_result: Optional[Dict[str, Any]] = None
    PROBE_COOLDOWN_SECONDS: float = 45.0

    @classmethod
    def get_current_profile_name(cls) -> str:
        idx = cls._active_profile_index % len(cls.PROFILE_PRESETS)
        return "+".join(cls.PROFILE_PRESETS[idx])

    @classmethod
    def rotate_client_profile(cls) -> str:
        """Rotates yt-dlp client profile in memory to bypass SABR / stream blocks."""
        cls._active_profile_index = (cls._active_profile_index + 1) % len(cls.PROFILE_PRESETS)
        new_profile = cls.PROFILE_PRESETS[cls._active_profile_index]
        profile_name = "+".join(new_profile)
        logger.info(f"[CanaryEngine] Rotated yt-dlp client profile to: {profile_name}")
        return profile_name

    @classmethod
    async def probe_extractor_health(cls, force: bool = False) -> Dict[str, Any]:
        """
        Canary Probe: Tests resolving capability on audio stream.
        Bounded with 45s cooldown, tight timeouts, and SoundCloud fallback verification.
        Never bypasses access controls, invents fake tokens, or loops indefinitely.
        """
        now = time.monotonic()
        if not force and cls._last_probe_result and (now - cls._last_probe_time) < cls.PROBE_COOLDOWN_SECONDS:
            return dict(cls._last_probe_result)

        start_t = time.time()
        test_target = "ytsearch1:lofi beats"
        cookie_diag = get_cookie_diagnostics()

        yt_ok = False
        yt_reason = "No stream format"
        latency = 0.0

        # 1. Bounded YouTube probe (4.0s timeout with active profile)
        profile = cls.PROFILE_PRESETS[cls._active_profile_index % len(cls.PROFILE_PRESETS)]
        try:
            opts = _build_ytdl_options(profile)
            ytdl_inst = yt_dlp.YoutubeDL(opts)
            data = await _run_ytdlp(
                functools.partial(ytdl_inst.extract_info, test_target, download=False),
                timeout=4.0,
                operation="stream_probe",
                correlation_id=f"PROBE-{uuid.uuid4().hex[:8].upper()}",
            )
            entry = data["entries"][0] if "entries" in data and data["entries"] else data
            stream_url = entry.get("url") if entry else None
            if not stream_url and entry and "formats" in entry:
                for fmt in entry["formats"]:
                    if fmt.get("acodec") != "none" and fmt.get("url"):
                        stream_url = fmt["url"]
                        break
            if stream_url:
                yt_ok = True
                latency = round((time.time() - start_t) * 1000, 1)
        except Exception as e:
            raw_err = _format_error(e)
            logger.debug(
                "[ExtractorProbe] provider=youtube operation=stream_probe exception_type=%s",
                type(e).__name__,
            )
            if "PO-Token" in raw_err or "Sign in" in raw_err or "bot" in raw_err.lower():
                yt_reason = "YouTube anti-bot verification (GVS / PO-Token or optional cookies helpful)"
            elif "timeout" in raw_err.lower() or "timed out" in raw_err.lower():
                yt_reason = "Resolution operation timed out"
            elif not cookie_diag.get("is_valid") and cookie_diag.get("present"):
                expired = cookie_diag.get("expired_tokens", [])
                yt_reason = f"Expired YouTube cookies ({', '.join(expired)}). Fresh cookies or public playback required."
            elif not cookie_diag.get("present"):
                yt_reason = "YouTube public access restriction (optional cookies /etc/secrets/cookies.txt may help)"
            else:
                yt_reason = raw_err[:80]

        if yt_ok:
            res = {
                "operational": True,
                "youtube_operational": True,
                "soundcloud_operational": False,
                "active_source": "YouTube",
                "profile": "+".join(profile),
                "latency_ms": latency,
                "message": f"Operational ({latency}ms latency via YouTube)",
                "cookie_status": cookie_diag.get("status"),
            }
            cls._last_probe_time = now
            cls._last_probe_result = res
            return res

        # 2. YouTube failed - SoundCloud is completely disabled by configuration
        res = {
            "operational": False,
            "youtube_operational": False,
            "soundcloud_operational": False,
            "active_source": None,
            "profile": "+".join(profile),
            "latency_ms": 0.0,
            "message": f"YouTube playback unavailable ({yt_reason}). SoundCloud is disabled by configuration.",
            "cookie_status": cookie_diag.get("status"),
        }

        cls._last_probe_time = now
        cls._last_probe_result = res
        return res

    @classmethod
    def rotate_po_token(cls) -> Tuple[bool, str]:
        """Rotates to next PO-Token in data/tokens.json if available."""
        token_data = _load_po_tokens_and_cookies()
        tokens = token_data.get("tokens", [])
        if not tokens:
            return False, "No secondary PO-Tokens configured in data/tokens.json."

        curr_token = token_data.get("active_po_token", "")
        try:
            curr_idx = tokens.index(curr_token) if curr_token in tokens else -1
            next_token = tokens[(curr_idx + 1) % len(tokens)]
        except Exception:
            next_token = tokens[0]

        token_data["active_po_token"] = next_token
        token_data["last_rotated"] = time.time()
        try:
            TOKENS_FILE.write_text(json.dumps(token_data, indent=2))
        except Exception as e:
            logger.warning(
                "[Resolver] YouTube token cache write failed (exception_type=%s)",
                type(e).__name__,
            )

        msg = "Successfully rotated to the next YouTube PO-Token."
        logger.info(f"[TokenRotator] {msg}")
        return True, msg

    @classmethod
    def _parse_entry(cls, data: Any, requester_id: int, requester_name: str) -> Optional[QueuedTrack]:
        """Parse raw yt-dlp dictionary into a validated QueuedTrack, filtering DRM and invalid formats."""
        if not data:
            return None
        entry = data["entries"][0] if "entries" in data and data["entries"] else data
        if not entry:
            return None

        stream_url = entry.get("url")
        if not stream_url and "formats" in entry:
            # 1. Best audio non-DRM format
            for fmt in entry["formats"]:
                if fmt.get("acodec") != "none" and fmt.get("url") and not fmt.get("has_drm"):
                    stream_url = fmt["url"]
                    break
            # 2. Any playable non-DRM format
            if not stream_url:
                for fmt in entry["formats"]:
                    if fmt.get("url") and not fmt.get("has_drm"):
                        stream_url = fmt["url"]
                        break

        if not stream_url:
            return None

        track_url = entry.get("webpage_url")
        if not track_url and entry.get("id"):
            extractor = str(entry.get("extractor_key") or entry.get("extractor") or "").lower()
            source_url = str(entry.get("original_url") or "")
            if "youtube" in extractor or "youtu" in source_url:
                track_url = f"https://www.youtube.com/watch?v={entry['id']}"

        return QueuedTrack(
            title=entry.get("title", "Unknown Title"),
            url=track_url or entry.get("url", ""),
            stream_url=stream_url,
            duration=int(entry.get("duration", 0) or 0),
            requester_id=requester_id,
            requester_name=requester_name,
            artist=entry.get("uploader") or entry.get("channel", "Unknown Artist"),
            thumbnail=entry.get("thumbnail"),
        )

    @classmethod
    async def search(
        cls,
        query: str,
        limit: int = 5,
        correlation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search YouTube for tracks matching query with deduplication, in-memory caching, transient retry, and candidate ranking."""
        cache_key = f"original-v4:{limit}:{query.strip().lower()}"
        if cache_key in cls._search_cache:
            return cls._search_cache[cache_key]

        # Deduplicate concurrent identical search queries to prevent worker starvation
        if cache_key in cls._pending_search_tasks and not cls._pending_search_tasks[cache_key].done():
            logger.info(
                "[Search] provider=youtube operation=search correlation_id=%s outcome=joined_pending_search query=%r",
                correlation_id,
                _safe_query_for_log(query),
            )
            try:
                res = await asyncio.shield(cls._pending_search_tasks[cache_key])
                if res is not None:
                    return res
            except Exception:
                pass

        async def _execute_search() -> List[Dict[str, Any]]:
            corr_id = correlation_id or uuid.uuid4().hex[:8].upper()
            fetch_count = max(limit * 3, 15) if not query.startswith("http") else limit
            search_query = f"ytsearch{fetch_count}:{query}" if not query.startswith("http") else query

            data = None
            search_timeout = float(os.getenv("YTDLP_SEARCH_TIMEOUT", "8.0"))
            # 1. Primary search with bounded timeout
            try:
                primary_opts = _build_ytdl_options(["android"], extract_flat=True)
                ydl_instance = yt_dlp.YoutubeDL(primary_opts)
                data = await _run_ytdlp(
                    functools.partial(ydl_instance.extract_info, search_query, download=False, process=False),
                    timeout=search_timeout,
                    operation="search",
                    correlation_id=corr_id,
                )
            except Exception as e:
                logger.info(
                    "[Resolver] provider=youtube operation=search corr_id=%s exception_type=%s outcome=primary_failed",
                    corr_id,
                    type(e).__name__,
                )
                data = None

            # 2. Configurable 1-retry fallback for transient network/client timeouts
            if not data:
                try:
                    retry_opts = _build_ytdl_options(["web", "mweb"], extract_flat=True)
                    ydl_retry = yt_dlp.YoutubeDL(retry_opts)
                    data = await _run_ytdlp(
                        functools.partial(ydl_retry.extract_info, search_query, download=False, process=False),
                        timeout=search_timeout,
                        operation="search_retry",
                        correlation_id=corr_id,
                        retry_count=1,
                    )
                except Exception as retry_err:
                    logger.info(
                        "[Resolver] provider=youtube operation=search_retry corr_id=%s exception_type=%s outcome=retry_failed",
                        corr_id,
                        type(retry_err).__name__,
                    )
                    data = None

            entries = (data.get("entries") if isinstance(data, dict) and "entries" in data else [data]) if data else []
            raw_candidates: List[Dict[str, Any]] = []
            for entry in (entries or []):
                if not entry or entry.get("has_drm"):
                    continue

                thumb = entry.get("thumbnail")
                if not thumb and entry.get("thumbnails"):
                    thumbs = entry.get("thumbnails")
                    if isinstance(thumbs, list) and thumbs:
                        thumb = thumbs[-1].get("url") or thumbs[0].get("url")
                vid_id = entry.get("id")
                if not thumb and vid_id:
                    thumb = f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"

                track_url = entry.get("webpage_url") or (f"https://www.youtube.com/watch?v={vid_id}" if vid_id else entry.get("url", ""))
                track_id = vid_id or f"yt_{abs(hash(entry.get('title', '')))}"
                uploader_name = entry.get("uploader") or entry.get("channel") or ""

                raw_candidates.append({
                    "id": str(track_id),
                    "title": entry.get("title", "Unknown Track"),
                    "url": track_url,
                    "duration": int(entry.get("duration", 0) or 0),
                    "artist": uploader_name or "Unknown Artist",
                    "uploader": uploader_name,
                    "channel": entry.get("channel") or uploader_name,
                    "channel_is_verified": bool(entry.get("channel_is_verified")),
                    "thumbnail": thumb,
                    "provider": "youtube",
                })

            intent = analyze_query_intent(query)
            scored_candidates = []
            for c in raw_candidates:
                if not is_original_recording_candidate(c, intent):
                    continue
                s, r = score_candidate_detailed(c, intent)
                title_match_ratio, combined_match_ratio, title_confidence = _candidate_match_metrics(c, intent)
                scored_candidates.append(
                    (
                        {
                            **c,
                            "_match_score": s,
                            "_match_reasons": r,
                            "_title_match_ratio": title_match_ratio,
                            "_title_match_confidence": title_confidence,
                            "_combined_match_ratio": combined_match_ratio,
                        },
                        s,
                        r,
                    )
                )

            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            normalized_query = " ".join(query.split())
            for rank, (candidate, score, reasons) in enumerate(scored_candidates[:5], 1):
                video_id = candidate.get("id")
                canonical_url = (
                    f"https://www.youtube.com/watch?v={video_id}"
                    if video_id and not str(video_id).startswith("yt_")
                    else None
                )
                logger.info(
                    "[Search] provider=youtube strategy=ytsearch correlation_id=%s "
                    "query=%r normalized_query=%r rank=%d title=%r channel=%r "
                    "duration_seconds=%d video_id=%s url=%s score=%.1f "
                    "title_match=%.2f reasons=%s",
                    corr_id,
                    _safe_query_for_log(query),
                    _safe_query_for_log(normalized_query),
                    rank,
                    candidate.get("title"),
                    candidate.get("uploader") or candidate.get("channel") or candidate.get("artist"),
                    candidate.get("duration", 0),
                    video_id,
                    canonical_url or "unavailable",
                    score,
                    candidate.get("_title_match_ratio", 0.0),
                    ",".join(reasons),
                )

            search_results = [
                {**candidate, "original_source_match": True}
                for candidate, _, _ in scored_candidates[:limit]
            ]
            if search_results:
                cls._search_cache[cache_key] = search_results
            return search_results

        search_task = asyncio.create_task(_execute_search())
        cls._pending_search_tasks[cache_key] = search_task

        def _cleanup_search_task(f: asyncio.Future[Any]) -> None:
            if cls._pending_search_tasks.get(cache_key) is f:
                cls._pending_search_tasks.pop(cache_key, None)

        search_task.add_done_callback(_cleanup_search_task)
        try:
            return await search_task
        except Exception:
            return []

    @classmethod
    async def resolve_spotify_metadata(cls, spotify_url: str) -> Optional[Dict[str, Any]]:
        """Extract title, artist, thumbnail from Spotify URLs via API / oEmbed."""
        from music_bot.services.spotify_service import SpotifyItemType, SpotifyService, SpotifyTrack, SpotifyCollection

        try:
            res = await SpotifyService.resolve_url(spotify_url)
            if res:
                if isinstance(res, SpotifyTrack):
                    return res.to_dict()
                elif isinstance(res, SpotifyCollection):
                    d = res.to_dict()
                    first_track = res.tracks[0] if res.tracks else None
                    d["title"] = res.title
                    d["artist"] = res.author_or_artist
                    d["search_query"] = first_track.search_query if first_track else f"{res.title} {res.author_or_artist}"
                    return d
        except Exception as e:
            logger.warning(
                "[Resolver] provider=spotify operation=metadata exception_type=%s",
                type(e).__name__,
            )

        try:
            fb = await SpotifyService.resolve_via_oembed(spotify_url)
            if fb:
                return fb.to_dict()
        except Exception as fb_err:
            logger.warning(
                "[Resolver] provider=spotify operation=oembed_fallback exception_type=%s",
                type(fb_err).__name__,
            )

        return None

    @classmethod
    async def resolve_spotify_collection(
        cls, spotify_url: str, limit: int = 100
    ) -> Optional[Dict[str, Any]]:
        """Resolve Spotify albums or playlists into collection dictionary."""
        from music_bot.services.spotify_service import SpotifyItemType, SpotifyService
        parsed = SpotifyService.match_spotify_link(spotify_url)
        if not parsed:
            return None
        item_type, item_id = parsed
        if item_type == SpotifyItemType.ALBUM:
            col = await SpotifyService.get_album(item_id, limit=limit)
            return col.to_dict() if col else None
        elif item_type == SpotifyItemType.PLAYLIST:
            col = await SpotifyService.get_playlist(item_id, limit=limit)
            return col.to_dict() if col else None
        return None

    @classmethod
    async def resolve_soundcloud_track(
        cls, query: str, requester_id: int, requester_name: str
    ) -> Optional[QueuedTrack]:
        """SoundCloud resolution provider for ultra-fast, zero-interruption playback."""
        clean = query.strip()
        search_target = clean if clean.startswith("http") else f"scsearch2:{clean}"
        try:
            sc_opts = {
                "quiet": True,
                "format": "bestaudio/best/worst",
                "noplaylist": True,
                "ignoreerrors": True,
                "socket_timeout": 8,
                "retries": 1,
            }
            ydl = yt_dlp.YoutubeDL(sc_opts)
            data = await _run_ytdlp(
                functools.partial(ydl.extract_info, search_target, download=False),
                timeout=15.0,
                operation="soundcloud_search",
                provider="soundcloud",
                correlation_id=uuid.uuid4().hex[:8].upper(),
            )
            if not data:
                return None
            raw_entries = data.get("entries") if isinstance(data, dict) and "entries" in data else [data]
            entries = list(raw_entries) if raw_entries else []
            for entry in entries:
                if not entry:
                    continue
                s_url = entry.get("url")
                if not s_url and "formats" in entry:
                    for fmt in entry.get("formats", []):
                        if fmt and fmt.get("url"):
                            s_url = fmt["url"]
                            break
                # If s_url is a soundcloud webpage rather than a media stream, extract stream from that track URL
                web_url = entry.get("webpage_url") or entry.get("url")
                if not s_url or (isinstance(s_url, str) and "soundcloud.com" in s_url and not any(p in s_url for p in (".m3u8", ".mp3", ".aac", ".opus", "media-streaming", "sndcdn"))):
                    if web_url and web_url.startswith("http"):
                        try:
                            direct_info = await _run_ytdlp(
                                functools.partial(ydl.extract_info, web_url, download=False),
                                timeout=6.0,
                                operation="soundcloud_track_resolution",
                                provider="soundcloud",
                                correlation_id=uuid.uuid4().hex[:8].upper(),
                            )
                            if direct_info:
                                s_url = direct_info.get("url")
                                if not s_url and "formats" in direct_info:
                                    for fmt in direct_info.get("formats", []):
                                        if fmt and fmt.get("url"):
                                            s_url = fmt["url"]
                                            break
                                if s_url:
                                    entry = direct_info
                        except Exception as d_err:
                            logger.debug(
                                "[Resolver] provider=soundcloud operation=track_resolution exception_type=%s",
                                type(d_err).__name__,
                            )
                if s_url:
                    return QueuedTrack(
                        title=entry.get("title", clean),
                        url=entry.get("webpage_url") or entry.get("url", clean),
                        stream_url=s_url,
                        duration=int(entry.get("duration", 0) or 0),
                        requester_id=requester_id,
                        requester_name=requester_name,
                        artist=entry.get("uploader") or entry.get("channel", "SoundCloud Artist"),
                        thumbnail=entry.get("thumbnail"),
                    )
        except Exception as e:
            logger.warning(
                "[Resolver] provider=soundcloud operation=resolution exception_type=%s",
                type(e).__name__,
            )
        return None

    @classmethod
    async def resolve_track(
        cls,
        query_or_url: str,
        requester_id: int,
        requester_name: str,
        title_hint: Optional[str] = None,
        artist_hint: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[QueuedTrack]:
        """
        Public resolver method. Deduplicates concurrent resolutions, checks in-memory
        and optional Redis cache (TTL ~1 hour), and guarantees non-blocking async execution.
        """
        correlation_id = correlation_id or uuid.uuid4().hex[:8].upper()
        cache_key = f"original-v4:{query_or_url.strip().lower()}"
        now = time.time()

        # 1. Check in-memory track cache (TTL: CACHE_TTL ~ 1 hour)
        if cache_key in cls._track_cache:
            cached_track, cached_time = cls._track_cache[cache_key]
            if now - cached_time < CACHE_TTL:
                logger.info(
                    "[Resolver] provider=youtube operation=resolve_cache correlation_id=%s outcome=memory_hit",
                    correlation_id,
                )
                cached = QueuedTrack(
                    title=cached_track.title,
                    url=cached_track.url,
                    stream_url=cached_track.stream_url,
                    duration=cached_track.duration,
                    requester_id=requester_id,
                    requester_name=requester_name,
                    artist=cached_track.artist,
                    thumbnail=cached_track.thumbnail,
                )
                setattr(cached, "_correlation_id", correlation_id)
                return cached

        # 2. Check optional Redis cache if configured
        redis_c = await get_redis_client()
        if redis_c:
            try:
                cached_json = await redis_c.get(f"mm:track:{cache_key}")
                if cached_json:
                    data = json.loads(cached_json)
                    restored_track = QueuedTrack(
                        title=data.get("title", "Unknown Track"),
                        url=data.get("url", ""),
                        stream_url=data.get("stream_url", ""),
                        duration=data.get("duration", 0),
                        requester_id=requester_id,
                        requester_name=requester_name,
                        artist=data.get("artist", "Unknown Artist"),
                        thumbnail=data.get("thumbnail"),
                    )
                    cls._track_cache[cache_key] = (restored_track, now)
                    setattr(restored_track, "_correlation_id", correlation_id)
                    logger.info(
                        "[Resolver] provider=youtube operation=resolve_cache correlation_id=%s outcome=redis_hit",
                        correlation_id,
                    )
                    return restored_track
            except Exception as r_err:
                logger.debug(f"[Resolver] Redis cache lookup failed: {_format_error(r_err)}")

        # 3. Deduplicate concurrent resolves of the same query
        if cache_key in cls._pending_tasks and not cls._pending_tasks[cache_key].done():
            logger.info(
                "[Resolver] provider=youtube operation=resolve correlation_id=%s outcome=joined_pending",
                correlation_id,
            )
            task = cls._pending_tasks[cache_key]
            try:
                res = await asyncio.shield(task)
                if res:
                    duplicate = QueuedTrack(
                        title=res.title,
                        url=res.url,
                        stream_url=res.stream_url,
                        duration=res.duration,
                        requester_id=requester_id,
                        requester_name=requester_name,
                        artist=res.artist,
                        thumbnail=res.thumbnail,
                    )
                    setattr(duplicate, "_correlation_id", correlation_id)
                    return duplicate
            except Exception:
                pass

        # 4. Create background resolution task
        task = asyncio.create_task(
            cls._execute_resolution_pipeline(
                query_or_url,
                requester_id,
                requester_name,
                title_hint=title_hint,
                artist_hint=artist_hint,
                correlation_id=correlation_id,
            )
        )
        cls._pending_tasks[cache_key] = task

        def _on_done(f: asyncio.Future):
            if cls._pending_tasks.get(cache_key) is f:
                cls._pending_tasks.pop(cache_key, None)
            try:
                res = f.result()
                if res:
                    cls._track_cache[cache_key] = (res, time.time())
                    # Write-through to Redis asynchronously
                    if redis_c:
                        async def _write_redis(k: str, t: QueuedTrack):
                            try:
                                payload = json.dumps({
                                    "title": t.title,
                                    "url": t.url,
                                    "stream_url": t.stream_url,
                                    "duration": t.duration,
                                    "artist": t.artist,
                                    "thumbnail": t.thumbnail,
                                })
                                await redis_c.setex(f"mm:track:{k}", CACHE_TTL, payload)
                            except Exception:
                                pass
                        asyncio.create_task(_write_redis(cache_key, res))
            except Exception:
                pass

        task.add_done_callback(_on_done)
        resolved = await task
        if resolved:
            out_track = QueuedTrack(
                title=resolved.title,
                url=resolved.url,
                stream_url=resolved.stream_url,
                duration=resolved.duration,
                requester_id=requester_id,
                requester_name=requester_name,
                artist=resolved.artist,
                thumbnail=resolved.thumbnail,
            )
            setattr(out_track, "_correlation_id", correlation_id)
            if hasattr(resolved, "provider"):
                setattr(out_track, "provider", getattr(resolved, "provider"))
            logger.info(
                "[Resolver] provider=%s operation=resolve correlation_id=%s "
                "outcome=resolved title=%r video_id=%s",
                getattr(out_track, "provider", "youtube"),
                correlation_id,
                out_track.title,
                _video_id_from_url(out_track.url) or "unavailable",
            )
            return out_track
        return None

    @classmethod
    def clear_caches(cls) -> None:
        """Clear all in-memory track resolution and search caches."""
        cls._track_cache.clear()
        cls._search_cache.clear()
        cls._pending_search_tasks.clear()
        logger.info("[Resolver] Cleared in-memory track and search caches.")

    @classmethod
    async def pre_resolve_track(cls, track: QueuedTrack) -> None:
        """
        Pre-resolve the next track in the queue while the current one plays.
        Populates stream_url, duration, and thumbnail ahead of time for gapless transition.
        """
        if not track or track.stream_url:
            return
        try:
            logger.info(f"[PreResolver] Lookahead resolving upcoming queue track: '{track.title}'")
            fresh = await cls.resolve_track(
                track.url or track.title, track.requester_id, track.requester_name
            )
            if fresh and fresh.stream_url:
                if apply_resolved_track(track, fresh):
                    logger.info(
                        "[PreResolver] operation=stream_prefetch correlation_id=%s "
                        "outcome=success title=%r video_id=%s",
                        getattr(track, "_correlation_id", "unavailable"),
                        track.title,
                        _video_id_from_url(track.url) or "unavailable",
                    )
                else:
                    logger.error(
                        "[PreResolver] operation=stream_prefetch correlation_id=%s "
                        "outcome=identity_mismatch queued_title=%r queued_video_id=%s "
                        "resolved_title=%r resolved_video_id=%s",
                        getattr(track, "_correlation_id", "unavailable"),
                        track.title,
                        _video_id_from_url(track.url) or "unavailable",
                        fresh.title,
                        _video_id_from_url(fresh.url) or "unavailable",
                    )
        except Exception as e:
            logger.debug(
                "[PreResolver] Lookahead resolution failed (exception_type=%s)",
                type(e).__name__,
            )

    @classmethod
    async def autocomplete_search(cls, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """
        Instant suggestions (<200ms) for slash command autocomplete.
        Checks matching cached queries and fetches YouTube search suggestions via Google's lightweight suggest API.
        """
        q = query.strip()
        if not q or len(q) < 2:
            return []

        results: List[Dict[str, str]] = []
        seen = set()

        # 1. Instant check: match local track cache for real resolved tracks
        q_lower = q.lower()
        for k, (cached_track, _) in list(cls._track_cache.items()):
            if q_lower in cached_track.title.lower() or (cached_track.artist and q_lower in cached_track.artist.lower()):
                if cached_track.title not in seen:
                    seen.add(cached_track.title)
                    results.append({
                        "title": cached_track.title,
                        "artist": cached_track.artist or "Resolved Track",
                        "url": cached_track.url or cached_track.title,
                    })
                    if len(results) >= limit:
                        return results

        # 2. Check cached search candidates for genuine songs
        for search_key, candidates in list(cls._search_cache.items()):
            for cand in candidates:
                cand_title = cand.get("title", "")
                cand_artist = cand.get("artist") or cand.get("uploader") or cand.get("channel") or ""
                if q_lower in cand_title.lower() or q_lower in cand_artist.lower():
                    if cand_title and cand_title not in seen:
                        seen.add(cand_title)
                        results.append({
                            "title": cand_title,
                            "artist": cand_artist or "YouTube Music",
                            "url": cand.get("url") or cand_title,
                        })
                        if len(results) >= limit:
                            return results

        # 3. Query playback history from database if available
        try:
            from music_bot.database.db import MusicDatabase
            from music_bot.config import MUSIC_DATABASE_PATH
            import aiosqlite
            if MUSIC_DATABASE_PATH.exists():
                async with aiosqlite.connect(str(MUSIC_DATABASE_PATH)) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute(
                        "SELECT DISTINCT title, artist, url FROM music_history WHERE title LIKE ? OR artist LIKE ? ORDER BY id DESC LIMIT ?",
                        (f"%{q}%", f"%{q}%", limit),
                    ) as cur:
                        for row in await cur.fetchall():
                            t_title = row["title"]
                            t_artist = row["artist"] or "History"
                            if t_title and t_title not in seen:
                                seen.add(t_title)
                                results.append({
                                    "title": t_title,
                                    "artist": t_artist,
                                    "url": row["url"] or t_title,
                                })
                                if len(results) >= limit:
                                    return results
        except Exception:
            pass

        # 4. Fallback: Return clean play action for current query (no generic spam)
        if not results:
            results.append({
                "title": f"Play '{q}'",
                "artist": "Direct Search",
                "url": q,
            })

        return results[:limit]


    @classmethod
    async def _execute_resolution_pipeline(
        cls,
        query_or_url: str,
        requester_id: int,
        requester_name: str,
        title_hint: Optional[str] = None,
        artist_hint: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[QueuedTrack]:
        """
        Internal multi-tiered resolution pipeline strictly utilizing authorized YouTube clients.
        SoundCloud is completely disabled.
        Decoupled two-stage execution:
        Stage 1: Fast flat search (extract_flat=True) to retrieve candidate metadata in <1.5s.
        Stage 2: Score candidates based on query intent, language matching, and original vs remix.
        Stage 3: Extract audio stream for top candidate(s) with fallback tiers.
        """
        start_t = time.time()
        spotify_info = None
        cleaned_query = query_or_url
        is_spotify = "spotify.com" in query_or_url or query_or_url.startswith("spotify:")
        if is_spotify:
            spotify_info = await cls.resolve_spotify_metadata(query_or_url)
            if spotify_info:
                cleaned_query = spotify_info.get("search_query", query_or_url)
                logger.info(f"[Resolver] Resolved Spotify metadata: '{spotify_info.get('title')}' by '{spotify_info.get('artist')}'")
        # 1. Multi-provider URL detection & metadata extraction
        apple_info = None
        if "apple.com" in query_or_url:
            from music_bot.services.apple_music_service import AppleMusicService
            apple_info = await AppleMusicService.resolve_url(query_or_url)
            if apple_info:
                cleaned_query = apple_info.get("search_query", query_or_url)
                logger.info(f"[Resolver] Resolved Apple Music metadata: '{apple_info.get('title')}' by '{apple_info.get('artist')}'")
            else:
                cleaned_query = query_or_url.split("/")[-1].split("?")[0].replace("-", " ")

        intent = analyze_query_intent(cleaned_query)

        def _apply_metadata_enhancements(t: Optional[QueuedTrack]) -> Optional[QueuedTrack]:
            if t and spotify_info:
                if spotify_info.get("title"):
                    t.title = spotify_info["title"]
                if spotify_info.get("artist") and spotify_info["artist"] != "Unknown Artist":
                    t.artist = spotify_info["artist"]
                if spotify_info.get("thumbnail"):
                    t.thumbnail = spotify_info["thumbnail"]
                if spotify_info.get("url"):
                    t.url = spotify_info["url"]
                elif query_or_url.startswith("http"):
                    t.url = query_or_url
                setattr(t, "provider", "spotify")
            elif t and apple_info:
                if apple_info.get("title"):
                    t.title = apple_info["title"]
                if apple_info.get("artist") and apple_info["artist"] != "Unknown Artist":
                    t.artist = apple_info["artist"]
                if apple_info.get("thumbnail"):
                    t.thumbnail = apple_info["thumbnail"]
                if apple_info.get("url"):
                    t.url = apple_info["url"]
                elif query_or_url.startswith("http"):
                    t.url = query_or_url
                setattr(t, "provider", "apple_music")
            return t

        cls.last_resolver_error = None
        corr_id = correlation_id or uuid.uuid4().hex[:8].upper()
        normalized_query = " ".join(cleaned_query.split())
        logger.info(
            "[Resolver] provider=youtube operation=resolve correlation_id=%s "
            "query=%r normalized_query=%r strategy=%s",
            corr_id,
            _safe_query_for_log(query_or_url),
            _safe_query_for_log(normalized_query),
            "direct_url" if cleaned_query.startswith("http") else "ytsearch",
        )
        failed_stage = "init"
        is_direct_url = cleaned_query.startswith("http://") or cleaned_query.startswith("https://")

        # 2. SSRF-validated direct audio stream resolution
        if is_direct_url and not is_spotify and not ("apple.com" in cleaned_query) and not ("youtube.com" in cleaned_query or "youtu.be" in cleaned_query):
            if "soundcloud.com" in cleaned_query:
                cls.last_resolver_error = (
                    f"[UNSUPPORTED_PROVIDER] SoundCloud is not supported by policy. "
                    f"Please use YouTube, Audius, or Jamendo (Ref: MM-{corr_id})."
                )
                return None

            from music_bot.services.network_security import validate_safe_url
            is_safe, sec_err, canonical_url = validate_safe_url(cleaned_query)
            if not is_safe:
                logger.warning(f"[Resolver] Blocked unsafe direct URL '{cleaned_query}': {sec_err}")
                cls.last_resolver_error = f"[SECURITY_VIOLATION] (Ref: MM-{corr_id}) Direct URL blocked: {sec_err}"
                return None

            # Attempt direct audio extraction via yt-dlp with SSRF protection
            try:
                direct_opts = _build_ytdl_options(None, use_cookies=False)
                direct_ydl = yt_dlp.YoutubeDL(direct_opts)
                direct_data = await _run_ytdlp(
                    functools.partial(direct_ydl.extract_info, canonical_url, download=False),
                    timeout=10.0,
                    operation="direct_url_extract",
                    correlation_id=corr_id,
                )
                if direct_data:
                    direct_track = cls._parse_entry(direct_data, requester_id, requester_name)
                    if direct_track and direct_track.stream_url:
                        # Verify stream URL is also safe against SSRF
                        s_safe, s_err, _ = validate_safe_url(direct_track.stream_url)
                        if s_safe:
                            direct_track = _apply_metadata_enhancements(direct_track)
                            setattr(direct_track, "provider", "direct_audio")
                            logger.info(f"[Resolver] [Ref: MM-{corr_id}] Direct audio URL resolved -> '{direct_track.title}'")
                            return direct_track
            except Exception as direct_exc:
                logger.info(f"[Resolver] [Ref: MM-{corr_id}] Direct URL extraction failed: {_format_error(direct_exc)}")

        def _entry_matches_original_policy(data: Any) -> bool:
            if not isinstance(data, dict):
                return False
            candidate = {
                "title": data.get("title") or "",
                "uploader": data.get("uploader") or data.get("channel") or data.get("artist") or "",
                "channel": data.get("channel") or data.get("uploader") or "",
                "channel_is_verified": bool(data.get("channel_is_verified")),
            }
            candidate_intent = analyze_query_intent(candidate["title"]) if is_direct_url else intent
            return is_original_recording_candidate(
                candidate,
                candidate_intent,
                spotify_meta=spotify_info,
                title_hint=title_hint,
                artist_hint=artist_hint,
            )

        def _entry_matches_selected_video(data: Any, target_url: str, operation: str) -> bool:
            expected_id = _video_id_from_url(target_url)
            if not expected_id:
                return True
            actual_id = None
            if isinstance(data, dict):
                actual_id = str(data.get("id") or "") or _video_id_from_url(
                    data.get("webpage_url") or data.get("original_url")
                )
            if actual_id != expected_id:
                logger.error(
                    "[Resolver] provider=youtube operation=%s correlation_id=%s "
                    "outcome=selected_video_mismatch expected_video_id=%s actual_video_id=%s",
                    operation,
                    corr_id,
                    expected_id,
                    actual_id or "unavailable",
                )
                return False
            return True

        candidate_urls: List[str] = []

        if is_direct_url and not is_spotify:
            candidate_urls = [cleaned_query]
        else:
            # Stage 1: Candidate selection from search cache or ytsearch
            failed_stage = "search"
            search_entries: List[Dict[str, Any]] = []
            search_error: Optional[str] = None

            # First attempt instant retrieval from cls.search cache
            try:
                cached_search = await cls.search(
                    cleaned_query,
                    limit=5,
                    correlation_id=corr_id,
                )
                if cached_search:
                    candidate_urls = [c["url"] for c in cached_search if c.get("url")]
            except Exception:
                pass

            if not candidate_urls:
                # Query up to 15 candidate tracks from YouTube for comprehensive original-vs-remix ranking
                search_query = f"ytsearch15:{cleaned_query}"
                active_cooldown = youtube_cooldown_status()
                if active_cooldown["cooldown_active"]:
                    search_error = (
                        f"YouTube {active_cooldown['last_failure']} cooldown active "
                        f"({active_cooldown['cooldown_remaining_seconds']} seconds remaining)"
                    )
                    logger.info(
                        "[Resolver] [Ref: MM-%s] provider=youtube operation=search_fallback "
                        "outcome=skipped_cooldown category=%s remaining_seconds=%s",
                        corr_id,
                        active_cooldown["last_failure"],
                        active_cooldown["cooldown_remaining_seconds"],
                    )
                else:
                     try:
                         flat_opts = _build_ytdl_options(["android"], extract_flat=True, use_cookies=False)
                         flat_ydl = yt_dlp.YoutubeDL(flat_opts)
                         search_timeout = float(os.getenv("YTDLP_SEARCH_TIMEOUT", "8.0"))
                         search_data = await _run_ytdlp(
                             functools.partial(flat_ydl.extract_info, search_query, download=False, process=False),
                             timeout=search_timeout,
                             operation="search_fallback",
                             correlation_id=corr_id,
                         )
                         if search_data:
                             entries = search_data.get("entries") if isinstance(search_data, dict) and "entries" in search_data else [search_data]
                             search_entries = [e for e in (entries or []) if e and not e.get("has_drm")]
                     except Exception as search_exc:
                         search_error = _format_error(search_exc)
                         logger.warning(f"[Resolver] [Ref: MM-{corr_id}] Search stage notice for '{cleaned_query[:50]}': {search_error}")
 
 
                if not search_entries:
                    dur = time.time() - start_t
                    if search_error and ("TimeoutError" in search_error or "timed out" in search_error.lower()):
                        cat = "TIMEOUT"
                        reason = f"Search timed out while contacting YouTube for '{cleaned_query[:60]}'."
                    elif search_error:
                        cat = "SEARCH_FAILURE"
                        reason = f"YouTube search failure for '{cleaned_query[:60]}': {search_error}"
                    else:
                        cat = "NO_RESULTS"
                        reason = f"YouTube search completed but returned no candidates for '{cleaned_query[:60]}'."

                    # Attempt multi-provider fallback (Audius / Jamendo) before failing
                    try:
                        from music_bot.services.alternative_providers import AudiusProviderService, JamendoProviderService
                        audius_candidates = await AudiusProviderService.search(cleaned_query, limit=3)
                        for cand in audius_candidates:
                            if is_alternative_provider_candidate(cand, intent):
                                fb_track = QueuedTrack(
                                    title=cand["title"],
                                    url=cand["url"],
                                    stream_url=cand["stream_url"],
                                    duration=cand["duration"],
                                    requester_id=requester_id,
                                    requester_name=requester_name,
                                    artist=cand["artist"],
                                    thumbnail=cand.get("thumbnail"),
                                )
                                fb_track = _apply_metadata_enhancements(fb_track)
                                setattr(fb_track, "provider", "audius")
                                logger.info(
                                    f"[Resolver] [Ref: MM-{corr_id}] Fallback provider Audius resolved '{cleaned_query[:40]}' -> '{fb_track.title}'"
                                )
                                return fb_track

                        jamendo_candidates = await JamendoProviderService.search(cleaned_query, limit=3)
                        for cand in jamendo_candidates:
                            if is_original_recording_candidate(cand, intent):
                                fb_track = QueuedTrack(
                                    title=cand["title"],
                                    url=cand["url"],
                                    stream_url=cand["stream_url"],
                                    duration=cand["duration"],
                                    requester_id=requester_id,
                                    requester_name=requester_name,
                                    artist=cand["artist"],
                                    thumbnail=cand.get("thumbnail"),
                                )
                                fb_track = _apply_metadata_enhancements(fb_track)
                                setattr(fb_track, "provider", "jamendo")
                                logger.info(
                                    f"[Resolver] [Ref: MM-{corr_id}] Fallback provider Jamendo resolved '{cleaned_query[:40]}' -> '{fb_track.title}'"
                                )
                                return fb_track
                    except Exception as fb_exc:
                        logger.debug(f"[Resolver] [Ref: MM-{corr_id}] Pre-search fallback error: {fb_exc}")

                    cls.last_resolver_error = f"[{cat}] (Ref: MM-{corr_id}) {reason}"
                    logger.warning(
                        f"[Resolver] [Ref: MM-{corr_id}] YouTube search returned 0 candidates | query='{cleaned_query[:40]}' | "
                        f"extractor={yt_dlp.version.__version__} | category={cat} | dur={dur:.2f}s"
                    )
                    return None

                # Stage 2: Rank candidates using smart query intent analysis
                failed_stage = "ranking"
                scored_candidates: List[Tuple[Dict[str, Any], float, List[str]]] = []
                for entry in search_entries:
                    if not is_original_recording_candidate(
                        entry,
                        intent,
                        spotify_meta=spotify_info,
                        title_hint=title_hint,
                        artist_hint=artist_hint,
                    ):
                        continue
                    score_val, reasons_list = score_candidate_detailed(
                        entry,
                        intent,
                        spotify_meta=spotify_info,
                        title_hint=title_hint,
                        artist_hint=artist_hint,
                    )
                    scored_candidates.append((entry, score_val, reasons_list))

                if not scored_candidates:
                    cls.last_resolver_error = (
                        f"[NO_ORIGINAL_MATCH] No verified original recording was found for "
                        f"'{cleaned_query[:60]}'. Try including the singer's name or provide a direct link."
                    )
                    logger.warning(f"[Resolver] [Ref: MM-{corr_id}] {cls.last_resolver_error}")
                    return None

                scored_candidates.sort(key=lambda x: x[1], reverse=True)

                # Log candidate ranking scores and reasons for debugging without exposing secrets
                logger.info(
                    f"[Resolver] [Ref: MM-{corr_id}] Ranked {len(scored_candidates)} candidates for query '{cleaned_query[:40]}':\n"
                    + "\n".join(
                        f"  #{i+1} [score={s:.1f}] '{c.get('title')}' by '{c.get('uploader') or c.get('channel')}' | reasons={', '.join(r[:4])}"
                        for i, (c, s, r) in enumerate(scored_candidates[:min(4, len(scored_candidates))])
                    )
                )

                for cand, _, _ in scored_candidates[:3]:
                    c_id = cand.get("id")
                    c_url = f"https://www.youtube.com/watch?v={c_id}" if c_id else (cand.get("url") or cand.get("webpage_url"))
                    if c_url and c_url not in candidate_urls:
                        candidate_urls.append(c_url)

        # Stage 3: Public stream format extraction on selected candidate(s) without cookies
        failed_stage = "stream_extraction"
        last_failure_reason = "No playable audio format returned"
        verification_failed = False
        youtube_rate_limited = False
        youtube_access_blocked = False
        youtube_timed_out = False

        # Emit a safe cookie-health snapshot and respect the upstream cooldown before
        # starting more YouTube extraction requests. A cooldown never blocks the
        # existing alternative-provider fallback for search queries.
        cookie_path = get_active_cookie_file()
        inspect_youtube_cookie_file(cookie_path)
        health_cooldown = youtube_cooldown_status()
        if health_cooldown["cooldown_active"]:
            last_failure_reason = (
                f"YouTube {health_cooldown['last_failure']} cooldown active "
                f"({health_cooldown['cooldown_remaining_seconds']} seconds remaining)"
            )
            youtube_rate_limited = health_cooldown["last_failure"] == "rate_limited"
            candidate_urls = []
            logger.warning(
                "[Resolver] [Ref: MM-%s] provider=youtube operation=stream_extract "
                "outcome=skipped_cooldown category=%s remaining_seconds=%s",
                corr_id,
                health_cooldown["last_failure"],
                health_cooldown["cooldown_remaining_seconds"],
            )
        for cand_idx, target_url in enumerate(candidate_urls[:2], 1):
            t1_msg = ""
            # The extractor may use an 8s socket timeout and retry once. Keep the
            # outer timeout long enough for that bounded retry to finish.
            try:
                tier1_opts = _build_ytdl_options(["ios", "android"], use_cookies=False)
                tier1_ydl = yt_dlp.YoutubeDL(tier1_opts)
                data = await _run_ytdlp(
                    functools.partial(tier1_ydl.extract_info, target_url, download=False),
                    timeout=20.0,
                    operation="stream_extract_tier1",
                    correlation_id=corr_id,
                    retry_count=cand_idx - 1,
                )
                if data:
                    track = cls._parse_entry(data, requester_id, requester_name)
                    if (
                        track
                        and track.stream_url
                        and _entry_matches_selected_video(data, target_url, "stream_extract_tier1")
                        and _entry_matches_original_policy(data)
                    ):
                        track = _apply_metadata_enhancements(track)
                        dur = time.time() - start_t
                        logger.info(
                            f"[Resolver] [Ref: MM-{corr_id}] Public Tier 1 resolved candidate #{cand_idx} '{cleaned_query[:40]}' in {dur:.2f}s -> '{track.title}'"
                        )
                        return track
                    if track:
                        verification_failed = True
                        last_failure_reason = "Original recording could not be verified from title and source metadata"
            except Exception as t1_err:
                t1_msg = _format_error(t1_err)
                record_youtube_failure(t1_msg)
                last_failure_reason = t1_msg
                logger.info(
                    "[Resolver] [Ref: MM-%s] provider=youtube operation=stream_extract_tier1 "
                    "candidate=%d exception_type=%s",
                    corr_id,
                    cand_idx,
                    type(t1_err).__name__,
                )
                if "429" in t1_msg or "too many requests" in t1_msg.lower():
                    youtube_rate_limited = True
                    last_failure_reason = "YouTube is rate-limiting this server (HTTP 429)."
                if _is_youtube_access_challenge(t1_msg):
                    # Repeating other YouTube clients or cookie attempts after an
                    # explicit access challenge wastes time and can worsen rate limits.
                    # Preserve the alternative-provider fallback below for searches.
                    youtube_access_blocked = True
                    last_failure_reason = (
                        "YouTube requires an accepted authenticated session or is "
                        "challenging this server; public extraction was stopped."
                    )
                    logger.warning(
                        "[Resolver] [Ref: MM-%s] provider=youtube operation=stream_extract "
                        "outcome=stopped_access_challenge alternative_fallback=%s",
                        corr_id,
                        not is_direct_url,
                    )
                    break
                # Do not fan out into six more extractor profiles after upstream
                # throttling, access challenges, or a network timeout. Those requests
                # cannot fix the server-side restriction and made failed searches take
                # 30-60+ seconds. Other genuine format/player-response failures retain
                # the existing bounded profile fallbacks.
                t1_lower = t1_msg.lower()
                upstream_blocked_or_slow = any(marker in t1_lower for marker in (
                    "http error 403", "http error 429", "too many requests",
                    "timed out", "timeout", "sign in to confirm", "not a bot",
                    "confirm you're not a bot", "confirm you’re not a bot",
                ))
                if (
                    not upstream_blocked_or_slow
                    and (
                        "format is not available" in t1_lower
                        or "failed to extract any player response" in t1_lower
                        or "player response" in t1_lower
                    )
                ):
                    # Newer YouTube responses may fail for one client profile while
                    # another supported profile still resolves the same public video.
                    # Keep this bounded and verify the returned video ID below.
                    for fallback_clients, fallback_format in (
                        (None, "bestaudio/best"),
                        (["mweb"], "bestaudio/best"),
                        (["tv_downgraded"], "bestaudio/best"),
                        (["android", "ios", "web"], "bestaudio/best"),
                        (["web"], "best"),
                        (["android_vr"], "best"),
                    ):
                        try:
                            fb_opts = _build_ytdl_options(fallback_clients, use_cookies=False)
                            fb_opts["format"] = fallback_format
                            fb_ydl = yt_dlp.YoutubeDL(fb_opts)
                            fb_data = await _run_ytdlp(
                                functools.partial(fb_ydl.extract_info, target_url, download=False),
                                timeout=8.0,
                                operation="stream_extract_format_fallback",
                                correlation_id=corr_id,
                                retry_count=cand_idx,
                            )
                            if fb_data:
                                track = cls._parse_entry(fb_data, requester_id, requester_name)
                                if (
                                    track
                                    and track.stream_url
                                    and _entry_matches_selected_video(
                                        fb_data,
                                        target_url,
                                        "stream_extract_format_fallback",
                                    )
                                    and _entry_matches_original_policy(fb_data)
                                ):
                                    track = _apply_metadata_enhancements(track)
                                    dur = time.time() - start_t
                                    logger.info(
                                        f"[Resolver] [Ref: MM-{corr_id}] Format fallback resolved candidate #{cand_idx} '{cleaned_query[:40]}' in {dur:.2f}s -> '{track.title}'"
                                    )
                                    return track
                                if track:
                                    verification_failed = True
                                    last_failure_reason = "Original recording could not be verified from title and source metadata"
                        except Exception as fb_err:
                            last_failure_reason = _format_error(fb_err)
                            logger.info(
                                "[Resolver] [Ref: MM-%s] provider=youtube operation=stream_extract_format_fallback "
                                "candidate=%d client_profile=%s exception_type=%s",
                                corr_id,
                                cand_idx,
                                ",".join(fallback_clients) if fallback_clients else "yt-dlp default",
                                type(fb_err).__name__,
                            )

            if youtube_rate_limited or youtube_access_blocked or "timed out" in t1_msg.lower() or "timeout" in t1_msg.lower():
                youtube_timed_out = "timed out" in t1_msg.lower() or "timeout" in t1_msg.lower()
                break

            # Tier 2 gets the same bounded retry window as the primary profile.
            try:
                tier2_opts = _build_ytdl_options(["web", "mweb", "android"], use_cookies=False)
                tier2_ydl = yt_dlp.YoutubeDL(tier2_opts)
                data = await _run_ytdlp(
                    functools.partial(tier2_ydl.extract_info, target_url, download=False),
                    timeout=20.0,
                    operation="stream_extract_tier2",
                    correlation_id=corr_id,
                    retry_count=cand_idx,
                )
                if data:
                    track = cls._parse_entry(data, requester_id, requester_name)
                    if (
                        track
                        and track.stream_url
                        and _entry_matches_selected_video(data, target_url, "stream_extract_tier2")
                        and _entry_matches_original_policy(data)
                    ):
                        track = _apply_metadata_enhancements(track)
                        dur = time.time() - start_t
                        logger.info(
                            f"[Resolver] [Ref: MM-{corr_id}] Public Tier 2 resolved candidate #{cand_idx} '{cleaned_query[:40]}' in {dur:.2f}s -> '{track.title}'"
                        )
                        return track
                    if track:
                        verification_failed = True
                        last_failure_reason = "Original recording could not be verified from title and source metadata"
            except Exception as t2_err:
                t2_msg = _format_error(t2_err)
                record_youtube_failure(t2_msg)
                last_failure_reason = t2_msg
                if "429" in t2_msg or "too many requests" in t2_msg.lower():
                    youtube_rate_limited = True
                    last_failure_reason = "YouTube is rate-limiting this server (HTTP 429)."
                logger.warning(
                    "[Resolver] [Ref: MM-%s] provider=youtube operation=stream_extract_tier2 "
                    "candidate=%d exception_type=%s",
                    corr_id,
                    cand_idx,
                    type(t2_err).__name__,
                )
                if _is_youtube_access_challenge(t2_msg):
                    youtube_access_blocked = True
                    last_failure_reason = "YouTube requires an accepted authenticated session or is challenging this server; public extraction was stopped."
                    logger.warning(
                        "[Resolver] [Ref: MM-%s] provider=youtube operation=stream_extract_tier2 "
                        "outcome=stopped_access_challenge", corr_id,
                    )
                    break
                if youtube_rate_limited:
                    break
                if "timed out" in t2_msg.lower():
                    break

        # Stage 4: Optional Cookie Fallback (Only if public extraction failed AND verified cookies exist).
        # Use cookies for ordinary extraction failures, but never amplify an explicit HTTP 429.
        if (
            candidate_urls
            and get_active_cookie_file()
            and not youtube_rate_limited
            and not youtube_access_blocked
            and not youtube_timed_out
        ):
            failed_stage = "cookie_fallback"
            top_target = candidate_urls[0]
            logger.info(
                "[Resolver] [Ref: MM-%s] provider=youtube operation=stream_extract_cookie_fallback outcome=started",
                corr_id,
            )
            # android_vr does not support cookie authentication in yt-dlp.
            # Start the authenticated fallback with a cookie-compatible web client,
            # then retain yt-dlp's default-client fallback as the final attempt.
            for cookie_clients, cookie_format in (
                (["web"], "bestaudio/best"),
                (None, "bestaudio/best"),
            ):
                try:
                    tier3_opts = _build_ytdl_options(cookie_clients, use_cookies=True)
                    tier3_opts["format"] = cookie_format
                    tier3_ydl = yt_dlp.YoutubeDL(tier3_opts)
                    data = await _run_ytdlp(
                        functools.partial(tier3_ydl.extract_info, top_target, download=False),
                        timeout=20.0,
                        operation="stream_extract_cookie_fallback",
                        correlation_id=corr_id,
                        retry_count=1,
                    )
                    if data:
                        track = cls._parse_entry(data, requester_id, requester_name)
                        if (
                            track
                            and track.stream_url
                            and _entry_matches_selected_video(
                                data,
                                top_target,
                                "stream_extract_cookie_fallback",
                            )
                            and _entry_matches_original_policy(data)
                        ):
                            track = _apply_metadata_enhancements(track)
                            dur = time.time() - start_t
                            logger.info(
                                f"[Resolver] [Ref: MM-{corr_id}] Cookie fallback resolved '{cleaned_query[:40]}' "
                                f"with {','.join(cookie_clients) if cookie_clients else 'yt-dlp default'} "
                                f"in {dur:.2f}s -> '{track.title}'"
                            )
                            return track
                        if track:
                            verification_failed = True
                            last_failure_reason = "Original recording could not be verified from title and source metadata"
                except Exception as t3_err:
                    t3_msg = _format_error(t3_err)
                    record_youtube_failure(t3_msg)
                    last_failure_reason = t3_msg
                    if "429" in t3_msg or "too many requests" in t3_msg.lower():
                        youtube_rate_limited = True
                        last_failure_reason = "YouTube is rate-limiting this server (HTTP 429)."
                    logger.warning(
                        "[Resolver] [Ref: MM-%s] provider=youtube operation=stream_extract_cookie_fallback "
                        "client_profile=%s exception_type=%s",
                        corr_id,
                        ",".join(cookie_clients) if cookie_clients else "yt-dlp default",
                        type(t3_err).__name__,
                    )
                    # Stop immediately on rate limits or explicit access challenges.
                    if _is_youtube_access_challenge(t3_msg):
                        youtube_access_blocked = True
                        last_failure_reason = "YouTube requires an accepted authenticated session or is challenging this server; authenticated extraction was stopped."
                        logger.warning(
                            "[Resolver] [Ref: MM-%s] provider=youtube operation=stream_extract_cookie_fallback "
                            "outcome=stopped_access_challenge", corr_id,
                        )
                        break
                    if youtube_rate_limited:
                        break
                    # A transient timeout on the web client should not suppress the
                    # final yt-dlp default-client attempt. Keep this to one bounded
                    # attempt per profile; _run_ytdlp enforces the per-attempt timeout.
                    if "timed out" in t3_msg.lower():
                        continue

        dur = time.time() - start_t
        # Accurately categorize and classify the error
        lower_failure_reason = last_failure_reason.lower()
        if verification_failed:
            cat = "NO_ORIGINAL_MATCH"
            reason = (
                f"No original recording could be verified for '{cleaned_query[:50]}'. "
                "Try a result from the artist's or label's official channel."
            )
        elif "video is unavailable" in lower_failure_reason or "private video" in lower_failure_reason or "has been removed" in lower_failure_reason:
            cat = "VIDEO_UNAVAILABLE"
            reason = f"YouTube reports that the requested video is unavailable for '{cleaned_query[:50]}'. Try another public link."
        elif youtube_rate_limited or "429" in lower_failure_reason or "too many requests" in lower_failure_reason:
            cat = "YOUTUBE_RATE_LIMITED"
            reason = "YouTube is temporarily limiting requests from this server. Wait before retrying, or try the song title instead of a video link."
        elif "TimeoutError" in last_failure_reason or "timed out" in lower_failure_reason:
            cat = "TIMEOUT"
            reason = f"Network or resolution timed out while contacting YouTube for '{cleaned_query[:50]}'."
        elif "access_denied" in lower_failure_reason or "access restriction" in lower_failure_reason or any(k in lower_failure_reason for k in ("sign in", "bot", "captcha", "confirm your age", "forbidden")):
            cat = "ACCESS_RESTRICTION"
            reason = f"YouTube access restriction encountered: {last_failure_reason}"
        elif "No playable" in last_failure_reason or "format is not available" in lower_failure_reason:
            cat = "UNAVAILABLE_FORMAT"
            reason = f"No playable audio streams found for '{cleaned_query[:50]}' ({last_failure_reason})."
        else:
            cat = "RESOLUTION_EXHAUSTED"
            reason = f"Audio resolution exhausted for '{cleaned_query[:50]}' ({last_failure_reason})."

        # Stage 4: Intelligent Multi-Provider Fallback (Audius & Jamendo)
        # When YouTube times out or fails, search secondary permitted providers
        if not is_direct_url and (cat in {"TIMEOUT", "RESOLUTION_EXHAUSTED", "YOUTUBE_RATE_LIMITED", "ACCESS_RESTRICTION", "UNAVAILABLE_FORMAT"} or "timed out" in lower_failure_reason):
            logger.info(
                f"[Resolver] [Ref: MM-{corr_id}] Engaging multi-provider fallback (Audius/Jamendo) for '{cleaned_query[:40]}'"
            )
            # Try Audius
            try:
                from music_bot.services.alternative_providers import AudiusProviderService, JamendoProviderService
                audius_candidates = await AudiusProviderService.search(cleaned_query, limit=3)
                for cand in audius_candidates:
                    if is_alternative_provider_candidate(cand, intent):
                        fb_track = QueuedTrack(
                            title=cand["title"],
                            url=cand["url"],
                            stream_url=cand["stream_url"],
                            duration=cand["duration"],
                            requester_id=requester_id,
                            requester_name=requester_name,
                            artist=cand["artist"],
                            thumbnail=cand.get("thumbnail"),
                        )
                        fb_track = _apply_metadata_enhancements(fb_track)
                        setattr(fb_track, "provider", "audius")
                        logger.info(
                            f"[Resolver] [Ref: MM-{corr_id}] Fallback provider Audius resolved '{cleaned_query[:40]}' -> '{fb_track.title}'"
                        )
                        return fb_track
            except Exception as audius_exc:
                logger.debug(f"[Resolver] [Ref: MM-{corr_id}] Audius fallback error: {audius_exc}")

            # Try Jamendo
            try:
                from music_bot.services.alternative_providers import JamendoProviderService
                jamendo_candidates = await JamendoProviderService.search(cleaned_query, limit=3)
                for cand in jamendo_candidates:
                    if is_alternative_provider_candidate(cand, intent):
                        fb_track = QueuedTrack(
                            title=cand["title"],
                            url=cand["url"],
                            stream_url=cand["stream_url"],
                            duration=cand["duration"],
                            requester_id=requester_id,
                            requester_name=requester_name,
                            artist=cand["artist"],
                            thumbnail=cand.get("thumbnail"),
                        )
                        fb_track = _apply_metadata_enhancements(fb_track)
                        setattr(fb_track, "provider", "jamendo")
                        logger.info(
                            f"[Resolver] [Ref: MM-{corr_id}] Fallback provider Jamendo resolved '{cleaned_query[:40]}' -> '{fb_track.title}'"
                        )
                        return fb_track
            except Exception as jam_exc:
                logger.debug(f"[Resolver] [Ref: MM-{corr_id}] Jamendo fallback error: {jam_exc}")

        cls.last_resolver_error = f"[{cat}] (Ref: MM-{corr_id}) {reason}"
        logger.warning(
            f"[Resolver] [Ref: MM-{corr_id}] All resolution tiers exhausted | query='{cleaned_query[:40]}' | "
            f"stage={failed_stage} | extractor={yt_dlp.version.__version__} | category={cat} | dur={dur:.2f}s | error={last_failure_reason}"
        )
        return None
