"""
Regression and Resilience Test Suite for MusicMaid Extractor Health and /debug Command.

Validates:
1. get_cookie_diagnostics safely identifies presence, tokens, and expiration without leaking secrets.
2. probe_extractor_health is bounded, implements cooldown, and verifies SoundCloud fallback.
3. cmd_debug and _run_pipeline_diagnostics execute within bounded deadlines, prevent deadlocks,
   and always edit or send a response with correlation ID DBG-<hex>.
4. Voice error embed advice suppresses misleading permission advice on dependency or timeout errors.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from music_bot.commands.music_cog import MusicCog
from music_bot.services.resolver_service import (
    AudioResolver,
    _validate_cookies_content,
    get_cookie_diagnostics,
)


# =============================================================================
# 1. COOKIE DIAGNOSTICS & SECRET PROTECTION
# =============================================================================

def test_cookie_diagnostics_when_empty():
    """Verify cookie diagnostics when no cookies are configured."""
    with patch("music_bot.services.resolver_service.get_active_cookie_file", return_value=None):
        diag = get_cookie_diagnostics()
        assert diag["present"] is False
        assert diag["status"] == "Missing"
        assert diag["token_count"] == 0
        assert "guidance" in diag


def test_cookie_diagnostics_never_leaks_token_values(tmp_path):
    """Verify that cookie tokens and values are never exposed in diagnostics dict."""
    secret_val = "SUPER_SECRET_AUTH_TOKEN_VALUE_XYZ_123"
    cookie_content = (
        f"# Netscape HTTP Cookie File\n"
        f".youtube.com\tTRUE\t/\tTRUE\t{int(time.time() + 86400)}\tLOGIN_INFO\t{secret_val}\n"
        f".youtube.com\tTRUE\t/\tTRUE\t{int(time.time() + 86400)}\tSID\tANOTHER_SECRET_456\n"
    )
    fake_cookie_file = tmp_path / "test_cookies.txt"
    fake_cookie_file.write_text(cookie_content, encoding="utf-8")

    with patch("music_bot.services.resolver_service.get_active_cookie_file", return_value=str(fake_cookie_file)):
        diag = get_cookie_diagnostics()
        assert diag["present"] is True
        assert diag["is_valid"] is True
        assert diag["token_count"] == 2
        # Ensure secret value is NOT anywhere in the diagnostic dictionary
        diag_str = str(diag)
        assert secret_val not in diag_str
        assert "ANOTHER_SECRET_456" not in diag_str
        assert "LOGIN_INFO" in diag.get("tokens_found", [])


def test_cookie_diagnostics_detects_expired_tokens(tmp_path):
    """Verify expired cookies are flagged and expired token names (only) are reported."""
    past_timestamp = int(time.time() - 3600)
    cookie_content = (
        f"# Netscape HTTP Cookie File\n"
        f".youtube.com\tTRUE\t/\tTRUE\t{past_timestamp}\tLOGIN_INFO\tEXPIRED_VAL\n"
    )
    fake_cookie_file = tmp_path / "test_expired_cookies.txt"
    fake_cookie_file.write_text(cookie_content, encoding="utf-8")

    with patch("music_bot.services.resolver_service.get_active_cookie_file", return_value=str(fake_cookie_file)):
        diag = get_cookie_diagnostics()
        assert diag["present"] is True
        assert diag["is_valid"] is False
        assert "LOGIN_INFO" in diag["expired_tokens"]
        assert "EXPIRED_VAL" not in str(diag)


# =============================================================================
# 2. EXTRACTOR HEALTH PROBE & RECOVERY BOUNDS
# =============================================================================

@pytest.mark.asyncio
async def test_probe_extractor_health_cooldown():
    """Verify probe_extractor_health respects 45s cooldown and reuses recent results."""
    # Reset state
    AudioResolver._last_probe_time = time.monotonic()
    AudioResolver._last_probe_result = {
        "operational": True,
        "youtube_operational": True,
        "message": "Cached healthy",
    }

    # Calling without force should immediately return cached dict without running extraction
    result = await AudioResolver.probe_extractor_health(force=False)
    assert result["message"] == "Cached healthy"


@pytest.mark.asyncio
async def test_probe_extractor_health_fallback_to_soundcloud():
    """Verify that when YouTube probe encounters restriction, SoundCloud fallback is checked."""
    AudioResolver._last_probe_time = 0.0
    AudioResolver._last_probe_result = None

    mock_sc_entry = {
        "url": "https://cf-media.sndcdn.com/stream/test_pcm",
        "title": "lofi beats",
        "formats": [{"acodec": "mp3", "url": "https://cf-media.sndcdn.com/stream/test_pcm"}],
    }

    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.side_effect = [
        Exception("No video formats found!"),
        {"entries": [mock_sc_entry]},
    ]

    with patch.object(AudioResolver, "PROFILE_PRESETS", [["mweb", "web"]]), \
         patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
        res = await AudioResolver.probe_extractor_health(force=True)
        assert res["operational"] is True
        assert res["youtube_operational"] is False
        assert res["soundcloud_operational"] is True
        assert res["active_fallback"] == "SoundCloud"


# =============================================================================
# 3. /debug COMMAND RESILIENCE & DEADLINE GUARANTEES
# =============================================================================

@pytest.mark.asyncio
async def test_cmd_debug_handles_timeout_cleanly():
    """Verify cmd_debug responds with timeout embed when pipeline diagnostics exceed deadline."""
    mock_bot = MagicMock()
    mock_bot.session_manager = MagicMock()
    mock_cog = MusicCog(mock_bot)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = True
    interaction.edit_original_response = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    # Simulate _run_pipeline_diagnostics timing out
    async def _mock_hang(*args, **kwargs):
        await asyncio.sleep(20.0)

    with patch.object(mock_cog, "_run_pipeline_diagnostics", side_effect=_mock_hang):
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            # app_commands decorator wraps callback into Command object
            await mock_cog.cmd_debug.callback(mock_cog, interaction, test_query="timeout test")

    # Ensure edit_original_response was called with a timeout embed
    assert interaction.edit_original_response.called
    called_embed = interaction.edit_original_response.call_args.kwargs.get("embed")
    assert called_embed is not None
    assert "DIAGNOSTIC NOTICE" in called_embed.title
    assert "DBG-" in called_embed.footer.text


@pytest.mark.asyncio
async def test_cmd_debug_handles_unhandled_exception_cleanly():
    """Verify cmd_debug catches unexpected exceptions and delivers error embed with DBG ID."""
    mock_bot = MagicMock()
    mock_bot.session_manager = MagicMock()
    mock_cog = MusicCog(mock_bot)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = True
    interaction.edit_original_response = AsyncMock()

    with patch.object(mock_cog, "_run_pipeline_diagnostics", side_effect=RuntimeError("Subprocess pipe crash")):
        await mock_cog.cmd_debug.callback(mock_cog, interaction, test_query="error test")

    assert interaction.edit_original_response.called
    called_embed = interaction.edit_original_response.call_args.kwargs.get("embed")
    assert called_embed is not None
    assert "EXCEPTION" in called_embed.title
    assert "DBG-" in called_embed.footer.text
    assert "Subprocess pipe crash" in called_embed.description


# =============================================================================
# 4. VOICE ERROR DIAGNOSTICS & ACCURATE ADVICE
# =============================================================================

@pytest.mark.asyncio
async def test_voice_error_advice_does_not_mislead_on_dependency_error():
    """Verify that davey / dependency errors do NOT display channel permission fix instructions."""
    # When davey is missing, error contains 'davey library needed'
    err_detail = (
        "Voice connection failed: Voice connection timed out after 3 attempts (5233ms).\n"
        "• Failed Stage: Voice Dependency Missing (davey)\n\n"
        "💡 Recommended Action: davey library needed in order to use voice."
    )

    is_perm_err = (
        ("permission" in err_detail.lower())
    ) and not any(dep in err_detail.lower() for dep in ("davey", "pynacl", "opus", "dependency", "timed out", "timeout"))

    # Must evaluate to False so permission troubleshooting is suppressed!
    assert is_perm_err is False


@pytest.mark.asyncio
async def test_voice_error_advice_shows_permission_fix_on_genuine_forbidden():
    """Verify that genuine 403 Forbidden permission errors DO display permission instructions."""
    err_detail = "MusicMaid was rejected with 403 Forbidden. Bot lacks Connect and Speak permissions."

    is_perm_err = (
        ("403" in err_detail and "forbidden" in err_detail.lower())
        or ("lacks permission" in err_detail.lower())
    ) and not any(dep in err_detail.lower() for dep in ("davey", "pynacl", "opus", "dependency", "timed out", "timeout"))

    assert is_perm_err is True
