"""Regression tests for realtime music session change detection."""

from web.realtime import live_session_payload_changed


def test_live_session_track_change_is_broadcast_even_when_session_id_is_stable():
    previous = [{
        "id": "session_music_123",
        "type": "music",
        "title": "Track One",
        "artist": "Artist",
        "started_at": "2026-10-30T10:00:00+00:00",
    }]
    current = [{
        "id": "session_music_123",
        "type": "music",
        "title": "Track Two",
        "artist": "Artist",
        "started_at": "2026-10-30T10:00:04+00:00",
    }]

    assert live_session_payload_changed(previous, current) is True


def test_live_session_sample_timestamp_does_not_create_false_change():
    previous = [{
        "id": "session_music_123",
        "type": "music",
        "title": "Track One",
        "artist": "Artist",
        "started_at": "2026-10-30T10:00:00+00:00",
    }]
    current = [{
        "id": "session_music_123",
        "type": "music",
        "title": "Track One",
        "artist": "Artist",
        "started_at": "2026-10-30T10:00:04+00:00",
    }]

    assert live_session_payload_changed(previous, current) is False


def test_live_session_addition_and_removal_are_detected():
    session = {"id": "session_music_123", "type": "music", "title": "Track One"}

    assert live_session_payload_changed([], [session]) is True
    assert live_session_payload_changed([session], []) is True
