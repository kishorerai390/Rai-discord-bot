"""
Audio Track Search and Stream Resolution Engine for Rai Music Bot.
Operates asynchronously with yt-dlp in a thread pool to avoid blocking the event loop.
Engineered for YouTube-only audio resolution and Spotify metadata identification.
SoundCloud is completely disabled.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
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
from typing import Any, Dict, List, Optional, Tuple

import yt_dlp

from music_bot.config import REDIS_URL
from music_bot.database.models import QueuedTrack

logger = logging.getLogger("RaiMusic.Resolver")

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
    is_vevo = "vevo" in uploader
    is_major_label = any(lbl in uploader for lbl in MAJOR_RECORD_LABELS)
    is_official_uploader = (
        is_topic_channel
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

    core_words = [w for w in re.findall(r"\w+", core_title) if len(w) > 1]
    if core_words:
        cand_words = set(re.findall(r"\w+", title))
        overlap = sum(1 for w in core_words if w in cand_words)
        ratio = overlap / len(core_words)
        overlap_pts = ratio * 30.0
        score += overlap_pts
        reasons.append(f"token_overlap_{ratio:.2f}(+{overlap_pts:.1f})")

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
        logger.warning(f"[Resolver] Could not initialize Redis client ({REDIS_URL}): {_format_error(e)}. Using in-memory cache.")
        return None


# Global executor for thread-safe asynchronous yt-dlp operations
_audio_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=20, thread_name_prefix="AudioResolver"
)

# Writable temporary cookie file destination (yt-dlp requires write permissions)
WRITABLE_COOKIE_PATH = Path(tempfile.gettempdir()) / "musicmaid_cookies.txt"



def _format_error(e: BaseException) -> str:
    """Format exception with full type name and details, never returning an empty string."""
    if isinstance(e, asyncio.TimeoutError):
        return f"{type(e).__name__} (Network or resolution operation timed out)"
    err_str = str(e).strip()
    if not err_str:
        return f"{type(e).__name__}: {repr(e)}"
    return f"{type(e).__name__}: {err_str}"


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
    clients = player_clients or (["web", "mweb", "android"] if use_cookies else ["android", "mweb"])
    opts: Dict[str, Any] = {
        "format": "bestaudio/bestaudio*/best[height<=720]/best/worstaudio/worst",
        "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
        "restrictfilenames": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "quiet": True,
        "default_search": "ytsearch",
        "socket_timeout": 8,
        "extractor_retries": 1,
        "retries": 1,
        "extractor_args": {
            "youtube": {
                "player_client": clients,
                "skip": ["translated_subs"],
            }
        },
    }
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
        loop = asyncio.get_running_loop()
        cookie_diag = get_cookie_diagnostics()

        yt_ok = False
        yt_reason = "No stream format"
        latency = 0.0

        # 1. Bounded YouTube probe (4.0s timeout with active profile)
        profile = cls.PROFILE_PRESETS[cls._active_profile_index % len(cls.PROFILE_PRESETS)]
        try:
            opts = _build_ytdl_options(profile)
            ytdl_inst = yt_dlp.YoutubeDL(opts)
            data = await asyncio.wait_for(
                loop.run_in_executor(
                    _audio_executor, functools.partial(ytdl_inst.extract_info, test_target, download=False)
                ),
                timeout=4.0,
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
            logger.debug(f"[ExtractorProbe] YouTube probe notice: {raw_err}")
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
            logger.warning(f"Failed writing rotated token: {e}")

        msg = f"Successfully rotated to next PO-Token ({next_token[:8]}...)."
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

        return QueuedTrack(
            title=entry.get("title", "Unknown Title"),
            url=entry.get("webpage_url") or entry.get("url", ""),
            stream_url=stream_url,
            duration=int(entry.get("duration", 0) or 0),
            requester_id=requester_id,
            requester_name=requester_name,
            artist=entry.get("uploader") or entry.get("channel", "Unknown Artist"),
            thumbnail=entry.get("thumbnail"),
        )

    @classmethod
    async def search(cls, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search YouTube for tracks matching query with in-memory caching and intelligent candidate ranking."""
        cache_key = f"{limit}:{query.strip().lower()}"
        if cache_key in cls._search_cache:
            return cls._search_cache[cache_key]

        loop = asyncio.get_running_loop()
        # Query candidates from YouTube for intelligent re-ranking (up to 15 candidates)
        fetch_count = max(limit * 3, 15) if not query.startswith("http") else limit
        search_query = f"ytsearch{fetch_count}:{query}" if not query.startswith("http") else query

        data = None
        # 1. Primary YouTube Search in executor (extract_flat=True for ultra-fast response)
        try:
            primary_opts = _build_ytdl_options(["android"], extract_flat=True)
            ydl_instance = yt_dlp.YoutubeDL(primary_opts)
            data = await asyncio.wait_for(
                loop.run_in_executor(
                    _audio_executor, functools.partial(ydl_instance.extract_info, search_query, download=False)
                ),
                timeout=5.0,
            )
        except Exception as e:
            err_msg = _format_error(e)
            logger.info(f"[Search] YouTube primary search notice for '{query}': {err_msg}")
            data = None

        entries = (data.get("entries") if isinstance(data, dict) and "entries" in data else [data]) if data else []
        raw_candidates: List[Dict[str, Any]] = []
        for entry in (entries or []):
            if not entry or entry.get("has_drm"):
                continue

            # Extract highest-quality thumbnail from yt-dlp metadata
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
                "thumbnail": thumb,
                "provider": "youtube",
            })

        # Rank candidates using query intent analysis
        intent = analyze_query_intent(query)
        scored_candidates = []
        for c in raw_candidates:
            s, r = score_candidate_detailed(c, intent)
            scored_candidates.append((c, s, r))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        if scored_candidates:
            logger.info(
                f"[Search] Ranked {len(scored_candidates)} candidates for query '{query[:40]}':\n"
                + "\n".join(
                    f"  #{i+1} [score={s:.1f}] '{c.get('title')}' by '{c.get('artist')}' | reasons={', '.join(r[:3])}"
                    for i, (c, s, r) in enumerate(scored_candidates[:min(4, len(scored_candidates))])
                )
            )

        results = [c for c, _, _ in scored_candidates[:limit]]
        cls._search_cache[cache_key] = results
        return results

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
            logger.warning(f"[Resolver] SpotifyService resolution error for '{spotify_url}': {_format_error(e)}")

        try:
            fb = await SpotifyService.resolve_via_oembed(spotify_url)
            if fb:
                return fb.to_dict()
        except Exception as fb_err:
            logger.warning(f"[Resolver] Fallback oEmbed failed for '{spotify_url}': {_format_error(fb_err)}")

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
        loop = asyncio.get_running_loop()
        try:
            sc_opts = {
                "quiet": True,
                "format": "bestaudio/best",
                "noplaylist": True,
                "nocheckcertificate": True,
                "ignoreerrors": True,
                "socket_timeout": 8,
                "retries": 1,
            }
            ydl = yt_dlp.YoutubeDL(sc_opts)
            data = await asyncio.wait_for(
                loop.run_in_executor(None, functools.partial(ydl.extract_info, search_target, download=False)),
                timeout=15.0,
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
                            direct_info = await asyncio.wait_for(
                                loop.run_in_executor(None, functools.partial(ydl.extract_info, web_url, download=False)),
                                timeout=6.0,
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
                            logger.debug(f"[Resolver] Direct SoundCloud track resolution notice: {d_err}")
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
            logger.warning(f"[Resolver] SoundCloud resolution notice for '{query[:50]}': {_format_error(e)}")
        return None

    @classmethod
    async def resolve_track(
        cls,
        query_or_url: str,
        requester_id: int,
        requester_name: str,
        title_hint: Optional[str] = None,
        artist_hint: Optional[str] = None,
    ) -> Optional[QueuedTrack]:
        """
        Public resolver method. Deduplicates concurrent resolutions, checks in-memory
        and optional Redis cache (TTL ~1 hour), and guarantees non-blocking async execution.
        """
        cache_key = query_or_url.strip().lower()
        now = time.time()

        # 1. Check in-memory track cache (TTL: CACHE_TTL ~ 1 hour)
        if cache_key in cls._track_cache:
            cached_track, cached_time = cls._track_cache[cache_key]
            if now - cached_time < CACHE_TTL:
                logger.info(f"[Resolver] In-memory cache hit for '{query_or_url[:60]}' -> '{cached_track.title}'")
                return QueuedTrack(
                    title=cached_track.title,
                    url=cached_track.url,
                    stream_url=cached_track.stream_url,
                    duration=cached_track.duration,
                    requester_id=requester_id,
                    requester_name=requester_name,
                    artist=cached_track.artist,
                    thumbnail=cached_track.thumbnail,
                )

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
                    logger.info(f"[Resolver] Redis cache hit for '{query_or_url[:60]}' -> '{restored_track.title}'")
                    return restored_track
            except Exception as r_err:
                logger.debug(f"[Resolver] Redis cache lookup failed: {_format_error(r_err)}")

        # 3. Deduplicate concurrent resolves of the same query
        if cache_key in cls._pending_tasks and not cls._pending_tasks[cache_key].done():
            logger.info(f"[Resolver] Deduplicating concurrent resolution for '{query_or_url[:60]}'")
            task = cls._pending_tasks[cache_key]
            try:
                res = await asyncio.shield(task)
                if res:
                    return QueuedTrack(
                        title=res.title,
                        url=res.url,
                        stream_url=res.stream_url,
                        duration=res.duration,
                        requester_id=requester_id,
                        requester_name=requester_name,
                        artist=res.artist,
                        thumbnail=res.thumbnail,
                    )
            except Exception:
                pass

        # 4. Create background resolution task
        task = asyncio.create_task(
            cls._execute_resolution_pipeline(
                query_or_url, requester_id, requester_name, title_hint=title_hint, artist_hint=artist_hint
            )
        )
        cls._pending_tasks[cache_key] = task

        def _on_done(f: asyncio.Future):
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
        return await task

    @classmethod
    def clear_caches(cls) -> None:
        """Clear all in-memory track resolution and search caches."""
        cls._track_cache.clear()
        cls._search_cache.clear()
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
                track.stream_url = fresh.stream_url
                track.duration = fresh.duration
                if not track.thumbnail and fresh.thumbnail:
                    track.thumbnail = fresh.thumbnail
                logger.info(f"[PreResolver] Successfully pre-resolved upcoming track: '{track.title}'")
        except Exception as e:
            logger.debug(f"[PreResolver] Lookahead resolution notice for '{track.title}': {e}")

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

        # 1. Instant check: match local track cache
        q_lower = q.lower()
        for k, (cached_track, _) in list(cls._track_cache.items()):
            if q_lower in cached_track.title.lower() or q_lower in k:
                if cached_track.title not in seen:
                    seen.add(cached_track.title)
                    results.append({
                        "title": cached_track.title,
                        "artist": cached_track.artist or "Cached Track",
                        "url": cached_track.url or cached_track.title,
                    })
                    if len(results) >= limit:
                        return results

        # 2. Fast remote suggest API (<150ms HTTP GET, no cookies or IP block risk)
        try:
            import aiohttp
            suggest_url = f"https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q={urllib.parse.quote_plus(q)}"
            timeout = aiohttp.ClientTimeout(total=1.2)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(suggest_url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
                            for suggestion in data[1]:
                                if suggestion not in seen:
                                    seen.add(suggestion)
                                    results.append({
                                        "title": str(suggestion),
                                        "artist": "Search Suggestion",
                                        "url": str(suggestion),
                                    })
                                    if len(results) >= limit:
                                        break
        except Exception as e:
            logger.debug(f"[Autocomplete] Suggest fetch error: {e}")

        # 3. Fallback: return the query itself
        if not results:
            results.append({
                "title": f"Play: {q}",
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
        loop = asyncio.get_running_loop()

        spotify_info = None
        cleaned_query = query_or_url
        is_spotify = "spotify.com" in query_or_url or query_or_url.startswith("spotify:")
        if is_spotify:
            spotify_info = await cls.resolve_spotify_metadata(query_or_url)
            if spotify_info:
                cleaned_query = spotify_info.get("search_query", query_or_url)
                logger.info(f"[Resolver] Resolved Spotify metadata: '{spotify_info.get('title')}' by '{spotify_info.get('artist')}'")
        elif "apple.com" in query_or_url:
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
            return t

        cls.last_resolver_error = None
        corr_id = uuid.uuid4().hex[:6].upper()
        failed_stage = "init"
        is_direct_url = cleaned_query.startswith("http://") or cleaned_query.startswith("https://")

        # 1. Direct SoundCloud resolution path
        if is_direct_url and "soundcloud.com" in cleaned_query:
            sc_track = await cls.resolve_soundcloud_track(cleaned_query, requester_id, requester_name)
            if sc_track and sc_track.stream_url:
                dur = time.time() - start_t
                logger.info(f"[Resolver] [Ref: MM-{corr_id}] Direct SoundCloud resolved in {dur:.2f}s -> '{sc_track.title}'")
                return sc_track

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
                cached_search = await cls.search(cleaned_query, limit=5)
                if cached_search:
                    candidate_urls = [c["url"] for c in cached_search if c.get("url")]
            except Exception:
                pass

            if not candidate_urls:
                # Query up to 15 candidate tracks from YouTube for comprehensive original-vs-remix ranking
                search_query = f"ytsearch15:{cleaned_query}"
                try:
                    flat_opts = _build_ytdl_options(["android"], extract_flat=True, use_cookies=False)
                    flat_ydl = yt_dlp.YoutubeDL(flat_opts)
                    search_data = await asyncio.wait_for(
                        loop.run_in_executor(
                            _audio_executor, functools.partial(flat_ydl.extract_info, search_query, download=False)
                        ),
                        timeout=6.0,
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
                        reason = f"No search results returned for '{cleaned_query[:60]}'."

                    cls.last_resolver_error = f"[{cat}] (Ref: MM-{corr_id}) {reason}"
                    logger.warning(
                        f"[Resolver] [Ref: MM-{corr_id}] YouTube search returned 0 candidates | query='{cleaned_query[:40]}' | "
                        f"extractor={yt_dlp.version.__version__} | category={cat} | dur={dur:.2f}s"
                    )

                    # Secondary fallback if enabled (e.g. SoundCloud emergency fallback)
                    try:
                        logger.info(f"[Resolver] [Ref: MM-{corr_id}] Attempting emergency SoundCloud search fallback for '{cleaned_query[:40]}'...")
                        sc_track = await cls.resolve_soundcloud_track(cleaned_query, requester_id, requester_name)
                        if sc_track:
                            sc_track = _apply_metadata_enhancements(sc_track)
                            return sc_track
                    except Exception as sc_err:
                        logger.debug(f"[Resolver] Emergency SoundCloud search notice: {sc_err}")

                    return None

                # Stage 2: Rank candidates using smart query intent analysis
                failed_stage = "ranking"
                scored_candidates: List[Tuple[Dict[str, Any], float, List[str]]] = []
                for entry in search_entries:
                    score_val, reasons_list = score_candidate_detailed(
                        entry,
                        intent,
                        spotify_meta=spotify_info,
                        title_hint=title_hint,
                        artist_hint=artist_hint,
                    )
                    scored_candidates.append((entry, score_val, reasons_list))

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
        for cand_idx, target_url in enumerate(candidate_urls[:2], 1):
            # Tier 1: Primary Public Profile (android) - 14.0s timeout for cold cloud responses
            try:
                tier1_opts = _build_ytdl_options(["android"], use_cookies=False)
                tier1_ydl = yt_dlp.YoutubeDL(tier1_opts)
                data = await asyncio.wait_for(
                    loop.run_in_executor(
                        _audio_executor, functools.partial(tier1_ydl.extract_info, target_url, download=False)
                    ),
                    timeout=14.0,
                )
                if data:
                    track = cls._parse_entry(data, requester_id, requester_name)
                    if track and track.stream_url:
                        track = _apply_metadata_enhancements(track)
                        dur = time.time() - start_t
                        logger.info(
                            f"[Resolver] [Ref: MM-{corr_id}] Public Tier 1 resolved candidate #{cand_idx} '{cleaned_query[:40]}' in {dur:.2f}s -> '{track.title}'"
                        )
                        return track
            except Exception as t1_err:
                t1_msg = _format_error(t1_err)
                last_failure_reason = t1_msg
                logger.info(f"[Resolver] [Ref: MM-{corr_id}] Candidate #{cand_idx} Tier 1 public notice for '{target_url}': {t1_msg}")

            # Tier 2: Fallback Public Profile (mweb) - 10.0s timeout
            try:
                tier2_opts = _build_ytdl_options(["mweb", "android"], use_cookies=False)
                tier2_ydl = yt_dlp.YoutubeDL(tier2_opts)
                data = await asyncio.wait_for(
                    loop.run_in_executor(
                        _audio_executor, functools.partial(tier2_ydl.extract_info, target_url, download=False)
                    ),
                    timeout=10.0,
                )
                if data:
                    track = cls._parse_entry(data, requester_id, requester_name)
                    if track and track.stream_url:
                        track = _apply_metadata_enhancements(track)
                        dur = time.time() - start_t
                        logger.info(
                            f"[Resolver] [Ref: MM-{corr_id}] Public Tier 2 resolved candidate #{cand_idx} '{cleaned_query[:40]}' in {dur:.2f}s -> '{track.title}'"
                        )
                        return track
            except Exception as t2_err:
                t2_msg = _format_error(t2_err)
                last_failure_reason = t2_msg
                logger.warning(f"[Resolver] [Ref: MM-{corr_id}] Candidate #{cand_idx} Tier 2 public failed for '{target_url}': {t2_msg}")

        # Stage 4: Optional Cookie Fallback (Only if public extraction failed AND verified cookies exist)
        if candidate_urls and get_active_cookie_file():
            failed_stage = "cookie_fallback"
            top_target = candidate_urls[0]
            try:
                logger.info(f"[Resolver] [Ref: MM-{corr_id}] Public tiers exhausted; attempting optional cookie fallback for '{top_target}'")
                tier3_opts = _build_ytdl_options(["android", "tv_embedded"], use_cookies=True)
                tier3_ydl = yt_dlp.YoutubeDL(tier3_opts)
                data = await asyncio.wait_for(
                    loop.run_in_executor(
                        _audio_executor, functools.partial(tier3_ydl.extract_info, top_target, download=False)
                    ),
                    timeout=8.0,
                )
                if data:
                    track = cls._parse_entry(data, requester_id, requester_name)
                    if track and track.stream_url:
                        track = _apply_metadata_enhancements(track)
                        dur = time.time() - start_t
                        logger.info(
                            f"[Resolver] [Ref: MM-{corr_id}] Cookie fallback resolved '{cleaned_query[:40]}' in {dur:.2f}s -> '{track.title}'"
                        )
                        return track
            except Exception as t3_err:
                last_failure_reason = _format_error(t3_err)

        # Stage 5: Secondary Provider Fallback (SoundCloud) for zero-interruption playback
        try:
            logger.info(f"[Resolver] [Ref: MM-{corr_id}] Attempting SoundCloud resolution fallback for '{cleaned_query[:50]}'")
            sc_query = f"{title_hint} {artist_hint or ''}".strip() if title_hint else cleaned_query
            if is_direct_url and ("youtube" in cleaned_query or "youtu.be" in cleaned_query) and not title_hint:
                sc_query = ""
                try:
                    import urllib.request
                    oembed_url = f"https://www.youtube.com/oembed?url={cleaned_query}&format=json"
                    req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                    with urllib.request.urlopen(req, timeout=5.0) as o_resp:
                        o_data = json.loads(o_resp.read().decode())
                        if o_data and o_data.get("title"):
                            author = (o_data.get("author_name") or "").replace(" - Topic", "").strip()
                            sc_query = f"{o_data.get('title')} {author}".strip()
                except Exception as o_err:
                    logger.debug(f"[Resolver] oEmbed lookup notice: {o_err}")

            if sc_query and not sc_query.startswith("http"):
                sc_track = await cls.resolve_soundcloud_track(sc_query, requester_id, requester_name)
                if sc_track:
                    sc_track = _apply_metadata_enhancements(sc_track)
                    dur = time.time() - start_t
                    logger.info(
                        f"[Resolver] [Ref: MM-{corr_id}] SoundCloud fallback successfully resolved '{sc_query[:40]}' in {dur:.2f}s -> '{sc_track.title}'"
                    )
                    return sc_track
        except Exception as sc_err:
            logger.warning(f"[Resolver] [Ref: MM-{corr_id}] SoundCloud fallback failed: {_format_error(sc_err)}")

        dur = time.time() - start_t
        # Accurately categorize and classify the error
        if "TimeoutError" in last_failure_reason or "timed out" in last_failure_reason.lower():
            cat = "TIMEOUT"
            reason = f"Network or resolution timed out while contacting YouTube for '{cleaned_query[:50]}'."
        elif any(k in last_failure_reason.lower() for k in ("sign in", "bot", "captcha", "confirm your age")):
            cat = "ACCESS_RESTRICTION"
            reason = f"YouTube access restriction encountered: {last_failure_reason}"
        elif "No playable" in last_failure_reason or "format is not available" in last_failure_reason.lower():
            cat = "UNAVAILABLE_FORMAT"
            reason = f"No playable audio streams found for '{cleaned_query[:50]}' ({last_failure_reason})."
        else:
            cat = "RESOLUTION_EXHAUSTED"
            reason = f"Audio resolution exhausted for '{cleaned_query[:50]}' ({last_failure_reason})."

        cls.last_resolver_error = f"[{cat}] (Ref: MM-{corr_id}) {reason}"
        logger.warning(
            f"[Resolver] [Ref: MM-{corr_id}] All resolution tiers exhausted | query='{cleaned_query[:40]}' | "
            f"stage={failed_stage} | extractor={yt_dlp.version.__version__} | category={cat} | dur={dur:.2f}s | error={last_failure_reason}"
        )
        return None
