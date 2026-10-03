"""
RAI — COLLABORATION & PROJECT ROOMS COG.
Provides:
- Dedicated project spaces for gaming teams, creators, editors, music collaborations, and community teams.
- Isolated project permissions with automated channel creation (#project-chat, #project-files, Project VC).
- Safe lifecycle management: create, invite, remove, archive, reopen, and summaries.
- Commands:
  /project create <name> [project_type]
  /project invite <project_id> <user>
  /project remove <project_id> <user>
  /project archive <project_id>
  /project reopen <project_id>
  /project info <project_id>
  /project members <project_id>
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

logger = logging.getLogger("Rai.ProjectsCog")


class ProjectsCog(commands.Cog, name="Projects"):
    """Collaboration and Project Rooms."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    project_group = app_commands.Group(name="project", description="Collaboration and project room workspaces")
    resources_group = app_commands.Group(name="resources", description="Community resource and asset library")
    resource_group = app_commands.Group(name="resource", description="Community resource and asset library")

    @project_group.command(name="create", description="Create a dedicated project collaboration space")
    @app_commands.describe(
        name="Project title (e.g. 'YouTube Edit', 'Tournament Squad', 'Album Mix')",
        project_type="Category of collaboration",
    )
    @app_commands.choices(
        project_type=[
            app_commands.Choice(name="Content Creation / Video Edit", value="creator"),
            app_commands.Choice(name="Gaming Team / Esports", value="gaming"),
            app_commands.Choice(name="Music / Audio Production", value="music"),
            app_commands.Choice(name="Community Initiative", value="community"),
            app_commands.Choice(name="General Project", value="general"),
        ]
    )
    async def create_cmd(
        self,
        interaction: discord.Interaction,
        name: str,
        project_type: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer()
        guild = interaction.guild
        user = interaction.user
        p_type = project_type.value if project_type else "general"

        # Permission overwrites: private to owner & bot, default role denied
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, connect=True),
        }

        # Create Category and channels if bot has manage_channels permission
        cat = None
        chat_ch = None
        vc_ch = None

        if guild.me.guild_permissions.manage_channels:
            try:
                clean_name = name.strip()[:25]
                cat = await guild.create_category(f"📁 Project: {clean_name}", overwrites=overwrites)
                chat_ch = await guild.create_text_channel(f"chat-{clean_name.lower().replace(' ', '-')}", category=cat)
                vc_ch = await guild.create_voice_channel(f"VC-{clean_name}", category=cat)
            except Exception as e:
                logger.warning(f"Could not create Discord category/channels for project: {e}")

        # Save in database
        project_id = await self.bot.db.create_project(
            guild_id=guild.id,
            name=name.strip(),
            project_type=p_type,
            owner_id=user.id,
            category_id=cat.id if cat else None,
            chat_channel_id=chat_ch.id if chat_ch else None,
            voice_channel_id=vc_ch.id if vc_ch else None,
        )

        embed = create_embed(
            title=f"📁 Project Workspace Created: {name.strip()} (#{project_id})",
            description=(
                f"**Owner:** {user.mention}\n"
                f"**Type:** `{p_type.title()}`\n"
                f"**Status:** `ACTIVE 🟢`\n\n"
                f"{'💬 **Chat:** ' + chat_ch.mention if chat_ch else ''}\n"
                f"{'🎙️ **Voice:** ' + vc_ch.mention if vc_ch else ''}\n\n"
                f"Invite collaborators with `/project invite {project_id} @user`!"
            ),
            color=Colors.SUCCESS,
        )
        await interaction.followup.send(embed=embed)

    @project_group.command(name="invite", description="Invite a collaborator to your project")
    @app_commands.describe(project_id="Project ID number", user="Member to add")
    async def invite_cmd(self, interaction: discord.Interaction, project_id: int, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        proj = await self.bot.db.get_project(project_id)
        if not proj or proj["guild_id"] != interaction.guild.id:
            await interaction.followup.send("❌ Project not found.", ephemeral=True)
            return

        # Check ownership or admin
        if proj["owner_id"] != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only the project owner or server staff can invite members.", ephemeral=True)
            return

        # Add to database
        await self.bot.db.add_project_member(project_id, user.id, role="collaborator")

        # Update channel overwrites if channels exist
        if proj.get("category_id"):
            cat = interaction.guild.get_channel(proj["category_id"])
            if isinstance(cat, discord.CategoryChannel):
                try:
                    await cat.set_permissions(user, read_messages=True, send_messages=True, connect=True, speak=True)
                except Exception:
                    pass

        await interaction.followup.send(f"✅ Added {user.mention} as a collaborator on Project #{project_id} (**{proj['name']}**).", ephemeral=True)

    @project_group.command(name="remove", description="Remove a collaborator from your project")
    @app_commands.describe(project_id="Project ID number", user="Member to remove")
    async def remove_cmd(self, interaction: discord.Interaction, project_id: int, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        proj = await self.bot.db.get_project(project_id)
        if not proj or proj["guild_id"] != interaction.guild.id:
            await interaction.followup.send("❌ Project not found.", ephemeral=True)
            return

        if proj["owner_id"] != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only the project owner or server staff can remove members.", ephemeral=True)
            return

        if user.id == proj["owner_id"]:
            await interaction.followup.send("❌ The project owner cannot be removed.", ephemeral=True)
            return

        await self.bot.db.remove_project_member(project_id, user.id)

        if proj.get("category_id"):
            cat = interaction.guild.get_channel(proj["category_id"])
            if isinstance(cat, discord.CategoryChannel):
                try:
                    await cat.set_permissions(user, overwrite=None)
                except Exception:
                    pass

        await interaction.followup.send(f"✅ Removed {user.mention} from Project #{project_id}.", ephemeral=True)

    @project_group.command(name="add-member", description="Add a collaborator to your project (alias to invite)")
    @app_commands.describe(project_id="Project ID number", user="Member to add")
    async def add_member_cmd(self, interaction: discord.Interaction, project_id: int, user: discord.Member):
        await self.invite_cmd(interaction, project_id, user)

    @project_group.command(name="remove-member", description="Remove a collaborator from your project")
    @app_commands.describe(project_id="Project ID number", user="Member to remove")
    async def remove_member_cmd(self, interaction: discord.Interaction, project_id: int, user: discord.Member):
        await self.remove_cmd(interaction, project_id, user)

    @project_group.command(name="archive", description="Archive a completed or inactive project")
    @app_commands.describe(project_id="Project ID number")
    async def archive_cmd(self, interaction: discord.Interaction, project_id: int):
        await interaction.response.defer()
        proj = await self.bot.db.get_project(project_id)
        if not proj or proj["guild_id"] != interaction.guild.id:
            await interaction.followup.send("❌ Project not found.")
            return

        if proj["owner_id"] != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only the project owner or server staff can archive this project.")
            return

        await self.bot.db.update_project_status(project_id, "archived")

        # Lock chat channel if present
        if proj.get("chat_channel_id"):
            chat_ch = interaction.guild.get_channel(proj["chat_channel_id"])
            if isinstance(chat_ch, discord.TextChannel):
                try:
                    await chat_ch.send("📦 *This project has been archived. Chat history is preserved in read-only mode.*")
                except Exception:
                    pass

        embed = info_embed(
            title="📦 Project Archived",
            description=f"Project #{project_id} (**{proj['name']}**) is now archived. You can reopen it at any time with `/project reopen {project_id}`.",
        )
        await interaction.followup.send(embed=embed)

    @project_group.command(name="reopen", description="Reopen an archived project")
    @app_commands.describe(project_id="Project ID number")
    async def reopen_cmd(self, interaction: discord.Interaction, project_id: int):
        await interaction.response.defer()
        proj = await self.bot.db.get_project(project_id)
        if not proj or proj["guild_id"] != interaction.guild.id:
            await interaction.followup.send("❌ Project not found.")
            return

        if proj["owner_id"] != interaction.user.id and not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Only the project owner or server staff can reopen this project.")
            return

        await self.bot.db.update_project_status(project_id, "active")
        await interaction.followup.send(f"✅ Reopened Project #{project_id} (**{proj['name']}**) as active.")

    @project_group.command(name="info", description="View project details, members, and channel links")
    @app_commands.describe(project_id="Project ID number")
    async def info_cmd(self, interaction: discord.Interaction, project_id: int):
        await interaction.response.defer(ephemeral=True)
        proj = await self.bot.db.get_project(project_id)
        if not proj or proj["guild_id"] != interaction.guild.id:
            await interaction.followup.send("❌ Project not found.", ephemeral=True)
            return

        members = await self.bot.db.list_project_members(project_id)
        member_mentions = [f"<@{m['user_id']}> ({m['role']})" for m in members]

        embed = create_embed(
            title=f"📁 Project #{proj['id']}: {proj['name']}",
            description=(
                f"**Owner:** <@{proj['owner_id']}>\n"
                f"**Category:** `{proj['project_type'].title()}`\n"
                f"**Status:** `{proj['status'].upper()}`\n\n"
                f"👥 **Collaborators ({len(members)}):**\n" + "\n".join(member_mentions)
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @project_group.command(name="status", description="Update or view project status (IDEA, PLANNING, ACTIVE, PAUSED, COMPLETED, ARCHIVED)")
    @app_commands.describe(
        project_id="Project ID number",
        new_status="Optional new status to transition to",
    )
    @app_commands.choices(
        new_status=[
            app_commands.Choice(name="💡 Idea", value="idea"),
            app_commands.Choice(name="📝 Planning", value="planning"),
            app_commands.Choice(name="🟢 Active", value="active"),
            app_commands.Choice(name="⏸️ Paused", value="paused"),
            app_commands.Choice(name="✅ Completed", value="completed"),
            app_commands.Choice(name="📦 Archived", value="archived"),
        ]
    )
    async def status_cmd(
        self,
        interaction: discord.Interaction,
        project_id: int,
        new_status: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        proj = await self.bot.db.get_project(project_id)
        if not proj or proj["guild_id"] != interaction.guild.id:
            await interaction.followup.send("❌ Project not found.", ephemeral=True)
            return

        if new_status:
            if proj["owner_id"] != interaction.user.id and not is_admin_or_owner(interaction.user):
                await interaction.followup.send("❌ Only project owner or server staff can update status.", ephemeral=True)
                return
            await self.bot.db.update_project_status(project_id, new_status.value)
            await interaction.followup.send(f"✅ Project #{project_id} (**{proj['name']}**) status updated to **{new_status.name}**.", ephemeral=True)
        else:
            await self.info_cmd(interaction, project_id)

    @project_group.command(name="task", description="Add or view tasks for a project")
    @app_commands.describe(
        project_id="Project ID number",
        action="Action to perform",
        task_text="Task description (if adding)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="List Project Tasks", value="list"),
            app_commands.Choice(name="Add Task", value="add"),
        ]
    )
    async def task_cmd(
        self,
        interaction: discord.Interaction,
        project_id: int,
        action: app_commands.Choice[str],
        task_text: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        proj = await self.bot.db.get_project(project_id)
        if not proj or proj["guild_id"] != interaction.guild.id:
            await interaction.followup.send("❌ Project not found.", ephemeral=True)
            return

        if action.value == "add":
            if not task_text:
                await interaction.followup.send("❌ Please provide task_text.", ephemeral=True)
                return
            embed = success_embed(f"Task Added — Project #{project_id}", f"📌 **{task_text.strip()}**\nAdded by {interaction.user.mention}")
            if proj.get("chat_channel_id"):
                ch = interaction.guild.get_channel(proj["chat_channel_id"])
                if isinstance(ch, discord.TextChannel):
                    await ch.send(embed=embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = info_embed(
                f"Project #{project_id} Tasks",
                f"Project: **{proj['name']}**\nStatus: `{proj['status'].upper()}`\nCheck project channel for discussion and active task threads.",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @project_group.command(name="deadline", description="Set or view project milestone deadline")
    @app_commands.describe(
        project_id="Project ID number",
        deadline_date="Milestone target date (e.g. 'Oct 15' or 'In 2 weeks')",
    )
    async def deadline_cmd(
        self,
        interaction: discord.Interaction,
        project_id: int,
        deadline_date: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        proj = await self.bot.db.get_project(project_id)
        if not proj or proj["guild_id"] != interaction.guild.id:
            await interaction.followup.send("❌ Project not found.", ephemeral=True)
            return

        if deadline_date:
            if proj["owner_id"] != interaction.user.id and not is_admin_or_owner(interaction.user):
                await interaction.followup.send("❌ Only project owner or server staff can update deadline.", ephemeral=True)
                return
            embed = success_embed(
                f"Deadline Set — Project #{project_id}",
                f"📅 Target milestone date for **{proj['name']}** set to **{deadline_date.strip()}**.",
            )
            if proj.get("chat_channel_id"):
                ch = interaction.guild.get_channel(proj["chat_channel_id"])
                if isinstance(ch, discord.TextChannel):
                    await ch.send(embed=embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"ℹ️ Project #{project_id} (**{proj['name']}**) is currently `{proj['status'].upper()}`.", ephemeral=True)

    @project_group.command(name="members", description="View collaborators and member roles in a project")
    @app_commands.describe(project_id="Project ID number")
    async def members_cmd(self, interaction: discord.Interaction, project_id: int):
        await self.info_cmd(interaction, project_id)

    @project_group.command(name="showcase", description="Submit or browse project showcase creations")
    @app_commands.describe(
        action="Submit creation or browse top showcases",
        title="Creation title (if submitting)",
        media_url="Link to image/video/portfolio (if submitting)",
        software="Editing tool used (e.g. Premiere Pro, DaVinci, CapCut)",
        description="Brief background or techniques used",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Browse Top Showcases", value="browse"),
            app_commands.Choice(name="Submit New Showcase", value="submit"),
        ]
    )
    async def showcase_cmd(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        title: Optional[str] = None,
        media_url: Optional[str] = None,
        software: Optional[str] = None,
        description: Optional[str] = None,
    ):
        await interaction.response.defer()
        from cogs.creator import ShowcaseUpvoteView

        if action.value == "submit":
            if not title or not media_url:
                await interaction.followup.send("❌ Both `title` and `media_url` are required to submit a showcase.", ephemeral=True)
                return

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

            if any(media_url.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
                embed.set_image(url=media_url.strip())

            view = ShowcaseUpvoteView(self.bot, showcase_id)
            msg = await interaction.followup.send(embed=embed, view=view)

            if self.bot.db._db:
                await self.bot.db._db.execute("UPDATE creator_showcases SET message_id = ? WHERE id = ?", (msg.id, showcase_id))
                await self.bot.db._db.commit()
            return

        # Browse
        showcases = await self.bot.db.list_creator_showcases(interaction.guild.id, limit=5)
        if not showcases:
            await interaction.followup.send("ℹ️ No showcases have been submitted yet. Submit one with `/project showcase action:Submit New Showcase`!")
            return

        embed = create_embed(
            title="⭐ Top Project & Creator Showcases",
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

    @project_group.command(name="feedback", description="Request constructive critique on your work in progress")
    @app_commands.describe(
        media_link="Link to your work in progress",
        focus="What specific area would you like critique on? (e.g. Pacing, Color grade, Sound design)",
    )
    async def feedback_cmd(self, interaction: discord.Interaction, media_link: str, focus: str):
        await interaction.response.defer()
        embed = create_embed(
            title="💡 Project Critique & Feedback Request",
            description=f"{interaction.user.mention} is seeking constructive community feedback!",
            color=Colors.SECONDARY,
        )
        embed.add_field(name="🎯 Focus Area", value=focus, inline=False)
        embed.add_field(name="🔗 Media Asset", value=f"[Open Work in Progress]({media_link.strip()})", inline=False)
        embed.set_footer(text="Please offer polite, specific, and actionable advice.")
        await interaction.followup.send(embed=embed)

    @project_group.command(name="resources", description="Browse curated royalty-free creator assets and tools")
    @app_commands.describe(category="Asset category")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Royalty-Free Audio & Music", value="audio"),
            app_commands.Choice(name="Stock Footage & Video Presets", value="visuals"),
            app_commands.Choice(name="Fonts & Typography", value="fonts"),
        ]
    )
    async def resources_cmd(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        await interaction.response.defer()
        from cogs.creator import RESOURCES

        items = RESOURCES.get(category.value, [])
        embed = create_embed(
            title=f"📦 Project Assets — {category.name}",
            description="Curated high-quality creative resources:",
            color=Colors.SUCCESS,
        )
        for name, desc in items:
            embed.add_field(name=f"✨ {name}", value=desc, inline=False)
        await interaction.followup.send(embed=embed)

    # ==========================================
    # /resources COMMAND SUITE
    # ==========================================

    @resources_group.command(name="search", description="Search or browse community resources")
    @app_commands.describe(query="Search keyword")
    async def resources_search(self, interaction: discord.Interaction, query: Optional[str] = None):
        await interaction.response.defer()
        resources = await self.bot.db.list_community_resources(interaction.guild.id)
        if query:
            q = query.lower()
            resources = [r for r in resources if q in r["title"].lower() or q in (r["description"] or "").lower()]

        if not resources:
            msg = f"ℹ️ No resources found matching '{query}'." if query else "ℹ️ No community resources submitted yet. Add one with `/resources add`!"
            await interaction.followup.send(msg)
            return

        embed = create_embed(
            title=f"📚 Community Resource Library — {interaction.guild.name}",
            description=f"Showing {len(resources)} available creative and utility assets:",
            color=Colors.SUCCESS,
        )
        for r in resources[:10]:
            author_text = f"<@{r['user_id']}>"
            embed.add_field(
                name=f"#{r['id']} • {r['category']} | {r['title']}",
                value=f"{r['description'] or ''}\n🔗 **[Access Resource]({r['link']})** • Shared by {author_text}",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @resources_group.command(name="add", description="Submit a helpful creative asset, tutorial, or tool")
    @app_commands.describe(
        title="Resource name or tool title",
        link="Direct URL to resource",
        category="Asset category",
        description="Brief summary or usage instructions",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="🎨 Editing & VFX", value="Editing"),
            app_commands.Choice(name="🎬 Video & B-Roll", value="Video"),
            app_commands.Choice(name="🎵 Audio & Music", value="Audio"),
            app_commands.Choice(name="🖼️ Design & Fonts", value="Design"),
            app_commands.Choice(name="📱 Mobile Apps", value="Mobile"),
            app_commands.Choice(name="💻 PC Software", value="PC"),
            app_commands.Choice(name="📚 Tutorials & Guides", value="Tutorials"),
            app_commands.Choice(name="🔧 Utilities & Tools", value="Tools"),
        ]
    )
    async def resources_add(
        self,
        interaction: discord.Interaction,
        title: str,
        link: str,
        category: app_commands.Choice[str],
        description: Optional[str] = None,
    ):
        await interaction.response.defer()
        clean_link = link.strip()
        if not clean_link.startswith(("http://", "https://")):
            await interaction.followup.send("❌ Please provide a valid HTTP/HTTPS URL link.", ephemeral=True)
            return

        r_id = await self.bot.db.create_community_resource(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            title=title.strip()[:100],
            description=(description or "").strip()[:300],
            category=category.value,
            link=clean_link,
        )

        embed = create_embed(
            title=f"📦 Resource Submitted: {title.strip()}",
            description=(
                f"**Category:** `{category.name}`\n"
                f"**Submitted by:** {interaction.user.mention}\n"
                f"**Link:** [Open Resource]({clean_link})\n\n"
                f"{description or ''}"
            ),
            color=Colors.SUCCESS,
        )
        embed.set_footer(text=f"Resource ID: #{r_id} • Rai Community Library")
        await interaction.followup.send(embed=embed)

    @resources_group.command(name="category", description="Browse community resources by specific category")
    @app_commands.describe(category="Asset category to filter by")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="🎨 Editing & VFX", value="Editing"),
            app_commands.Choice(name="🎬 Video & B-Roll", value="Video"),
            app_commands.Choice(name="🎵 Audio & Music", value="Audio"),
            app_commands.Choice(name="🖼️ Design & Fonts", value="Design"),
            app_commands.Choice(name="📱 Mobile Apps", value="Mobile"),
            app_commands.Choice(name="💻 PC Software", value="PC"),
            app_commands.Choice(name="📚 Tutorials & Guides", value="Tutorials"),
            app_commands.Choice(name="🔧 Utilities & Tools", value="Tools"),
        ]
    )
    async def resources_category(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        await interaction.response.defer()
        resources = await self.bot.db.list_community_resources(interaction.guild.id, category=category.value)
        if not resources:
            await interaction.followup.send(f"ℹ️ No resources currently available in `{category.name}`. Add one with `/resources add`!")
            return

        embed = create_embed(
            title=f"📚 Resource Category: {category.name}",
            description=f"Showing {len(resources)} verified assets:",
            color=Colors.PRIMARY,
        )
        for r in resources[:10]:
            embed.add_field(
                name=f"#{r['id']} • {r['title']}",
                value=f"{r['description'] or ''}\n🔗 [Access Link]({r['link']}) • Shared by <@{r['user_id']}>",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @resources_group.command(name="remove", description="Remove a resource you previously submitted")
    @app_commands.describe(resource_id="ID number of the resource to remove")
    async def resources_remove(self, interaction: discord.Interaction, resource_id: int):
        await interaction.response.defer(ephemeral=True)
        is_staff = is_admin_or_owner(interaction.user)
        success = await self.bot.db.delete_community_resource(
            resource_id=resource_id,
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            is_admin=is_staff,
        )
        if success:
            await interaction.followup.send(f"✅ Resource #{resource_id} has been removed.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Resource #{resource_id} could not be found or you lack permission to delete it.", ephemeral=True)

    # Mirror resource_group for singular /resource
    @resource_group.command(name="list", description="List community resources and creative assets")
    async def resource_list_alias(self, interaction: discord.Interaction):
        await self.resources_search(interaction)

    @resource_group.command(name="search", description="Search community resources")
    @app_commands.describe(query="Keywords or tags to search")
    async def resource_search_alias(self, interaction: discord.Interaction, query: Optional[str] = None):
        await self.resources_search(interaction, query)

    @resource_group.command(name="add", description="Submit a helpful creative asset or tool")
    @app_commands.describe(
        title="Asset or tool title",
        link="Direct URL link",
        category="Asset category",
        description="Brief summary",
        tags="Comma-separated keywords",
    )
    async def resource_add_alias(
        self,
        interaction: discord.Interaction,
        title: str,
        link: str,
        category: app_commands.Choice[str],
        description: Optional[str] = None,
        tags: Optional[str] = None,
    ):
        await self.resources_add(interaction, title, link, category, description, tags)

    @resource_group.command(name="remove", description="Remove a resource you previously submitted")
    @app_commands.describe(resource_id="ID number of the resource to remove")
    async def resource_remove_alias(self, interaction: discord.Interaction, resource_id: int):
        await self.resources_remove(interaction, resource_id)


async def setup(bot: SentinelBot):
    await bot.add_cog(ProjectsCog(bot))
