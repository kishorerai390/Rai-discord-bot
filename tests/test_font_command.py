import pytest
from unittest.mock import AsyncMock, MagicMock
from cogs.utility import UtilityCog, FontDropdown, FontSelectView
from utils.font_generator import AVAILABLE_STYLES, transform_text

def test_font_view_initialization():
    view = FontSelectView("Hello World", "small_caps")
    assert len(view.children) >= 2
    dropdowns = [c for c in view.children if isinstance(c, FontDropdown)]
    assert len(dropdowns) == 1
    dropdown = dropdowns[0]
    assert len(dropdown.options) == min(len(AVAILABLE_STYLES), 25)

@pytest.mark.asyncio
async def test_font_dropdown_callback():
    dropdown = FontDropdown("The Raivora", "small_caps")
    dropdown._values = ["bold_gothic"]
    
    interaction = AsyncMock()
    await dropdown.callback(interaction)
    
    assert interaction.response.edit_message.called
    kwargs = interaction.response.edit_message.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "𝕿𝖍𝖊 𝕽𝖆𝖎𝖛𝖔𝖗𝖆" in embed.description

@pytest.mark.asyncio
async def test_font_slash_command():
    bot = MagicMock()
    cog = UtilityCog(bot)
    
    interaction = AsyncMock()
    await cog.font.callback(cog, interaction, text="RAI Sentinel", style="sans_bold")
    
    assert interaction.response.send_message.called
    kwargs = interaction.response.send_message.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "𝗥𝗔𝗜 𝗦𝗲𝗻𝘁𝗶𝗻𝗲𝗹" in embed.description
