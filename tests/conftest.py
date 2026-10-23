"""Shared pytest fixtures for deterministic, isolated MusicMaid tests."""
from __future__ import annotations

import pytest

from music_bot.services import youtube_health_monitor


@pytest.fixture(autouse=True)
def reset_youtube_health_cooldown_between_tests():
    """Do not let one test's simulated upstream failure poison unrelated tests.

    Production cooldown behavior remains unchanged; the reset is test-only and
    happens around each individual test.
    """
    with youtube_health_monitor._LOCK:
        youtube_health_monitor._COOLDOWN_UNTIL = 0.0
        youtube_health_monitor._LAST_FAILURE = "none"
        youtube_health_monitor._LAST_FAILURE_AT = 0.0
        youtube_health_monitor._LAST_STATUS_LOGGED = None
    yield
    with youtube_health_monitor._LOCK:
        youtube_health_monitor._COOLDOWN_UNTIL = 0.0
        youtube_health_monitor._LAST_FAILURE = "none"
        youtube_health_monitor._LAST_FAILURE_AT = 0.0
        youtube_health_monitor._LAST_STATUS_LOGGED = None
