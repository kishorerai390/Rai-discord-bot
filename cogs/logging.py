"""
Comprehensive Server Audit Logging Cog.
Routes logs to dedicated channels:
- Member Joins & Leaves
- Message Deletions & Edits
- Voice Channel Events
- Role & Channel Updates
- Moderation & Security events
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional, List, Dict
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner
from utils.ai_incident_responder import AIIncidentAnalyzer, OwnerIncidentActionView, IncidentAlertTracker

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class LoggingCog(commands.Cog, name="Logging"):
    """Server activity and audit logging."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._role_delete_buffer: dict[int, list[tuple[str, int]]] = {}
        self._role_delete_tasks: dict[int, asyncio.Task] = {}
        self._role_create_buffer: dict[int, list[tuple[str, int]]] = {}
        self._role_create_tasks: dict[int, asyncio.Task] = {}
        self._founder_dm_timestamps: dict[int, list[float]] = {}
        self._voice_session_times: dict[tuple[int, int], float] = {}
        self._voice_hops: dict[tuple[int, int], list[float]] = {}

    def cog_unload(self):
        for task in list(self._role_delete_tasks.values()) + list(self._role_create_tasks.values()):
            task.cancel()

    logging_group = app_commands.Group(
        name="logging",
        description="Configure server audit logging channels",
        default_permissions=discord.Permissions(administrator=True),
    )

    async def _dispatch_founder_activity_dm(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Sends the live activity embed directly to the Founder / Owner in DM with AI analysis and action buttons."""
        try:
            enabled = await self.bot.db.get_founder_activity_dm(guild.id)
        except Exception:
            enabled = False

        if not enabled:
            return

        low_title = (embed.title or "").lower()
        # Routine voice lifecycle and state changes are purely local audio logs; NEVER dispatch as security incident alerts
        if any(term in low_title for term in [
            "microphone muted", "microphone unmuted",
            "audio deafened", "audio undeafened",
            "camera turned on", "camera turned off",
            "stream ended",
            "voice room connected",
            "voice room disconnected",
            "voice room switched",
            "voice room created",
            "voice room deleted",
            "room closed",
            "temporary voice",
        ]):
            return

        now = time.time()
        timestamps = self._founder_dm_timestamps.get(guild.id, [])
        # Keep timestamps from the last 10 seconds
        timestamps = [t for t in timestamps if now - t < 10.0]
        self._founder_dm_timestamps[guild.id] = timestamps

        # Rate-limit to max 5 DMs per 10s per guild to protect against Discord DM rate-limits
        if len(timestamps) >= 5:
            return
        timestamps.append(now)

        # Locate designated recipient or guild owner
        target_user = None
        try:
            recipient_id = await self.bot.db.get_founder_dm_recipient(guild.id)
            if recipient_id:
                target_user = self.bot.get_user(recipient_id)
                if not target_user:
                    target_user = await self.bot.fetch_user(recipient_id)
        except Exception:
            target_user = None

        if not target_user:
            if guild.owner:
                target_user = guild.owner
            elif guild.owner_id:
                try:
                    target_user = self.bot.get_user(guild.owner_id)
                    if not target_user:
                        target_user = await self.bot.fetch_user(guild.owner_id)
                except Exception:
                    target_user = None

        if target_user and not getattr(target_user, "bot", False):
            # Run AI Incident Analysis
            ctx = context or {}
            event_type = ctx.get("event_type", "general")
            target_id = ctx.get("target_id")
            target_name = ctx.get("target_name")
            actor = ctx.get("actor")

            analysis = AIIncidentAnalyzer.analyze(
                event_type=event_type,
                title=embed.title or "Server Activity",
                description=embed.description or "",
                actor=actor,
                target_name=target_name,
            )

            from utils.owner_reporter import generate_incident_id, OwnerReporter
            inc_id = ctx.get("incident_id") or generate_incident_id()

            # Build enriched DM embed with AI Analysis (shared with private report channel)
            dm_embed = discord.Embed.from_dict(embed.to_dict())
            dm_embed.add_field(name="🆔 Incident ID", value=f"`{inc_id}`", inline=True)
            dm_embed.add_field(
                name="🧠 AI Incident Triage",
                value=(
                    f"• **Threat Level:** {analysis.threat_level}\n"
                    f"• **Assessment:** {analysis.assessment}\n"
                    f"• **Recommendation:** {analysis.recommendation}"
                ),
                inline=False,
            )
            dm_embed.set_footer(text=f"Rai AI Security Console • {inc_id} • {guild.name}")

            pending_count = IncidentAlertTracker.get_pending_count(target_user.id) + 1

            view = OwnerIncidentActionView(
                bot=self.bot,
                guild_id=guild.id,
                target_id=target_id,
                target_name=target_name,
                actor_id=actor.id if actor else None,
                event_type=event_type,
                owner_id=target_user.id,
                analysis=analysis,
                pending_count=pending_count,
            )

            # 1. 📩 SERVER OWNER DM
            try:
                sent_msg = await target_user.send(embed=dm_embed, view=view)
                IncidentAlertTracker.add_alert(target_user.id, sent_msg)
            except (discord.Forbidden, discord.HTTPException):
                try:
                    await target_user.send(embed=dm_embed)
                except Exception:
                    pass

            # 2. 📋 CORRESPONDING PRIVATE REPORT CHANNEL IN SERVER
            try:
                low_title = (embed.title or "").lower()
                if any(k in event_type for k in ["voice", "room"]) or any(k in low_title for k in ["voice", "microphone", "camera", "stream", "audio", "deafened"]):
                    channel_key = "room_report_id"
                elif any(k in event_type for k in ["music", "track"]):
                    channel_key = "music_report_id"
                elif any(k in event_type for k in ["member", "message"]):
                    channel_key = "mod_report_id"
                elif any(k in event_type for k in ["anti_raid", "anti_nuke", "anti_spam", "everyone_mention", "phishing", "threat"]) or "security" in low_title or "incident" in low_title:
                    channel_key = "security_report_id"
                elif any(k in event_type for k in ["channel", "role", "thread", "bot"]):
                    channel_key = "bot_report_id"
                else:
                    channel_key = "system_report_id"

                from utils.owner_reporter import get_owner_report_channel
                cat_name = channel_key.replace("_report_id", "")
                rep_channel = await get_owner_report_channel(self.bot, guild.id, cat_name)
                if rep_channel and isinstance(rep_channel, discord.TextChannel):
                    try:
                        ch_view = OwnerIncidentActionView(
                            bot=self.bot,
                            guild_id=guild.id,
                            target_id=target_id,
                            target_name=target_name,
                            actor_id=actor.id if actor else None,
                            event_type=event_type,
                            owner_id=target_user.id,
                            analysis=analysis,
                            pending_count=pending_count,
                        )
                        await rep_channel.send(embed=dm_embed, view=ch_view)
                    except Exception as ch_send_err:
                        logger.warning(f"Direct send to report channel failed: {ch_send_err}")
            except Exception as e:
                logger.warning(f"Failed to route activity embed to private report channel: {e}")

    async def _send_log(
        self,
        guild: discord.Guild,
        channel_attr: str,
        embed: discord.Embed,
        context: Optional[Dict[str, Any]] = None,
        dispatch_dm: bool = True,
    ) -> None:
        """Helper to send log embed to channel specified in logging_config, and to Founder in DM."""
        cfg = await self.bot.db.get_logging_config(guild.id)
        channel_id = getattr(cfg, channel_attr, None) or cfg.general_channel_id
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    # Public log channel receives clean embed WITHOUT buttons
                    await channel.send(embed=embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

        # Real-time alert to Founder in DM WITH AI analysis and interactive action buttons
        if dispatch_dm:
            await self._dispatch_founder_activity_dm(guild, embed, context)

    # ==========================================
    # EVENT LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = create_embed(
            title="📥 Member Joined",
            description=f"{member.mention} (`{member.id}`)",
            color=Colors.SUCCESS,
            thumbnail_url=member.display_avatar.url,
        )
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Server Member Count", value=str(member.guild.member_count), inline=True)
        await self._send_log(member.guild, "member_channel_id", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = create_embed(
            title="📤 Member Left",
            description=f"**{member.name}** (`{member.id}`)",
            color=Colors.ERROR,
            thumbnail_url=member.display_avatar.url,
        )
        roles = [r.mention for r in member.roles if not r.is_default()]
        if roles:
            embed.add_field(name="Roles Held", value=", ".join(roles[:15]), inline=False)
        embed.add_field(name="Server Member Count", value=str(member.guild.member_count), inline=True)
        await self._send_log(member.guild, "member_channel_id", embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        embed = create_embed(
            title="🗑️ Message Deleted",
            description=f"**Author:** {message.author.mention} (`{message.author.id}`)\n**Channel:** {message.channel.mention}",
            color=Colors.ERROR,
        )
        if message.content:
            embed.add_field(name="Content", value=f"```{message.content[:1000]}```", inline=False)
        if message.attachments:
            names = [a.filename for a in message.attachments]
            embed.add_field(name="Attachments", value=", ".join(names), inline=False)

        await self._send_log(message.guild, "message_channel_id", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return

        embed = create_embed(
            title="✏️ Message Edited",
            description=f"**Author:** {before.author.mention} (`{before.author.id}`)\n**Channel:** {before.channel.mention}\n[Jump to Message]({after.jump_url})",
            color=Colors.INFO,
        )
        embed.add_field(name="Before", value=f"```{before.content[:500]}```", inline=False)
        embed.add_field(name="After", value=f"```{after.content[:500]}```", inline=False)
        await self._send_log(before.guild, "message_channel_id", embed)

    async def _is_hidden_voice(self, channel: Optional[discord.abc.GuildChannel]) -> bool:
        if not channel:
            return False
        if getattr(channel, "name", "").startswith("🔒"):
            return True
        if hasattr(self.bot, "db") and self.bot.db:
            try:
                fn = getattr(self.bot.db, "get_hidden_voice_room", None)
                if callable(fn):
                    res = fn(channel.id)
                    if asyncio.iscoroutine(res):
                        room = await res
                        if room:
                            return True
            except Exception:
                pass
        return False

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Do not expose hidden voice rooms in public logs
        if (after.channel and await self._is_hidden_voice(after.channel)) or (before.channel and await self._is_hidden_voice(before.channel)):
            return

        now = time.monotonic()
        key = (member.guild.id, member.id)

        if before.channel == after.channel:
            # Check for non-channel voice updates: stream, video, server mute, server deaf, self mute, self deaf
            embed = None
            if not before.self_stream and after.self_stream and after.channel:
                embed = create_embed(title="📺 Screen Share / Stream Started", color=0x5865F2)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.description = f"{member.mention} started screen sharing / streaming in **#{after.channel.name}**."
            elif before.self_stream and not after.self_stream and after.channel:
                embed = create_embed(title="⏹️ Stream Ended", color=Colors.DARK)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.description = f"{member.mention} stopped streaming in **#{after.channel.name}**."
            elif not before.self_video and after.self_video and after.channel:
                embed = create_embed(title="📹 Camera Turned On", color=Colors.SUCCESS)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.description = f"{member.mention} turned on camera in **#{after.channel.name}**."
            elif before.self_video and not after.self_video and after.channel:
                embed = create_embed(title="📷 Camera Turned Off", color=Colors.DARK)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.description = f"{member.mention} turned off camera in **#{after.channel.name}**."
            elif not before.self_mute and after.self_mute and after.channel:
                embed = create_embed(title="🔇 Microphone Muted", color=Colors.DARK)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.description = f"{member.mention} muted their microphone in **#{after.channel.name}**."
            elif before.self_mute and not after.self_mute and after.channel:
                embed = create_embed(title="🎙️ Microphone Unmuted", color=Colors.SUCCESS)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.description = f"{member.mention} unmuted their microphone in **#{after.channel.name}**."
            elif not before.self_deaf and after.self_deaf and after.channel:
                embed = create_embed(title="🎧 Audio Deafened", color=Colors.DARK)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.description = f"{member.mention} deafened their audio in **#{after.channel.name}**."
            elif before.self_deaf and not after.self_deaf and after.channel:
                embed = create_embed(title="👂 Audio Undeafened", color=Colors.SUCCESS)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.description = f"{member.mention} undeafened their audio in **#{after.channel.name}**."
            elif not before.mute and after.mute and after.channel:
                embed = create_embed(title="⚠️ Member Server-Muted", color=Colors.WARNING)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.description = f"{member.mention} was **server-muted** by staff in **#{after.channel.name}**."
            elif not before.deaf and after.deaf and after.channel:
                embed = create_embed(title="⚠️ Member Server-Deafened", color=Colors.WARNING)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                embed.description = f"{member.mention} was **server-deafened** by staff in **#{after.channel.name}**."

            if embed:
                await self._send_log(member.guild, "voice_channel_id", embed, dispatch_dm=False)
            return

        if before.channel is None and after.channel is not None:
            # User Joined VC
            self._voice_session_times[key] = now
            occupants = len(after.channel.members)
            embed = create_embed(title="📥 Voice Room Connected", color=Colors.SUCCESS)
            embed.set_author(name=member.name, icon_url=member.display_avatar.url)
            embed.description = (
                f"{member.mention} connected to **#{after.channel.name}**\n"
                f"👥 **Occupants:** `{occupants} member(s) in room`"
            )
            await self._send_log(member.guild, "voice_channel_id", embed, dispatch_dm=False)

        elif before.channel is not None and after.channel is None:
            # User Left VC
            join_time = self._voice_session_times.pop(key, None)
            if join_time:
                duration_sec = int(now - join_time)
                m, s = divmod(duration_sec, 60)
                h, m = divmod(m, 60)
                dur_str = f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"
            else:
                dur_str = "Session ended"

            embed = create_embed(title="📤 Voice Room Disconnected", color=Colors.ERROR)
            embed.set_author(name=member.name, icon_url=member.display_avatar.url)
            embed.description = (
                f"{member.mention} left **#{before.channel.name}**\n"
                f"⏱️ **Session Duration:** `{dur_str}`"
            )
            await self._send_log(member.guild, "voice_channel_id", embed, dispatch_dm=False)

        else:
            # User Switched VC
            hops = self._voice_hops.get(key, [])
            hops = [t for t in hops if now - t < 10.0]
            hops.append(now)
            self._voice_hops[key] = hops

            is_hopping = len(hops) >= 3
            warning_text = "\n⚠️ **Rapid Hopping Alert:** Member switched channels 3+ times in <10s!" if is_hopping else ""

            embed = create_embed(title="🔀 Voice Room Switched", color=Colors.WARNING if is_hopping else Colors.INFO)
            embed.set_author(name=member.name, icon_url=member.display_avatar.url)
            occupants = len(after.channel.members)
            embed.description = (
                f"{member.mention} switched from **#{before.channel.name}** ➔ **#{after.channel.name}**\n"
                f"👥 **New Room Occupants:** `{occupants} member(s)`"
                f"{warning_text}"
            )
            await self._send_log(member.guild, "voice_channel_id", embed, dispatch_dm=is_hopping)

    async def _flush_role_creations(self, guild: discord.Guild) -> None:
        await asyncio.sleep(2.5)
        roles = self._role_create_buffer.pop(guild.id, [])
        self._role_create_tasks.pop(guild.id, None)
        if not roles:
            return

        if len(roles) == 1:
            name, role_id, mention = roles[0]
            embed = create_embed(
                title="🛡️ Role Created",
                description=f"Role: {mention} (`{name}` | ID: `{role_id}`)",
                color=Colors.SUCCESS,
            )
        else:
            role_lines = [f"• {mention} (`{name}` | ID: `{role_id}`)" for name, role_id, mention in roles[:15]]
            if len(roles) > 15:
                role_lines.append(f"... and {len(roles) - 15} more")
            embed = create_embed(
                title=f"🛡️ Roles Created ({len(roles)} Roles)",
                description="\n".join(role_lines),
                color=Colors.SUCCESS,
            )
        await self._send_log(guild, "general_channel_id", embed)

    async def _flush_role_deletions(self, guild: discord.Guild) -> None:
        await asyncio.sleep(2.5)
        roles = self._role_delete_buffer.pop(guild.id, [])
        self._role_delete_tasks.pop(guild.id, None)
        if not roles:
            return

        if len(roles) == 1:
            name, role_id = roles[0]
            embed = create_embed(
                title="🛡️ Role Deleted",
                description=f"Role Name: `{name}` (ID: `{role_id}`)",
                color=Colors.ERROR,
            )
        else:
            role_lines = [f"• `{name}` (ID: `{role_id}`)" for name, role_id in roles[:15]]
            if len(roles) > 15:
                role_lines.append(f"... and {len(roles) - 15} more")
            embed = create_embed(
                title=f"🛡️ Roles Deleted ({len(roles)} Roles)",
                description="\n".join(role_lines),
                color=Colors.ERROR,
            )
        await self._send_log(guild, "general_channel_id", embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        if role.managed:
            return
        guild = role.guild
        if guild.id not in self._role_create_buffer:
            self._role_create_buffer[guild.id] = []
        self._role_create_buffer[guild.id].append((role.name, role.id, role.mention))

        if guild.id in self._role_create_tasks and not self._role_create_tasks[guild.id].done():
            return
        self._role_create_tasks[guild.id] = asyncio.create_task(self._flush_role_creations(guild))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        if role.managed:
            return
        guild = role.guild
        if guild.id not in self._role_delete_buffer:
            self._role_delete_buffer[guild.id] = []
        self._role_delete_buffer[guild.id].append((role.name, role.id))

        if guild.id in self._role_delete_tasks and not self._role_delete_tasks[guild.id].done():
            return
        self._role_delete_tasks[guild.id] = asyncio.create_task(self._flush_role_deletions(guild))

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        icon = "🔊" if isinstance(channel, discord.VoiceChannel) else ("📁" if isinstance(channel, discord.CategoryChannel) else "💬")
        embed = create_embed(
            title="📁 Channel Created",
            description=f"Channel: {icon} {channel.mention} ( {channel.name} | ID: `{channel.id}` )",
            color=Colors.SUCCESS,
        )
        actor = None
        try:
            guild = channel.guild
            if guild.me.guild_permissions.view_audit_log:
                async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.channel_create):
                    if entry.target and entry.target.id == channel.id:
                        actor = entry.user
                        break
        except Exception:
            actor = None

        context = {
            "event_type": "channel_create",
            "target_id": channel.id,
            "target_name": channel.name,
            "actor": actor,
        }
        await self._send_log(channel.guild, "general_channel_id", embed, context=context)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        is_voice = isinstance(channel, discord.VoiceChannel)
        cname_low = getattr(channel, "name", "").lower()
        is_temp_room = is_voice and any(term in cname_low for term in ["room", "suite", "sanctum", "lounge", "chamber", "🔏", "➕"])

        actor = None
        try:
            guild = channel.guild
            if guild.me.guild_permissions.view_audit_log:
                async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.channel_delete):
                    if entry.target and entry.target.id == channel.id:
                        actor = entry.user
                        break
        except Exception:
            actor = None

        if is_temp_room:
            embed = create_embed(
                title="🔐 Voice Room Closed",
                description=f"Temporary voice room `#{channel.name}` (ID: `{channel.id}`) was closed.",
                color=0x1ABC9C,
            )
            context = {
                "event_type": "room_delete",
                "target_id": channel.id,
                "target_name": channel.name,
                "actor": actor,
            }
            await self._send_log(channel.guild, "voice_channel_id", embed, context=context)
            return

        icon = "🔊" if is_voice else ("📁" if isinstance(channel, discord.CategoryChannel) else "💬")
        embed = create_embed(
            title="📁 Channel Deleted",
            description=f"Channel Name: {icon} `#{channel.name}` (ID: `{channel.id}`)",
            color=Colors.ERROR,
        )
        context = {
            "event_type": "channel_delete",
            "target_id": channel.id,
            "target_name": channel.name,
            "actor": actor,
        }
        await self._send_log(channel.guild, "general_channel_id", embed, context=context)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `#{before.name}` ➔ `#{after.name}`")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append(f"**Topic:** Updated in {after.mention}")
        if not changes:
            return

        embed = create_embed(
            title="📁 Channel Updated",
            description="\n".join(changes),
            color=Colors.INFO,
        )
        context = {
            "event_type": "channel_update",
            "target_id": after.id,
            "target_name": after.name,
        }
        await self._send_log(after.guild, "general_channel_id", embed, context=context)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        embed = create_embed(
            title="🧵 Thread Created",
            description=f"Thread: {thread.mention} (`{thread.name}`)\nParent: {thread.parent.mention if thread.parent else '*Unknown*'}",
            color=Colors.SUCCESS,
        )
        context = {
            "event_type": "channel_create",
            "target_id": thread.id,
            "target_name": thread.name,
        }
        await self._send_log(thread.guild, "general_channel_id", embed, context=context)


    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @logging_group.command(name="setup", description="Configure general audit logging channel")
    @is_admin_or_owner()
    @app_commands.describe(channel="Text channel to receive all server audit logs")
    async def logging_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.update_logging_config(interaction.guild.id, general_channel_id=channel.id)
        await interaction.response.send_message(
            embed=success_embed("General Log Channel Configured", f"Logs will be sent to {channel.mention}."),
            ephemeral=True,
        )

    @logging_group.command(name="set", description="Assign a specific channel for an event category")
    @is_admin_or_owner()
    @app_commands.describe(
        category="Log category to assign",
        channel="Destination channel",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Moderation Logs", value="moderation_channel_id"),
            app_commands.Choice(name="Security Incidents", value="security_channel_id"),
            app_commands.Choice(name="AutoMod Logs", value="automod_channel_id"),
            app_commands.Choice(name="Member Joins/Leaves", value="member_channel_id"),
            app_commands.Choice(name="Message Edits/Deletions", value="message_channel_id"),
            app_commands.Choice(name="Voice State Activity", value="voice_channel_id"),
        ]
    )
    async def logging_set(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
        channel: discord.TextChannel,
    ):
        updates = {category.value: channel.id}
        await self.bot.db.update_logging_config(interaction.guild.id, **updates)
        await interaction.response.send_message(
            embed=success_embed(f"{category.name} Assigned", f"Set log destination to {channel.mention}."),
            ephemeral=True,
        )

    @logging_group.command(name="founder_dm", description="Toggle live activity DM alerts for the Founder")
    @is_admin_or_owner()
    async def logging_founder_dm(self, interaction: discord.Interaction):
        current = await self.bot.db.get_founder_activity_dm(interaction.guild.id)
        new_state = not current
        await self.bot.db.set_founder_activity_dm(interaction.guild.id, new_state)
        status_text = "**enabled** (you will receive real-time VC and channel activity in DM)" if new_state else "**disabled**"
        await interaction.response.send_message(
            embed=success_embed("Founder Live Activity Alerts", f"Founder DM activity alerts are now {status_text}."),
            ephemeral=True,
        )

    @logging_group.command(name="founder_recipient", description="Assign which user receives the live activity DMs")
    @is_admin_or_owner()
    @app_commands.describe(user="The Founder / Admin user to receive activity DMs")
    async def logging_founder_recipient(self, interaction: discord.Interaction, user: discord.User):
        await self.bot.db.set_founder_dm_recipient(interaction.guild.id, user.id)
        await interaction.response.send_message(
            embed=success_embed("Founder Alert Recipient Set", f"Live activity DMs will be sent to {user.mention} (`{user.id}`)."),
            ephemeral=True,
        )

    @logging_group.command(name="status", description="Display current logging destinations for this server")
    @is_admin_or_owner()
    async def logging_status(self, interaction: discord.Interaction):
        cfg = await self.bot.db.get_logging_config(interaction.guild.id)

        def ch_mention(cid: Optional[int]) -> str:
            if not cid:
                return "*Not Set*"
            ch = interaction.guild.get_channel(cid)
            return ch.mention if ch else f"ID: `{cid}` *(Deleted)*"

        founder_dm_enabled = await self.bot.db.get_founder_activity_dm(interaction.guild.id)
        founder_recipient_id = await self.bot.db.get_founder_dm_recipient(interaction.guild.id)
        recip_text = f"<@{founder_recipient_id}>" if founder_recipient_id else "Server Owner / Founder (Default)"

        embed = create_embed(
            title=f"📋 Logging Channel Routing — {interaction.guild.name}",
            color=Colors.INFO,
        )
        embed.add_field(name="General Logs", value=ch_mention(cfg.general_channel_id), inline=True)
        embed.add_field(name="Moderation Logs", value=ch_mention(cfg.moderation_channel_id), inline=True)
        embed.add_field(name="Security Alerts", value=ch_mention(cfg.security_channel_id), inline=True)
        embed.add_field(name="AutoMod Violations", value=ch_mention(cfg.automod_channel_id), inline=True)
        embed.add_field(name="Member Joins/Leaves", value=ch_mention(cfg.member_channel_id), inline=True)
        embed.add_field(name="Message Logs", value=ch_mention(cfg.message_channel_id), inline=True)
        embed.add_field(name="Voice Logs", value=ch_mention(cfg.voice_channel_id), inline=True)
        embed.add_field(
            name="Founder Live DM Alerts",
            value=f"{'🟢 Enabled' if founder_dm_enabled else '🔴 Disabled'} • Recipient: {recip_text}",
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(LoggingCog(bot))
