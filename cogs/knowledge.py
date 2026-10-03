"""
RAI — SERVER KNOWLEDGE & RESOURCE SYSTEM COG.
Provides:
- Searchable server knowledge base (rules, guides, resource presets, FAQs, wikis).
- Strict information boundary classification:
  - [KNOWN SERVER INFORMATION]
  - [GENERAL INFORMATION]
  - [UNCERTAIN INFORMATION]
  Never hallucinates or invents server policies.
- Commands:
  /server guide
  /server faq
  /server resources
  /server wiki
  /server search <query>
  /server add-knowledge <topic> <content> [category]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.KnowledgeCog")


class KnowledgeCog(commands.Cog, name="Knowledge"):
    """Server Knowledge and Resource Base."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    server_group = app_commands.Group(name="server", description="Server knowledge, FAQs, guides, and resources")

    @server_group.command(name="guide", description="View the official server guide and community handbook")
    async def guide_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        entry = await self.bot.db.get_knowledge_entry(interaction.guild.id, "guide")
        content = entry["content"] if entry else "Welcome to our community! Please follow server rules, respect members, and check our designated channels for announcements."

        embed = create_embed(
            title=f"📖 SERVER GUIDE — {interaction.guild.name}",
            description=f"**[KNOWN SERVER INFORMATION]**\n\n{content}",
            color=Colors.PRIMARY,
        )
        embed.set_footer(text="Verified official server guidance.")
        await interaction.followup.send(embed=embed)

    @server_group.command(name="faq", description="View frequently asked questions and official answers")
    async def faq_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        entries = await self.bot.db.list_knowledge_entries(interaction.guild.id, category="faq")

        embed = create_embed(
            title=f"❓ Server FAQ — {interaction.guild.name}",
            description="**[KNOWN SERVER INFORMATION]**\nFrequently Asked Questions:",
            color=Colors.PRIMARY,
        )
        if entries:
            for e in entries[:10]:
                embed.add_field(name=f"Q: {e['topic'].title()}", value=f"A: {e['content']}", inline=False)
        else:
            embed.description += "\n\nNo FAQ entries configured yet. Staff can add them with `/server add-knowledge`!"

        await interaction.followup.send(embed=embed)

    @server_group.command(name="resources", description="Find links to server editing presets, templates, or community files")
    async def resources_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        entries = await self.bot.db.list_knowledge_entries(interaction.guild.id, category="resource")

        embed = create_embed(
            title=f"📦 Community Resources & Presets — {interaction.guild.name}",
            description="**[KNOWN SERVER INFORMATION]**\nConfigured server resources and download links:",
            color=Colors.PRIMARY,
        )
        if entries:
            for e in entries[:10]:
                embed.add_field(name=f"🔗 {e['topic'].title()}", value=e['content'], inline=False)
        else:
            embed.description += "\n\nNo resource links configured yet."

        await interaction.followup.send(embed=embed)

    @server_group.command(name="wiki", description="Access the server documentation wiki")
    async def wiki_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        entries = await self.bot.db.list_knowledge_entries(interaction.guild.id)

        embed = create_embed(
            title=f"📚 Server Knowledge Base & Wiki — {interaction.guild.name}",
            description=f"**[KNOWN SERVER INFORMATION]**\nThis server has **{len(entries)}** documented knowledge topics:",
            color=Colors.PRIMARY,
        )
        if entries:
            for e in entries[:12]:
                embed.add_field(name=f"📄 {e['topic'].title()} [{e['category'].upper()}]", value=e['content'][:100], inline=True)
        else:
            embed.description += "\n\nThe wiki is currently empty. Staff can add topics with `/server add-knowledge`."

        await interaction.followup.send(embed=embed)

    @server_group.command(name="search", description="Search the server knowledge base for answers")
    @app_commands.describe(query="The keyword, rule, or topic you are searching for")
    async def search_cmd(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=False)
        results = await self.bot.db.search_knowledge_entries(interaction.guild.id, query, limit=5)

        embed = create_embed(
            title=f"🔍 Knowledge Search: \"{query}\"",
            color=Colors.PRIMARY,
        )

        if results:
            embed.description = "**[KNOWN SERVER INFORMATION]**\nFound the following matching documentation:"
            for r in results:
                embed.add_field(
                    name=f"📌 {r['topic'].title()} ({r['category'].upper()})",
                    value=r['content'],
                    inline=False,
                )
        else:
            embed.description = (
                f"**[UNCERTAIN INFORMATION]**\n"
                f"No specific server policy or guide was found matching *\"{query}\"*.\n"
                f"*Rai will not invent or guess server policies. Please consult a staff member.*"
            )

        await interaction.followup.send(embed=embed)

    @server_group.command(name="add-knowledge", description="Add or update a topic in the server knowledge base (Staff only)")
    @app_commands.describe(
        topic="The topic identifier (e.g. 'rules', 'tournaments', 'editing-preset', 'streamer-guide')",
        content="The full documentation or instructions",
        category="Category tag (guide, faq, resource, rules)",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Guide / Handbook", value="guide"),
            app_commands.Choice(name="FAQ Entry", value="faq"),
            app_commands.Choice(name="Resource Link / Preset", value="resource"),
            app_commands.Choice(name="Rule Clarification", value="rules"),
        ]
    )
    async def add_knowledge_cmd(
        self,
        interaction: discord.Interaction,
        topic: str,
        content: str,
        category: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only staff can add server knowledge entries.", ephemeral=True)
            return

        cat = category.value if category else "guide"
        await self.bot.db.add_knowledge_entry(
            guild_id=interaction.guild.id,
            topic=topic.strip().lower(),
            content=content.strip(),
            category=cat,
            created_by=interaction.user.id,
        )

        embed = success_embed(
            title="📚 Knowledge Entry Saved",
            description=f"Added topic **{topic.strip().lower()}** under category `{cat}`.\nMembers can now query this via `/server search`.",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(KnowledgeCog(bot))
