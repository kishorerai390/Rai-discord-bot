"""Regression tests for the music player's autoplay controller button."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from voicelink.views.controller import AutoPlay


class FakePlayer:
    def __init__(self):
        self.settings = {"autoplay": False, "controller_msg": True}
        self.is_playing = True
        self._ph = MagicMock()
        self._ph.replace.side_effect = lambda value, *_args, **_kwargs: value

    @property
    def autoplay(self):
        # Match the real Player API: autoplay is read-only and backed by settings.
        return self.settings.get("autoplay", False)

    def is_privileged(self, _user):
        return True


class TestAutoPlayButton(unittest.IsolatedAsyncioTestCase):
    async def test_toggle_updates_setting_and_acknowledges_interaction(self):
        player = FakePlayer()
        button = AutoPlay(player=player, btn_data={})

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock()
        interaction.guild_id = 123
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        interaction.followup.send = AsyncMock()

        with patch(
            "voicelink.views.controller.LangHandler.get_lang",
            new=AsyncMock(return_value="Autoplay enabled"),
        ):
            await button.callback(interaction)

        self.assertTrue(player.settings["autoplay"])
        self.assertTrue(player.autoplay)
        interaction.response.defer.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once_with(view=button.view)
        interaction.followup.send.assert_awaited_once()
