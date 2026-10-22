"""Regression tests for YouTube resolver access-challenge classification."""

import pytest

from music_bot.services.resolver_service import _is_youtube_access_challenge


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
