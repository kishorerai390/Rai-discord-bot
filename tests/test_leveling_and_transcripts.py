import unittest
from unittest.mock import AsyncMock, MagicMock
import datetime
from utils.transcript_html import generate_html_transcript, _format_markdown

class TestLevelingAndTranscripts(unittest.IsolatedAsyncioTestCase):
    def test_markdown_formatting(self):
        raw = "**Bold Text** and *Italic Text* and `code sample`"
        formatted = _format_markdown(raw)
        self.assertIn("<strong>Bold Text</strong>", formatted)
        self.assertIn("<em>Italic Text</em>", formatted)
        self.assertIn("code sample", formatted)

    async def test_generate_html_transcript(self):
        channel = MagicMock()
        channel.name = "ticket-test"
        channel.guild.name = "Rai Fam"

        # Mock messages
        msg1 = MagicMock()
        msg1.author.display_name = "Alice"
        msg1.author.bot = False
        msg1.author.display_avatar.url = "https://example.com/avatar1.png"
        msg1.created_at = datetime.datetime.now(datetime.timezone.utc)
        msg1.content = "Hello, I need help with my roles!"
        msg1.attachments = []
        msg1.embeds = []

        msg2 = MagicMock()
        msg2.author.display_name = "StaffBob"
        msg2.author.bot = True
        msg2.author.display_avatar.url = "https://example.com/avatar2.png"
        msg2.created_at = datetime.datetime.now(datetime.timezone.utc)
        msg2.content = "Sure thing! Which squad role do you want?"
        msg2.attachments = []
        msg2.embeds = []

        async def mock_history(*args, **kwargs):
            for m in [msg1, msg2]:
                yield m

        channel.history = mock_history

        html = await generate_html_transcript(channel)
        self.assertIn("Alice", html)
        self.assertIn("StaffBob", html)
        self.assertIn("Hello, I need help with my roles!", html)
        self.assertIn("Which squad role do you want?", html)
        self.assertIn("ticket-test", html)
        self.assertIn("The Raivora Luxury Sentinel", html)

if __name__ == "__main__":
    unittest.main()
