"""Regression tests for explicit voice-channel selection in connect_channel."""

from types import SimpleNamespace

from voicelink.player import _resolve_requested_voice_channel


def test_explicit_channel_takes_priority_for_slash_command():
    explicit_channel = object()
    interaction = SimpleNamespace(user=SimpleNamespace(voice=None))

    assert _resolve_requested_voice_channel(interaction, explicit_channel) is explicit_channel


def test_prefix_command_uses_author_voice_channel_when_no_channel_given():
    voice_channel = object()
    ctx = SimpleNamespace(author=SimpleNamespace(voice=SimpleNamespace(channel=voice_channel)))

    assert _resolve_requested_voice_channel(ctx) is voice_channel


def test_slash_command_uses_user_voice_channel_when_no_channel_given():
    voice_channel = object()
    interaction = SimpleNamespace(user=SimpleNamespace(voice=SimpleNamespace(channel=voice_channel)))

    assert _resolve_requested_voice_channel(interaction) is voice_channel


def test_missing_voice_state_returns_none_instead_of_attribute_error():
    interaction = SimpleNamespace(user=SimpleNamespace(voice=None))

    assert _resolve_requested_voice_channel(interaction) is None
