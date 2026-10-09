"""
Unit tests for Real-Time Consoles and Interactive Dispatcher.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock
import discord

from utils.realtime_consoles import (
    get_system_vitals,
    build_admin_control_payload,
    build_server_dashboard_payload,
    build_system_health_payload,
    build_antinuke_payload,
    build_lockdown_payload,
    build_security_alerts_payload,
    build_honeypot_payload,
    build_room_control_payload,
    build_suggestions_payload,
    build_support_desk_payload,
    build_hall_of_fame_payload,
    build_music_control_payload,
    build_welcome_payload,
    build_bot_commands_payload,
    RealtimeConsoleDispatcher,
)

class TestRealtimeConsoles(unittest.IsolatedAsyncioTestCase):
    def test_vitals_retrieval(self):
        v = get_system_vitals()
        self.assertIn("mem_mb", v)
        self.assertIn("latency_ms", v)
        self.assertIn("uptime_str", v)
        self.assertIn("now_ts", v)

    def test_all_payload_builders(self):
        builders = [
            build_admin_control_payload,
            build_server_dashboard_payload,
            build_system_health_payload,
            build_antinuke_payload,
            build_lockdown_payload,
            build_security_alerts_payload,
            build_honeypot_payload,
            build_room_control_payload,
            build_suggestions_payload,
            build_support_desk_payload,
            build_hall_of_fame_payload,
            build_music_control_payload,
            build_welcome_payload,
            build_bot_commands_payload,
        ]
        for b in builders:
            payload = b()
            self.assertIn("embeds", payload)
            self.assertIn("components", payload)
            self.assertTrue(len(payload["embeds"]) > 0)
            self.assertTrue(len(payload["components"]) > 0)

    async def test_dispatcher_handles_refresh(self):
        bot = MagicMock()
        bot.latency = 0.02
        interaction = MagicMock(spec=discord.Interaction)
        interaction.data = {"custom_id": "rt_adm:refresh"}
        interaction.response = MagicMock()
        interaction.response.edit_message = AsyncMock()

        handled = await RealtimeConsoleDispatcher.handle_interaction(bot, interaction)
        self.assertTrue(handled)
        interaction.response.edit_message.assert_awaited_once()

    async def test_dispatcher_handles_ping(self):
        bot = MagicMock()
        bot.latency = 0.02
        interaction = MagicMock(spec=discord.Interaction)
        interaction.data = {"custom_id": "rt_adm:ping"}
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        handled = await RealtimeConsoleDispatcher.handle_interaction(bot, interaction)
        self.assertTrue(handled)
        interaction.response.send_message.assert_awaited_once()

    async def test_dispatcher_handles_honeypot(self):
        bot = MagicMock()
        interaction = MagicMock(spec=discord.Interaction)
        interaction.data = {"custom_id": "rt_hp:status"}
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        handled = await RealtimeConsoleDispatcher.handle_interaction(bot, interaction)
        self.assertTrue(handled)
        interaction.response.send_message.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()
