import pytest
from unittest.mock import AsyncMock, MagicMock
import datetime
from utils.transcript_html import generate_html_transcript, _format_markdown

def test_markdown_formatting():
    raw = "**Bold Text** and *Italic Text* and `code sample`"
    formatted = _format_markdown(raw)
    assert "<strong>Bold Text</strong>" in formatted
    assert "<em>Italic Text</em>" in formatted
    assert "code sample" in formatted

@pytest.mark.asyncio
async def test_generate_html_transcript():
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

    html = await generate_html_transcript(channel, closer=msg2.author)
    assert "<!DOCTYPE html>" in html
    assert "#ticket-test" in html
    assert "Rai Fam" in html
    assert "Hello, I need help with my roles!" in html
    assert "Sure thing! Which squad role do you want?" in html
    assert "StaffBob" in html
    assert '<span class="bot-tag">BOT</span>' in html
