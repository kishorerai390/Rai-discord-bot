"""Regression tests for YouTube resolver access-challenge classification."""

import pytest

from music_bot.services.resolver_service import (
    _is_youtube_access_challenge,
    _should_attempt_cookie_fallback,
)


@pytest.mark.parametrize(
    "message",
    [
        "Sign in to confirm you're not a bot",
        "YouTube says: confirm you're not a bot",
        "Please confirm you’re not a bot to continue",
        "CAPTCHA challenge required",
        "consent required",
        "NOT A BOT",
    ],
)
def test_detects_explicit_youtube_access_challenges(message):
    assert _is_youtube_access_challenge(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "",
        None,
        "HTTP Error 403: Forbidden",
        "HTTP Error 429: Too Many Requests",
        "Requested format is not available",
        "Unable to download webpage",
    ],
)
def test_does_not_misclassify_other_resolver_errors(message):
    assert _is_youtube_access_challenge(message) is False



def test_cookie_fallback_is_allowed_after_public_access_challenge():
    # A sign-in/bot challenge should trigger the configured authenticated tier.
    assert _should_attempt_cookie_fallback(
        ["https://www.youtube.com/watch?v=example"],
        "/tmp/verified-cookies.txt",
        youtube_rate_limited=False,
        youtube_access_blocked=True,
        youtube_timed_out=False,
    ) is True


def test_cookie_fallback_stays_disabled_without_verified_cookies_or_after_rate_limit():
    candidate = ["https://www.youtube.com/watch?v=example"]
    assert _should_attempt_cookie_fallback(
        candidate, None, False, True, False
    ) is False
    assert _should_attempt_cookie_fallback(
        candidate, "/tmp/verified-cookies.txt", True, False, False
    ) is False
    assert _should_attempt_cookie_fallback(
        candidate, "/tmp/verified-cookies.txt", False, False, True
    ) is False
