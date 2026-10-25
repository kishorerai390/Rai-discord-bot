"""Regression tests for strict secondary-provider song-title matching."""

import pytest

from music_bot.services.resolver_service import (
    _is_strong_fallback_title_match,
    analyze_query_intent,
)


@pytest.mark.parametrize(
    ("query", "candidate_title", "expected"),
    [
        ("kalyani", "Kalyan", False),
        ("kalyani", "Kalyani", True),
        ("KALYANI", "Kalyani (Official Audio)", True),
        ("kalyani", "Kalyani 10th Anniversary Special", True),
        ("shape of you", "Shape of You", True),
        ("shape of you", "Shape of You Remix", True),
        ("shape of you", "Shape of You - Deluxe Edition", True),
        ("acoustic breeze", "Acoustic Breeze - Official Release", True),
        ("despacito", "I write despacito not tragedies", False),
        ("despacito", "Despacito - Official Release", True),
    ],
)
def test_fallback_title_guard(query, candidate_title, expected):
    candidate = {"title": candidate_title}
    assert _is_strong_fallback_title_match(
        candidate, analyze_query_intent(query)
    ) is expected
