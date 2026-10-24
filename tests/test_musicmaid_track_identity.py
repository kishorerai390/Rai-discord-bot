"""Regression tests for alternative-provider song identity safeguards."""

from types import SimpleNamespace

from music_bot.commands.music_cog import _alternative_track_matches_query


def test_kalyan_is_not_accepted_for_kalyani_request():
    track = SimpleNamespace(title="Kalyan", artist="Multani")
    assert not _alternative_track_matches_query("Kalyani", track)


def test_exact_kalyani_title_is_accepted():
    track = SimpleNamespace(title="Kalyani - Classical Recording", artist="Carnatic Artist")
    assert _alternative_track_matches_query("Kalyani", track)


def test_query_media_words_are_removed_before_identity_check():
    track = SimpleNamespace(title="Kalyani - Official Audio", artist="Carnatic Artist")
    assert _alternative_track_matches_query("Kalyani song", track)


def test_mismatched_long_title_token_is_rejected():
    track = SimpleNamespace(title="Kalyan Official Audio", artist="Unknown")
    assert not _alternative_track_matches_query("Kalyani official audio", track)
