from __future__ import annotations

import time

from music_bot.services import youtube_health_monitor as monitor


def test_missing_cookie_file_is_reported_safely(tmp_path):
    result = monitor.inspect_cookie_file(str(tmp_path / "missing.txt"))
    assert result["status"] == "missing"
    assert result["present"] is False
    assert "cookie" in result["summary"].lower()


def test_cookie_values_are_not_returned(tmp_path):
    cookie_file = tmp_path / "cookies.txt"
    expiry = int(time.time()) + 3600
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        f".youtube.com\tTRUE\t/\tTRUE\t{expiry}\tSAPISID\tSECRET_VALUE\n",
        encoding="utf-8",
    )
    result = monitor.inspect_cookie_file(str(cookie_file))
    assert result["present"] is True
    assert result["readable"] is True
    assert "SECRET_VALUE" not in repr(result)
    assert "present_unverified" == result["status"]


def test_rate_limit_sets_cooldown(monkeypatch):
    monkeypatch.setattr(monitor, "_COOLDOWN_UNTIL", 0.0)
    monkeypatch.setattr(monitor, "_LAST_FAILURE", "none")
    category = monitor.record_failure("HTTP Error 429: Too Many Requests")
    assert category == "rate_limited"
    status = monitor.cooldown_status()
    assert status["cooldown_active"] is True
    assert status["cooldown_remaining_seconds"] > 0


def test_timeout_is_classified():
    assert monitor.record_failure("Network operation timed out") == "timeout"
