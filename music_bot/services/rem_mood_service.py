"""Playback-driven personality state for Rem / MusicMaid.

This is a lightweight per-guild state machine. It never changes playback,
voice state, bot presence, or avatar; callers may use the returned transition
for UI/announcements without coupling mood logic to the audio pipeline.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class RemMoodService:
    """Derive Rem's playful mood from real playback events."""

    @staticmethod
    def _state(session: Any) -> Dict[str, Any]:
        if not hasattr(session, "_rem_mood"):
            session._rem_mood = "balanced"
        if not hasattr(session, "_rem_completed_count"):
            session._rem_completed_count = 0
        if not hasattr(session, "_rem_skip_counts"):
            session._rem_skip_counts = {}
        return {
            "mood": session._rem_mood,
            "completed_count": session._rem_completed_count,
        }

    @classmethod
    def _set(cls, session: Any, mood: str, reason: str) -> Dict[str, Any]:
        before = cls._state(session)
        previous = before["mood"]
        session._rem_mood = mood
        return {
            "previous": previous,
            "mood": mood,
            "changed": previous != mood,
            "reason": reason,
            "completed_count": session._rem_completed_count,
        }

    @classmethod
    def on_track_started(cls, session: Any) -> Dict[str, Any]:
        """A real track start moves Rem out of idle/lonely mode."""
        cls._state(session)
        return cls._set(session, "happy", "track_started")

    @classmethod
    def on_track_completed(cls, session: Any) -> Dict[str, Any]:
        """Count natural completions; every 100th completion triggers hyper mode."""
        cls._state(session)
        session._rem_completed_count += 1
        if session._rem_completed_count and session._rem_completed_count % 100 == 0:
            return cls._set(session, "hyper", "100_tracks_completed")
        return cls._set(session, "happy", "track_completed")

    @classmethod
    def on_track_skipped(cls, session: Any, track: Optional[Any]) -> Dict[str, Any]:
        """Become annoyed only after the same track is skipped three times."""
        cls._state(session)
        key = str(getattr(track, "url", "") or getattr(track, "title", "")).strip().lower()
        if not key:
            return cls._set(session, session._rem_mood, "skip_without_track")
        counts = session._rem_skip_counts
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= 3:
            return cls._set(session, "annoyed", "same_track_skipped_three_times")
        return cls._set(session, session._rem_mood, "track_skipped")

    @classmethod
    def on_queue_empty(cls, session: Any) -> Dict[str, Any]:
        """An empty manual queue is lonely only when no autoplay/radio will continue."""
        cls._state(session)
        return cls._set(session, "lonely", "queue_empty")

    @classmethod
    def get_status(cls, session: Any) -> Dict[str, Any]:
        """Read current mood without mutating playback state."""
        return cls._state(session)
