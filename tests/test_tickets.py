import unittest
from unittest.mock import AsyncMock, MagicMock
import datetime
import discord

from cogs.tickets import TicketControlView, TicketPanelView, generate_transcript


class TestTickets(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.name = "RAI FAM"
        self.guild.id = 1457382179981099090

        self.channel = MagicMock(spec=discord.TextChannel)
        self.channel.name = "ticket-user-1234"
        self.channel.guild = self.guild

    async def test_generate_transcript(self):
        msg1 = MagicMock(spec=discord.Message)
        msg1.created_at = datetime.datetime(2026, 9, 30, 10, 0, 0, tzinfo=datetime.timezone.utc)
        msg1.author = MagicMock()
        msg1.author.__str__.return_value = "TestUser#1234"
        msg1.author.id = 111111
        msg1.content = "I need help with roles"
        msg1.attachments = []

        msg2 = MagicMock(spec=discord.Message)
        msg2.created_at = datetime.datetime(2026, 9, 30, 10, 2, 0, tzinfo=datetime.timezone.utc)
        msg2.author = MagicMock()
        msg2.author.__str__.return_value = "Staff#0001"
        msg2.author.id = 999999
        msg2.content = "Here is the screenshot:"
        att = MagicMock()
        att.url = "https://cdn.discordapp.com/attachments/1.png"
        msg2.attachments = [att]

        async def mock_history(limit, oldest_first):
            yield msg1
            yield msg2

        self.channel.history = mock_history

        transcript = await generate_transcript(self.channel)
        self.assertIn("=== TRANSCRIPT FOR #ticket-user-1234 ===", transcript)
        self.assertIn("Guild: RAI FAM (1457382179981099090)", transcript)
        self.assertIn("I need help with roles", transcript)
        self.assertIn("[Attachment: https://cdn.discordapp.com/attachments/1.png]", transcript)

    def test_ticket_views_custom_ids(self):
        panel_view = TicketPanelView()
        create_btn = [c for c in panel_view.children if getattr(c, "custom_id", None) == "sentinel_ticket_create"]
        self.assertEqual(len(create_btn), 1)

        control_view = TicketControlView()
        close_btn = [c for c in control_view.children if getattr(c, "custom_id", None) == "sentinel_ticket_close"]
        self.assertEqual(len(close_btn), 1)


if __name__ == "__main__":
    unittest.main()
