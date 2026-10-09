"""
Rai Creator Hub Cog.
Provides:
- Creator showcase submissions with interactive ⭐ upvoting
- Feedback requests for video/photo editing
- Curated editing tips (Premiere, After Effects, DaVinci, Photoshop, CapCut)
- High-quality design and editing resources
- Creator studio temporary voice rooms
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from database.models import CreatorShowcase
from utils.embeds import create_embed, error_embed, info_embed, success_embed

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

EDITING_TIPS = {
    "premiere": [
        ("Use Adjustment Layers", "Apply Lumetri color grades, blurs, or crops across multiple clips without touching individual media."),
        ("Dynamic Link with After Effects", "Right click a clip -> 'Replace with After Effects Composition' to animate titles and VFX seamlessly."),
        ("Pancake Timelines", "Stack your raw sequence above your master sequence to drag selects downward in seconds."),
    ],
    "davinci": [
        ("Node Organization", "Label your color nodes (e.g. Exposure, WB, Contrast, Look, Vignette) for clean and reversible grading."),
        ("Fairlight Audio Ducking", "Use sidechain compression in Fairlight to cleanly duck background music whenever dialogue speaks."),
        ("Render Cache Smart Mode", "Turn playback render cache to Smart for buttery smooth 60fps editing of 4K footage."),
    ],
    "after_effects": [
        ("Easy Ease Shortcuts", "Select keyframes and press F9 for smooth velocity curves. Fine-tune in the Graph Editor."),
        ("Null Object Parents", "Parent multiple layers to a Null Object to control camera moves and scale transitions effortlessly."),
        ("Motion Blur Switch", "Always enable the composition-level motion blur switch for realistic movement on transform keyframes."),
    ],
    "photoshop": [
        ("Smart Objects", "Always convert layers to Smart Objects before resizing or applying filters so edits remain non-destructive."),
        ("High-Pass Frequency Separation", "Use high-pass filters with linear light for skin retouching that preserves organic texture."),
        ("Custom Curves Luminescence", "Set your Curves adjustment layer to Luminosity mode to prevent unwanted color shifts."),
    ],
    "mobile": [
        ("CapCut Keyframing", "Use diamond keyframes for custom zooms and pans rather than default automated transitions."),
        ("Speed Ramping", "Use bezier velocity curves in CapCut or Alight Motion to create punchy syncs on musical beats."),
    ],
}

RESOURCES = {
    "audio": [
        ("FreeSound.org", "Massive open-source library of royalty-free sound effects and ambient tracks."),
        ("YouTube Audio Library", "High-quality, copyright-cleared background music for content creators."),
        ("Incompetech", "Classic royalty-free music by Kevin MacLeod with simple attribution."),
    ],
    "visuals": [
        ("Unsplash & Pexels", "High-resolution, completely free commercial stock photography and 4K B-roll footage."),
        ("Mixkit", "Free video assets, Premiere Pro title templates, and transition presets."),
        ("Envato Elements Free Monthly", "Rotating free professional design mockups, fonts, and overlays."),
    ],
    "fonts": [
        ("Google Fonts", "1,500+ open source typefaces optimized for screens, videos, and modern branding."),
        ("DaFont / FontSpace", "Free stylized display fonts for thumbnails and video title sequences."),
    ],
}


class ShowcaseUpvoteView(discord.ui.View):
    def __init__(self, bot: SentinelBot, showcase_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.showcase_id = showcase_id
        self.voted_users: set[int] = set()

    @discord.ui.button(label="Upvote", style=discord.ButtonStyle.secondary, emoji="⭐", custom_id="showcase_upvote_btn")
    async def upvote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.voted_users:
            await interaction.response.send_message("ℹ️ You have already upvoted this creation!", ephemeral=True)
            return

        self.voted_users.add(interaction.user.id)
        new_count = await self.bot.db.upvote_creator_showcase(self.showcase_id)

        button.label = f"Upvote ({new_count})"
        button.style = discord.ButtonStyle.primary
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"⭐ Upvoted! Total stars: **{new_count}**", ephemeral=True)


class CreatorCog(commands.Cog, name="Creator"):
    """Creator Hub, Showcase, Feedback, and Editing Tips."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    creator_group = app_commands.Group(name="creator", description="Creator Hub tools and resources")
    showcase_group = app_commands.Group(name="showcase", description="Community creator showcase commands")

    # ==========================================
    # SHOWCASE COMMANDS
    # ==========================================

    @showcase_group.command(name="submit", description="Submit your edit, photo, or artwork to the community showcase")
    @app_commands.describe(
        title="Title of your creation",
        media_url="Direct link to image, video, ArtStation, or YouTube portfolio",
        software="Editing tool used (e.g. Premiere Pro, DaVinci, After Effects, Photoshop, CapCut)",
        description="Brief background or techniques used"
    )
    async def submit_showcase(
        self,
        interaction: discord.Interaction,
        title: str,
        media_url: str,
        software: Optional[str] = None,
        description: Optional[str] = None,
    ):
        await interaction.response.defer()

        showcase_id = await self.bot.db.create_creator_showcase(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            title=title.strip(),
            media_url=media_url.strip(),
            software=software.strip() if software else None,
            description=description.strip() if description else None,
        )

        embed = create_embed(
            title=f"🎨 Creator Showcase: {title.strip()}",
            description=f"Created by {interaction.user.mention}\n\n{description or ''}\n\n🔗 **[View Media Asset]({media_url.strip()})**",
            color=Colors.PRIMARY,
        )
        if software:
            embed.add_field(name="🛠️ Software / Tool", value=software, inline=True)
        embed.set_footer(text="Show your appreciation by clicking ⭐ Upvote below!")

        # If it's an image link, display thumbnail
        if any(media_url.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
            embed.set_image(url=media_url.strip())

        view = ShowcaseUpvoteView(self.bot, showcase_id)
        msg = await interaction.followup.send(embed=embed, view=view)

        if self.bot.db._db:
            await self.bot.db._db.execute("UPDATE creator_showcases SET message_id = ? WHERE id = ?", (msg.id, showcase_id))
            await self.bot.db._db.commit()

    @showcase_group.command(name="top", description="View the most upvoted community creations")
    async def top_showcases(self, interaction: discord.Interaction):
        await interaction.response.defer()
        showcases = await self.bot.db.list_creator_showcases(interaction.guild.id, limit=5)
        if not showcases:
            await interaction.followup.send("ℹ️ No showcases have been submitted yet. Be the first with `/showcase submit`!")
            return

        embed = create_embed(
            title="⭐ Top Community Showcases",
            description="Leading creations recognized by the community:",
            color=Colors.GOLD,
        )
        for s in showcases:
            author_mention = f"<@{s.user_id}>"
            embed.add_field(
                name=f"⭐ {s.upvotes} | {s.title}",
                value=f"By: {author_mention} • [Link]({s.media_url})",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    # ==========================================
    # CREATOR TOOLS & RESOURCES
    # ==========================================

    @creator_group.command(name="feedback", description="Request constructive feedback on your edit or artwork")
    @app_commands.describe(
        media_link="Link to your work in progress",
        focus="What specific area would you like critique on? (e.g. Pacing, Color grade, Sound design)"
    )
    async def request_feedback(
        self,
        interaction: discord.Interaction,
        media_link: str,
        focus: str,
    ):
        await interaction.response.defer()
        embed = create_embed(
            title="💡 Critique & Feedback Request",
            description=f"{interaction.user.mention} is seeking constructive community feedback!",
            color=Colors.SECONDARY,
        )
        embed.add_field(name="🎯 Focus Area", value=focus, inline=False)
        embed.add_field(name="🔗 Media Asset", value=f"[Open Work in Progress]({media_link.strip()})", inline=False)
        embed.set_footer(text="Please offer polite, specific, and actionable advice.")
        await interaction.followup.send(embed=embed)

    @creator_group.command(name="tip", description="Get professional editing and production tips")
    @app_commands.describe(software="Select editing software")
    @app_commands.choices(
        software=[
            app_commands.Choice(name="Adobe Premiere Pro", value="premiere"),
            app_commands.Choice(name="DaVinci Resolve", value="davinci"),
            app_commands.Choice(name="After Effects", value="after_effects"),
            app_commands.Choice(name="Photoshop", value="photoshop"),
            app_commands.Choice(name="Mobile Editing (CapCut)", value="mobile"),
        ]
    )
    async def editing_tip(self, interaction: discord.Interaction, software: app_commands.Choice[str]):
        await interaction.response.defer()
        tips = EDITING_TIPS.get(software.value, [])
        embed = create_embed(
            title=f"🎬 Production Tips — {software.name}",
            description="Pro workflows and time-savers:",
            color=Colors.PRIMARY,
        )
        for title, desc in tips:
            embed.add_field(name=f"💡 {title}", value=desc, inline=False)
        await interaction.followup.send(embed=embed)

    @creator_group.command(name="resources", description="Browse curated royalty-free sound, video, and font resources")
    @app_commands.describe(category="Asset category")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Royalty-Free Audio & Music", value="audio"),
            app_commands.Choice(name="Stock Footage & Video Presets", value="visuals"),
            app_commands.Choice(name="Fonts & Typography", value="fonts"),
        ]
    )
    async def resources(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        await interaction.response.defer()
        items = RESOURCES.get(category.value, [])
        embed = create_embed(
            title=f"📦 Creator Assets — {category.name}",
            description="Curated high-quality creative resources:",
            color=Colors.SUCCESS,
        )
        for name, desc in items:
            embed.add_field(name=f"✨ {name}", value=desc, inline=False)
        await interaction.followup.send(embed=embed)

    @creator_group.command(name="room", description="Create a temporary creator studio voice room")
    @app_commands.describe(studio_type="Type of studio needed")
    @app_commands.choices(
        studio_type=[
            app_commands.Choice(name="PC Editing", value="PC Editing"),
            app_commands.Choice(name="Mobile Editing", value="Mobile Editing"),
            app_commands.Choice(name="Video Studio", value="Video Studio"),
            app_commands.Choice(name="Audio Studio", value="Audio Studio"),
            app_commands.Choice(name="Work Together (Co-Working)", value="Work Together"),
        ]
    )
    async def create_creator_room(self, interaction: discord.Interaction, studio_type: app_commands.Choice[str]):
        await interaction.response.defer()
        guild = interaction.guild

        category = discord.utils.find(lambda c: "CREATOR" in c.name.upper(), guild.categories)
        channel_name = f"🎨・{studio_type.value}"

        vc = await guild.create_voice_channel(
            name=channel_name,
            category=category,
            reason=f"Creator studio room created by {interaction.user}",
        )

        if interaction.user.voice and interaction.user.voice.channel:
            try:
                await interaction.user.move_to(vc)
            except Exception:
                pass

        embed = success_embed(
            "Studio Created",
            f"Created creator voice studio {vc.mention} for **{studio_type.name}**.",
        )
        await interaction.followup.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Intelligent media showcase engine: auto-reacts, threads, and keeps gallery clean."""
        if message.author.bot or not message.guild:
            return
        if message.channel.id != 1551184138932068373:  # #📸・MEDIA-AND-CLIPS
            return

        has_media = bool(message.attachments)
        if not has_media:
            content_lower = message.content.lower()
            media_domains = (
                "youtube.com", "youtu.be", "tiktok.com", "medal.tv",
                "twitch.tv", "twitter.com", "x.com", "streamable.com",
                "imgur.com", "giphy.com", "tenor.com", ".mp4", ".mov",
                ".webm", ".png", ".jpg", ".jpeg", ".webp", ".gif"
            )
            has_media = any(dom in content_lower for dom in media_domains)

        if has_media:
            # Auto-react with star for weekly spotlight voting
            try:
                await message.add_reaction("⭐")
            except Exception:
                pass

            # Auto-create discussion thread to keep main gallery clean
            try:
                author_name = message.author.display_name[:20]
                thread_name = f"💬・Comments on {author_name}'s Clip"
                await message.create_thread(
                    name=thread_name,
                    auto_archive_duration=1440,
                    reason="Media Showcase Auto-Thread"
                )
            except Exception as e:
                logger.debug(f"Auto-thread creation skipped: {e}")
        else:
            # Non-media plain text message in gallery
            try:
                await message.delete()
                await message.channel.send(
                    f"👋 {message.author.mention}, this channel is a dedicated media & clip showcase! "
                    f"Please share clips or artwork here, or chat in <#1545502730699808768> (`#💬・ɢᴇɴᴇʀᴀʟ-ᴄʜᴀᴛ`).",
                    delete_after=7,
                )
            except Exception:
                pass


async def setup(bot: SentinelBot):
    await bot.add_cog(CreatorCog(bot))
