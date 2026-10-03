"""
Rai AI Mascot & Chat Companion Cog.
Features:
- Conversational AI Companion activated by pinging @The Raivora in chat
- Powered by Cloud Gemini 1.5 Flash + Embedded Heuristic Neural Persona
- Knows server lore, founder rc.rai_007, gaming modes, economy, and AutoMod rules
- Slash command: /askrai for direct inquiries
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.ai_security_brain import AISecurityBrain
from utils.embeds import create_embed

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class AICompanionCog(commands.Cog, name="AI Companion"):
    """Rai AI Mascot & Intelligent Chat Companion."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.brain = AISecurityBrain(bot)

    # ==========================================
    # CHAT MENTION LISTENER
    # ==========================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Responds conversationally when mentioned in text channels."""
        # Ignore bots, webhooks, or DMs
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return

        # Check if the bot was mentioned directly (and not via @everyone/@here)
        if self.bot.user not in message.mentions or message.mention_everyone:
            return

        # Clean mention tags from text
        clean_content = re.sub(rf"<@!?{self.bot.user.id}>", "", message.content).strip()

        # Generate response
        try:
            async with message.channel.typing():
                response_text = await self.brain.generate_chat_response(
                    prompt=clean_content,
                    user_name=message.author.display_name,
                    guild_name=message.guild.name,
                )
                await message.reply(response_text, mention_author=False)
        except Exception as e:
            logger.warning(f"Error generating AI companion response: {e}")

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @app_commands.command(name="askrai", description="Ask Rai AI anything about the server, gaming, or general chat")
    @app_commands.describe(question="Your question or message for Rai")
    async def ask_rai(self, interaction: discord.Interaction, question: str):
        """Direct AI inquiry."""
        await interaction.response.defer()
        guild_name = interaction.guild.name if interaction.guild else "RAI FAM💗"
        response_text = await self.brain.generate_chat_response(
            prompt=question,
            user_name=interaction.user.display_name,
            guild_name=guild_name,
        )

        embed = discord.Embed(
            title="🍸 Rai AI Companion",
            description=response_text,
            color=0x9B59B6,
        )
        embed.set_footer(text=f"Engine: {self.brain.active_engine_name} • RAI FAM💗")
        await interaction.followup.send(embed=embed)


async def setup(bot: SentinelBot):
    await bot.add_cog(AICompanionCog(bot))
