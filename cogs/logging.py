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
import datetime
import logging
import time
from typing import TYPE_CHECKING, Optional, List, Dict, Any
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner
from utils.helpers import find_audit_executor
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
    logs_group = app_commands.Group(
        name="logs",
        description="Configure server audit logging channels and separate category",
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
        fallback_map = {
            "anti_nuke_channel_id": "security_channel_id",
            "server_settings_channel_id": "server_audit_channel_id",
            "invite_logs_channel_id": "member_channel_id",
            "webhook_logs_channel_id": "channel_logs_channel_id",
            "welcome_logs_channel_id": "member_channel_id",
        }
        channel_id = getattr(cfg, channel_attr, None)
        if not channel_id and channel_attr in fallback_map:
            channel_id = getattr(cfg, fallback_map[channel_attr], None)
        if not channel_id:
            channel_id = cfg.general_channel_id

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
        guild = member.guild
        embed = create_embed(
            title="📥 Member Joined",
            description=f"{member.mention} (`{member.id}`)",
            color=Colors.SUCCESS,
            thumbnail_url=member.display_avatar.url,
        )
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Server Member Count", value=str(member.guild.member_count), inline=True)
        await self._send_log(member.guild, "member_channel_id", embed)

        if member.bot:
            bot_embed = create_embed(
                title="🤖 Bot Added to Server",
                description=f"{member.mention} (`{member.id}`)",
                color=Colors.INFO,
                thumbnail_url=member.display_avatar.url,
            )
            bot_embed.add_field(name="Bot Name", value=f"`{member.name}`", inline=True)
            bot_embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
            await self._send_log(guild, "bot_logs_channel_id", bot_embed)
        else:
            welcome_embed = create_embed(
                title="👋 Welcome Gateway Arrival",
                description=f"{member.mention} entered the server gateway.",
                color=Colors.SUCCESS,
                thumbnail_url=member.display_avatar.url,
            )
            welcome_embed.add_field(name="Member ID", value=f"`{member.id}`", inline=True)
            welcome_embed.add_field(name="Member Count", value=str(guild.member_count), inline=True)
            await self._send_log(guild, "welcome_logs_channel_id", welcome_embed)

        # Suspicious Alt Account Detection (Accounts under 7 days old)
        account_age_days = (discord.utils.utcnow() - member.created_at).days
        if account_age_days < 7 and not member.bot:
            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_security_alert(
                    self.bot,
                    guild.id,
                    event="Suspicious New Account / Potential Alt",
                    user=member,
                    severity="HIGH",
                    details={
                        "Account Age": f"`{account_age_days} day(s) old`",
                        "Created At": discord.utils.format_dt(member.created_at, "F"),
                        "Join Target": guild.name,
                        "Risk Assessment": "Account created < 7 days ago — High risk of alt or raid bypass",
                    },
                )
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Correlate with audit log to distinguish kicks from voluntary leaves
        executor, audit_entry = await find_audit_executor(
            member.guild, discord.AuditLogAction.kick, target_id=member.id, max_retries=2, delay_seconds=0.4
        )
        roles = [r.mention for r in member.roles if not r.is_default()]

        if executor and audit_entry:
            embed = create_embed(
                title="👢 Member Kicked",
                description=f"**Target:** {member.mention} (`{member.name}` | ID: `{member.id}`)",
                color=Colors.WARNING,
                thumbnail_url=member.display_avatar.url,
            )
            embed.add_field(name="Moderator", value=f"{executor.mention} (`{executor.name}`)", inline=True)
            embed.add_field(name="Reason", value=audit_entry.reason or "No reason provided", inline=True)
            if roles:
                embed.add_field(name="Roles Held", value=", ".join(roles[:15]), inline=False)
            embed.add_field(name="Server Member Count", value=str(member.guild.member_count), inline=True)
            await self._send_log(member.guild, "moderation_channel_id", embed)
            return

        embed = create_embed(
            title="📤 Member Left",
            description=f"**{member.name}** (`{member.id}`)",
            color=Colors.ERROR,
            thumbnail_url=member.display_avatar.url,
        )
        if roles:
            embed.add_field(name="Roles Held", value=", ".join(roles[:15]), inline=False)
        embed.add_field(name="Server Member Count", value=str(member.guild.member_count), inline=True)
        await self._send_log(member.guild, "member_channel_id", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        executor, audit_entry = await find_audit_executor(
            guild, discord.AuditLogAction.ban, target_id=user.id, max_retries=2, delay_seconds=0.4
        )
        embed = create_embed(
            title="🔨 Member Banned",
            description=f"**Target:** {user.mention} (`{user.name}` | ID: `{user.id}`)",
            color=Colors.ERROR,
            thumbnail_url=user.display_avatar.url if hasattr(user, "display_avatar") else None,
        )
        actor_text = f"{executor.mention} (`{executor.name}`)" if executor else "Unknown / External Integration"
        reason_text = audit_entry.reason if (audit_entry and audit_entry.reason) else "No reason specified"
        embed.add_field(name="Moderator", value=actor_text, inline=True)
        embed.add_field(name="Reason", value=reason_text, inline=True)
        await self._send_log(guild, "moderation_channel_id", embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        executor, audit_entry = await find_audit_executor(
            guild, discord.AuditLogAction.unban, target_id=user.id, max_retries=2, delay_seconds=0.4
        )
        embed = create_embed(
            title="🔓 Member Unbanned",
            description=f"**Target:** {user.mention} (`{user.name}` | ID: `{user.id}`)",
            color=Colors.SUCCESS,
            thumbnail_url=user.display_avatar.url if hasattr(user, "display_avatar") else None,
        )
        actor_text = f"{executor.mention} (`{executor.name}`)" if executor else "Unknown / External Integration"
        reason_text = audit_entry.reason if (audit_entry and audit_entry.reason) else "No reason specified"
        embed.add_field(name="Moderator", value=actor_text, inline=True)
        embed.add_field(name="Reason", value=reason_text, inline=True)
        await self._send_log(guild, "moderation_channel_id", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild = after.guild

        # 1. Timeout / Communication Disabled detection
        if before.timed_out_until != after.timed_out_until:
            now_utc = discord.utils.utcnow()
            if after.timed_out_until and after.timed_out_until > now_utc:
                executor, audit_entry = await find_audit_executor(
                    guild, discord.AuditLogAction.member_update, target_id=after.id, max_retries=2, delay_seconds=0.4
                )
                actor_text = f"{executor.mention} (`{executor.name}`)" if executor else "Staff (Uncertain Attribution)"
                reason_text = audit_entry.reason if (audit_entry and audit_entry.reason) else "No reason specified"
                embed = create_embed(
                    title="⏳ Member Timed Out",
                    description=f"{after.mention} (`{after.name}` | ID: `{after.id}`) was placed in timeout.",
                    color=Colors.WARNING,
                    thumbnail_url=after.display_avatar.url,
                )
                embed.add_field(name="Moderator", value=actor_text, inline=True)
                embed.add_field(name="Expires", value=discord.utils.format_dt(after.timed_out_until, "R"), inline=True)
                embed.add_field(name="Reason", value=reason_text, inline=False)
                await self._send_log(guild, "moderation_channel_id", embed)
            elif before.timed_out_until and (not after.timed_out_until or after.timed_out_until <= now_utc):
                executor, audit_entry = await find_audit_executor(
                    guild, discord.AuditLogAction.member_update, target_id=after.id, max_retries=2, delay_seconds=0.4
                )
                actor_text = f"{executor.mention} (`{executor.name}`)" if executor else "Staff (Uncertain Attribution)"
                embed = create_embed(
                    title="⌛ Timeout Removed",
                    description=f"{after.mention} (`{after.name}`) had their timeout removed.",
                    color=Colors.SUCCESS,
                    thumbnail_url=after.display_avatar.url,
                )
                embed.add_field(name="Moderator", value=actor_text, inline=True)
                await self._send_log(guild, "moderation_channel_id", embed)

        # 2. Nickname Changes
        if before.nick != after.nick:
            embed = create_embed(
                title="🏷️ Nickname Changed",
                description=f"**Member:** {after.mention} (`{after.id}`)",
                color=Colors.INFO,
                thumbnail_url=after.display_avatar.url,
            )
            embed.add_field(name="Before", value=before.nick or "*None (Username)*", inline=True)
            embed.add_field(name="After", value=after.nick or "*None (Reset to Username)*", inline=True)
            await self._send_log(guild, "member_channel_id", embed)

        # 3. Roles Assigned / Removed
        if set(before.roles) != set(after.roles):
            added_roles = [r for r in after.roles if r not in before.roles]
            removed_roles = [r for r in before.roles if r not in after.roles]
            if added_roles or removed_roles:
                executor, _ = await find_audit_executor(
                    guild, discord.AuditLogAction.member_role_update, target_id=after.id, max_retries=2, delay_seconds=0.4
                )
                embed = create_embed(
                    title="🛡️ Member Roles Updated",
                    description=f"**Member:** {after.mention} (`{after.id}`)",
                    color=Colors.INFO,
                    thumbnail_url=after.display_avatar.url,
                )
                if added_roles:
                    embed.add_field(name="➕ Roles Added", value=", ".join(r.mention for r in added_roles), inline=False)
                if removed_roles:
                    embed.add_field(name="➖ Roles Removed", value=", ".join(r.mention for r in removed_roles), inline=False)
                embed.add_field(
                    name="Updated By",
                    value=f"{executor.mention} (`{executor.name}`)" if executor else "Uncertain / Self-Assigned",
                    inline=True,
                )
                await self._send_log(guild, "role_logs_channel_id", embed)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if not guild:
            return
        channel = guild.get_channel(payload.channel_id)
        count = len(payload.message_ids)

        embed = create_embed(
            title="📑 Bulk Messages Purged",
            description=(
                f"**Channel:** {channel.mention if channel else f'ID: `{payload.channel_id}`'}\n"
                f"**Messages Deleted:** `{count} message(s)`\n"
                f"**Action:** Consolidated bulk deletion log (flood protection active)"
            ),
            color=Colors.ERROR,
        )
        await self._send_log(guild, "message_channel_id", embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Auto-publish messages posted in Announcement / News channels."""
        if not message.guild or message.author.bot:
            return

        if message.channel.type == discord.ChannelType.news or message.channel.id == 1545502718792175646:
            try:
                if not getattr(message.flags, "crossposted", False):
                    await message.publish()
                    logger.info("Auto-published announcement message %s in %s", message.id, message.channel.name)
                    try:
                        await message.add_reaction("📢")
                    except Exception:
                        pass
            except discord.HTTPException as e:
                logger.debug("Announcement auto-publish notice: %s", e)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Check for Ghost Ping (deleted message containing user/role/@everyone mentions)
        has_user_mentions = bool(message.mentions)
        has_role_mentions = bool(message.role_mentions)
        has_everyone = bool(message.mention_everyone)
        if has_user_mentions or has_role_mentions or has_everyone:
            targets = []
            if has_everyone:
                targets.append("@everyone / @here")
            for u in message.mentions:
                targets.append(f"{u.mention} (`{u.name}`)")
            for r in message.role_mentions:
                targets.append(f"{r.mention} (`{r.name}`)")

            ghost_embed = create_embed(
                title="👻 Ghost Ping Detected",
                description=(
                    f"**Author:** {message.author.mention} (`{message.author.id}`)\n"
                    f"**Channel:** {message.channel.mention}\n"
                    f"**Pinged Target(s):** {', '.join(targets[:8])}\n\n"
                    f"**Deleted Message Content:**\n```{message.content[:900] if message.content else '[No Text Content]'}```"
                ),
                color=Colors.ERROR,
            )
            # Route to moderation logs channel
            await self._send_log(message.guild, "moderation_channel_id", ghost_embed)

            # Send confidential mod report
            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_mod_report(
                    self.bot,
                    message.guild.id,
                    event="Ghost Ping Detected",
                    user=message.author,
                    reason=f"Message with {len(targets)} mention(s) deleted in #{message.channel.name}",
                    action_taken="Logged to moderation audit logs",
                    severity="MEDIUM",
                    details={"Channel": message.channel.mention, "Target(s)": ", ".join(targets[:5])},
                )
            except Exception:
                pass

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

    async def _get_voice_moderator(
        self, member: discord.Member, check_attribute: str, expected_val: bool
    ) -> Optional[discord.Member]:
        """Queries guild audit logs to find the moderator responsible for a voice mute or deafen action."""
        guild = member.guild
        if not guild.me.guild_permissions.view_audit_log:
            return None
        try:
            await asyncio.sleep(0.4)
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                if entry.target and entry.target.id == member.id:
                    now_utc = datetime.datetime.now(datetime.timezone.utc)
                    entry_created = getattr(entry, "created_at", now_utc)
                    if (now_utc - entry_created).total_seconds() <= 12.0:
                        if getattr(entry.after, check_attribute, None) == expected_val:
                            return entry.user
        except Exception as e:
            logger.debug(f"Audit log check for voice moderation failed: {e}")
        return None

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
                mod = await self._get_voice_moderator(member, "mute", True)
                embed = create_embed(title="⚠️ Member Server-Muted", color=Colors.WARNING)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                if mod:
                    embed.description = f"{member.mention} was **server-muted** by {mod.mention} (`{mod.display_name}`) in **#{after.channel.name}**."
                else:
                    embed.description = f"{member.mention} was **server-muted** by staff in **#{after.channel.name}**."
            elif before.mute and not after.mute and after.channel:
                mod = await self._get_voice_moderator(member, "mute", False)
                embed = create_embed(title="🎙️ Member Server-Unmuted", color=Colors.SUCCESS)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                if mod:
                    embed.description = f"{member.mention} was **server-unmuted** by {mod.mention} (`{mod.display_name}`) in **#{after.channel.name}**."
                else:
                    embed.description = f"{member.mention} was **server-unmuted** in **#{after.channel.name}**."
            elif not before.deaf and after.deaf and after.channel:
                mod = await self._get_voice_moderator(member, "deaf", True)
                embed = create_embed(title="⚠️ Member Server-Deafened", color=Colors.WARNING)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                if mod:
                    embed.description = f"{member.mention} was **server-deafened** by {mod.mention} (`{mod.display_name}`) in **#{after.channel.name}**."
                else:
                    embed.description = f"{member.mention} was **server-deafened** by staff in **#{after.channel.name}**."
            elif before.deaf and not after.deaf and after.channel:
                mod = await self._get_voice_moderator(member, "deaf", False)
                embed = create_embed(title="👂 Member Server-Undeafened", color=Colors.SUCCESS)
                embed.set_author(name=member.name, icon_url=member.display_avatar.url)
                if mod:
                    embed.description = f"{member.mention} was **server-undeafened** by {mod.mention} (`{mod.display_name}`) in **#{after.channel.name}**."
                else:
                    embed.description = f"{member.mention} was **server-undeafened** in **#{after.channel.name}**."

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
            await self._send_log(member.guild, "voice_channel_id", embed)

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
        await self._send_log(guild, "role_logs_channel_id", embed)

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
        await self._send_log(guild, "role_logs_channel_id", embed)

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
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if before.managed or after.managed:
            return
        guild = after.guild
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` ➔ `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Color:** `{before.color}` ➔ `{after.color}`")
        if before.hoist != after.hoist:
            changes.append(f"**Separately Displayed (Hoist):** `{before.hoist}` ➔ `{after.hoist}`")
        if before.mentionable != after.mentionable:
            changes.append(f"**Mentionable:** `{before.mentionable}` ➔ `{after.mentionable}`")
        if before.permissions != after.permissions:
            added_perms = [perm for perm, val in after.permissions if val and not getattr(before.permissions, perm)]
            removed_perms = [perm for perm, val in before.permissions if val and not getattr(after.permissions, perm)]
            if added_perms:
                changes.append(f"**Permissions Granted:** `+{', +'.join(added_perms[:8])}`")
            if removed_perms:
                changes.append(f"**Permissions Revoked:** `-{', -'.join(removed_perms[:8])}`")

        if not changes:
            return

        executor, _ = await find_audit_executor(
            guild, discord.AuditLogAction.role_update, target_id=after.id, max_retries=2, delay_seconds=0.4
        )
        embed = create_embed(
            title="🛡️ Role Updated",
            description=f"**Role:** {after.mention} (`{after.name}` | ID: `{after.id}`)\n\n" + "\n".join(changes),
            color=Colors.INFO,
        )
        embed.add_field(
            name="Executor",
            value=f"{executor.mention} (`{executor.name}`)" if executor else "Uncertain Attribution",
            inline=True,
        )
        await self._send_log(guild, "role_logs_channel_id", embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        icon = "🔊" if isinstance(channel, discord.VoiceChannel) else ("📁" if isinstance(channel, discord.CategoryChannel) else "💬")
        embed = create_embed(
            title="📁 Channel Created",
            description=f"Channel: {icon} {channel.mention} ( `#{channel.name}` | ID: `{channel.id}` )",
            color=Colors.SUCCESS,
        )
        executor, _ = await find_audit_executor(
            channel.guild, discord.AuditLogAction.channel_create, target_id=channel.id, max_retries=2, delay_seconds=0.4
        )
        if executor:
            embed.add_field(name="Created By", value=f"{executor.mention} (`{executor.name}`)", inline=True)

        context = {
            "event_type": "channel_create",
            "target_id": channel.id,
            "target_name": channel.name,
            "actor": executor,
        }
        await self._send_log(channel.guild, "channel_logs_channel_id", embed, context=context)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        is_voice = isinstance(channel, discord.VoiceChannel)
        cname_low = getattr(channel, "name", "").lower()
        is_temp_room = is_voice and any(term in cname_low for term in ["room", "suite", "sanctum", "lounge", "chamber", "🔏", "➕"])

        executor, _ = await find_audit_executor(
            channel.guild, discord.AuditLogAction.channel_delete, target_id=channel.id, max_retries=2, delay_seconds=0.4
        )

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
                "actor": executor,
            }
            await self._send_log(channel.guild, "voice_channel_id", embed, context=context)
            return

        icon = "🔊" if is_voice else ("📁" if isinstance(channel, discord.CategoryChannel) else "💬")
        embed = create_embed(
            title="📁 Channel Deleted",
            description=f"Channel Name: {icon} `#{channel.name}` (ID: `{channel.id}`)",
            color=Colors.ERROR,
        )
        if executor:
            embed.add_field(name="Deleted By", value=f"{executor.mention} (`{executor.name}`)", inline=True)

        context = {
            "event_type": "channel_delete",
            "target_id": channel.id,
            "target_name": channel.name,
            "actor": executor,
        }
        await self._send_log(channel.guild, "channel_logs_channel_id", embed, context=context)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `#{before.name}` ➔ `#{after.name}`")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append(f"**Topic:** Updated in {after.mention}")
        if before.overwrites != after.overwrites:
            changes.append("⚙️ **Permission Overwrites Modified**")

        if not changes:
            return

        executor, _ = await find_audit_executor(
            after.guild, discord.AuditLogAction.channel_update, target_id=after.id, max_retries=2, delay_seconds=0.4
        )
        embed = create_embed(
            title="📁 Channel Updated",
            description="\n".join(changes),
            color=Colors.INFO,
        )
        if executor:
            embed.add_field(name="Updated By", value=f"{executor.mention} (`{executor.name}`)", inline=True)

        context = {
            "event_type": "channel_update",
            "target_id": after.id,
            "target_name": after.name,
            "actor": executor,
        }
        await self._send_log(after.guild, "channel_logs_channel_id", embed, context=context)

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
        await self._send_log(thread.guild, "channel_logs_channel_id", embed, context=context)

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        executor, audit_entry = await find_audit_executor(
            guild, discord.AuditLogAction.webhook_create, max_retries=2, delay_seconds=0.4
        )
        action_name = "Webhook Created"
        if not executor:
            executor, audit_entry = await find_audit_executor(
                guild, discord.AuditLogAction.webhook_delete, max_retries=2, delay_seconds=0.4
            )
            if executor:
                action_name = "Webhook Deleted"

        embed = create_embed(
            title=f"🔗 {action_name}",
            description=f"Webhook modification detected in {channel.mention} (`#{channel.name}`).",
            color=Colors.WARNING if action_name == "Webhook Created" else Colors.INFO,
        )
        embed.add_field(
            name="Executor",
            value=f"{executor.mention} (`{executor.name}`)" if executor else "Uncertain Attribution",
            inline=True,
        )
        await self._send_log(guild, "webhook_logs_channel_id", embed)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        changes = []
        if before.name != after.name:
            changes.append(f"**Server Name:** `{before.name}` ➔ `{after.name}`")
        if before.verification_level != after.verification_level:
            changes.append(f"**Verification Level:** `{before.verification_level.name}` ➔ `{after.verification_level.name}`")
        if before.default_notifications != after.default_notifications:
            changes.append(f"**Default Notifications:** `{before.default_notifications.name}` ➔ `{after.default_notifications.name}`")
        if before.afk_channel != after.afk_channel:
            old_afk = before.afk_channel.name if before.afk_channel else "None"
            new_afk = after.afk_channel.name if after.afk_channel else "None"
            changes.append(f"**AFK Channel:** `#{old_afk}` ➔ `#{new_afk}`")
        if before.afk_timeout != after.afk_timeout:
            changes.append(f"**AFK Timeout:** `{before.afk_timeout}s` ➔ `{after.afk_timeout}s`")

        if not changes:
            return

        executor, _ = await find_audit_executor(
            after, discord.AuditLogAction.guild_update, max_retries=2, delay_seconds=0.4
        )
        embed = create_embed(
            title="⚙️ Server Settings Modified",
            description="\n".join(changes),
            color=Colors.PRIMARY,
        )
        if executor:
            embed.add_field(name="Modified By", value=f"{executor.mention} (`{executor.name}`)", inline=True)
        await self._send_log(after, "server_settings_channel_id", embed)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if not invite.guild or not isinstance(invite.guild, discord.Guild):
            return
        inviter_str = f"{invite.inviter.mention} (`{invite.inviter.name}`)" if invite.inviter else "Unknown Inviter"
        channel_str = invite.channel.mention if hasattr(invite, "channel") and invite.channel else "Unknown"
        max_uses_str = str(invite.max_uses) if invite.max_uses else "Unlimited"
        expires_str = discord.utils.format_dt(discord.utils.utcnow() + datetime.timedelta(seconds=invite.max_age), "R") if invite.max_age else "Never"

        embed = create_embed(
            title="🎟️ Invite Created",
            description=f"New invite link generated: **`{invite.code}`**",
            color=Colors.SUCCESS,
        )
        embed.add_field(name="Creator", value=inviter_str, inline=True)
        embed.add_field(name="Channel", value=channel_str, inline=True)
        embed.add_field(name="Max Uses", value=max_uses_str, inline=True)
        embed.add_field(name="Expires", value=expires_str, inline=True)
        if invite.temporary:
            embed.add_field(name="Temporary Membership", value="Yes", inline=True)
        await self._send_log(invite.guild, "invite_logs_channel_id", embed)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if not invite.guild or not isinstance(invite.guild, discord.Guild):
            return
        channel_str = invite.channel.mention if hasattr(invite, "channel") and invite.channel else "Unknown"
        embed = create_embed(
            title="🎟️ Invite Deleted / Revoked",
            description=f"Invite link removed: **`{invite.code}`**",
            color=Colors.WARNING,
        )
        embed.add_field(name="Target Channel", value=channel_str, inline=True)
        await self._send_log(invite.guild, "invite_logs_channel_id", embed)


    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    LOG_CHANNEL_SPECS = [
        ("member-logs", "member_channel_id", "Member joins, leaves, and nickname updates"),
        ("message-logs", "message_channel_id", "Message edits, deletions, and bulk purges"),
        ("moderation-logs", "moderation_channel_id", "Moderation actions, bans, kicks, timeouts"),
        ("security-logs", "security_channel_id", "Security alerts and threat analysis"),
        ("anti-nuke-logs", "anti_nuke_channel_id", "High-speed anti-nuke detections and automated containment"),
        ("automod-logs", "automod_channel_id", "AutoMod link, spam, mention, and keyword interceptions"),
        ("role-logs", "role_logs_channel_id", "Role creation, deletion, and role permission updates"),
        ("channel-logs", "channel_logs_channel_id", "Channel creation, deletion, and permission updates"),
        ("voice-logs", "voice_channel_id", "Voice connections, disconnections, and state changes"),
        ("server-settings-logs", "server_settings_channel_id", "Server setting adjustments and configuration changes"),
        ("invite-logs", "invite_logs_channel_id", "Invite creations, deletions, and vanity URL changes"),
        ("webhook-logs", "webhook_logs_channel_id", "Webhook creations, deletions, and payload abuse"),
        ("bot-logs", "bot_logs_channel_id", "Bot additions, integration modifications, and commands"),
        ("welcome-logs", "welcome_logs_channel_id", "Welcome gateway arrivals, screening, and onboarding"),
    ]

    @logging_group.command(name="setup", description="Configure general audit logging channel")
    @is_admin_or_owner()
    @app_commands.describe(channel="Text channel to receive all server audit logs")
    async def logging_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.update_logging_config(interaction.guild.id, general_channel_id=channel.id)
        await interaction.response.send_message(
            embed=success_embed("General Log Channel Configured", f"Default logs will be sent to {channel.mention}."),
            ephemeral=True,
        )

    @logging_group.command(name="auto_setup", description="Automatically provision or link all 15 centralized audit channels")
    @is_admin_or_owner()
    @app_commands.describe(category_name="Optional category name for audit logs (default: 📜 | AUDIT & LOGS)")
    async def logging_auto_setup(self, interaction: discord.Interaction, category_name: Optional[str] = "📜 | AUDIT & LOGS"):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        if not guild.me.guild_permissions.manage_channels:
            await interaction.followup.send(
                embed=error_embed("Missing Permissions", "Bot requires `Manage Channels` permission to auto-setup logging channels."),
                ephemeral=True,
            )
            return

        # 1. Locate or create parent category
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, attach_files=True),
                }
                category = await guild.create_category(name=category_name, overwrites=overwrites)
            except Exception as e:
                await interaction.followup.send(
                    embed=error_embed("Category Creation Failed", f"Could not create category `{category_name}`: {e}"),
                    ephemeral=True,
                )
                return

        # 2. Map existing channels or create missing ones (reusing existing to avoid duplicates)
        updates = {}
        report_lines = []

        cfg = await self.bot.db.get_logging_config(guild.id)

        for c_name, attr_name, desc in self.LOG_CHANNEL_SPECS:
            existing_id = getattr(cfg, attr_name, None)
            target_ch = guild.get_channel(existing_id) if existing_id else None

            # Fallback: check if a channel with matching name already exists in guild
            if not target_ch:
                target_ch = discord.utils.get(guild.text_channels, name=c_name)

            if target_ch:
                updates[attr_name] = target_ch.id
                report_lines.append(f"• **{c_name}**: {target_ch.mention} *(Linked existing)*")
            else:
                try:
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
                        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, attach_files=True),
                    }
                    new_ch = await guild.create_text_channel(
                        name=c_name,
                        category=category,
                        overwrites=overwrites,
                        topic=f"Rai Centralized Logging • {desc}",
                    )
                    updates[attr_name] = new_ch.id
                    report_lines.append(f"• **{c_name}**: {new_ch.mention} *(Created)*")
                    await asyncio.sleep(0.4)
                except Exception as ce:
                    report_lines.append(f"• **{c_name}**: ⚠️ Creation failed ({ce})")

        if updates:
            await self.bot.db.update_logging_config(guild.id, **updates)

        embed = create_embed(
            title="🛡️ Centralized Logging System Initialized",
            description=(
                f"Configured **{len(updates)}** dedicated audit channels under **{category.name}**.\n\n"
                + "\n".join(report_lines[:15])
            ),
            color=Colors.SUCCESS,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @logging_group.command(name="set", description="Assign a specific channel for an event category")
    @is_admin_or_owner()
    @app_commands.describe(
        category="Log category to assign",
        channel="Destination channel",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Moderation Logs (#mod-logs)", value="moderation_channel_id"),
            app_commands.Choice(name="Security Incidents (#security-logs)", value="security_channel_id"),
            app_commands.Choice(name="AutoMod Logs (#automod-logs)", value="automod_channel_id"),
            app_commands.Choice(name="Member Joins/Leaves (#member-logs)", value="member_channel_id"),
            app_commands.Choice(name="Message Edits/Deletions (#message-logs)", value="message_channel_id"),
            app_commands.Choice(name="Voice State Activity (#voice-logs)", value="voice_channel_id"),
            app_commands.Choice(name="Channel Updates (#channel-logs)", value="channel_logs_channel_id"),
            app_commands.Choice(name="Role Updates (#role-logs)", value="role_logs_channel_id"),
            app_commands.Choice(name="Server Audit Logs (#server-audit-logs)", value="server_audit_channel_id"),
            app_commands.Choice(name="Backup Logs (#backup-logs)", value="backup_logs_channel_id"),
            app_commands.Choice(name="Report Logs (#report-logs)", value="report_logs_channel_id"),
            app_commands.Choice(name="Ticket Logs (#ticket-logs)", value="ticket_logs_channel_id"),
            app_commands.Choice(name="Staff Logs (#staff-logs)", value="staff_logs_channel_id"),
            app_commands.Choice(name="Bot Logs (#bot-logs)", value="bot_logs_channel_id"),
            app_commands.Choice(name="Error Logs (#error-logs)", value="error_logs_channel_id"),
            app_commands.Choice(name="System Status (#system-status)", value="system_status_channel_id"),
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
            title=f"📋 Centralized Logging Routing — {interaction.guild.name}",
            description="Status of all 15 dedicated server audit channels:",
            color=Colors.INFO,
        )
        embed.add_field(name="General Logs", value=ch_mention(cfg.general_channel_id), inline=True)
        embed.add_field(name="Moderation Logs", value=ch_mention(cfg.moderation_channel_id), inline=True)
        embed.add_field(name="Security Alerts", value=ch_mention(cfg.security_channel_id), inline=True)
        embed.add_field(name="AutoMod Logs", value=ch_mention(cfg.automod_channel_id), inline=True)
        embed.add_field(name="Member Logs", value=ch_mention(cfg.member_channel_id), inline=True)
        embed.add_field(name="Message Logs", value=ch_mention(cfg.message_channel_id), inline=True)
        embed.add_field(name="Voice Logs", value=ch_mention(cfg.voice_channel_id), inline=True)
        embed.add_field(name="Channel Logs", value=ch_mention(cfg.channel_logs_channel_id), inline=True)
        embed.add_field(name="Role Logs", value=ch_mention(cfg.role_logs_channel_id), inline=True)
        embed.add_field(name="Server Audit Logs", value=ch_mention(cfg.server_audit_channel_id), inline=True)
        embed.add_field(name="Backup Logs", value=ch_mention(cfg.backup_logs_channel_id), inline=True)
        embed.add_field(name="Report Logs", value=ch_mention(cfg.report_logs_channel_id), inline=True)
        embed.add_field(name="Ticket Logs", value=ch_mention(cfg.ticket_logs_channel_id), inline=True)
        embed.add_field(name="Staff Logs", value=ch_mention(cfg.staff_logs_channel_id), inline=True)
        embed.add_field(name="Bot Logs", value=ch_mention(cfg.bot_logs_channel_id), inline=True)
        embed.add_field(name="Error Logs", value=ch_mention(cfg.error_logs_channel_id), inline=True)
        embed.add_field(name="System Status", value=ch_mention(cfg.system_status_channel_id), inline=True)
        embed.add_field(
            name="Founder Live DM Alerts",
            value=f"{'🟢 Enabled' if founder_dm_enabled else '🔴 Disabled'} • Recipient: {recip_text}",
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # /LOGS COMMAND GROUP (MODULE 4)
    # ==========================================

    @logs_group.command(name="setup", description="Provision or link 📁 SERVER LOGS category and all 14 separate channels")
    @is_admin_or_owner()
    @app_commands.describe(category_name="Optional custom category name (defaults to 📁 SERVER LOGS)")
    async def logs_setup(self, interaction: discord.Interaction, category_name: Optional[str] = "📁 SERVER LOGS"):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        if not guild.me.guild_permissions.manage_channels:
            await interaction.followup.send(
                embed=error_embed("Missing Permissions", "Bot requires `Manage Channels` permission to auto-setup logging channels."),
                ephemeral=True,
            )
            return

        cat_target_name = (category_name or "📁 SERVER LOGS").strip()
        category = discord.utils.get(guild.categories, name=cat_target_name)
        if not category:
            for cat in guild.categories:
                if "server logs" in cat.name.lower() or "server-logs" in cat.name.lower():
                    category = cat
                    break

        if not category:
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, attach_files=True),
                }
                category = await guild.create_category(name=cat_target_name, overwrites=overwrites)
            except Exception as e:
                await interaction.followup.send(
                    embed=error_embed("Category Creation Failed", f"Could not create category `{cat_target_name}`: {e}"),
                    ephemeral=True,
                )
                return

        updates = {}
        report_lines = []
        cfg = await self.bot.db.get_logging_config(guild.id)

        for c_name, attr_name, desc in self.LOG_CHANNEL_SPECS:
            existing_id = getattr(cfg, attr_name, None)
            target_ch = guild.get_channel(existing_id) if existing_id else None

            # Fallback 1: check inside category
            if not target_ch and category:
                target_ch = discord.utils.get(category.text_channels, name=c_name)

            # Fallback 2: check whole guild by name
            if not target_ch:
                target_ch = discord.utils.get(guild.text_channels, name=c_name)

            if target_ch:
                updates[attr_name] = target_ch.id
                report_lines.append(f"• **#{c_name}**: {target_ch.mention} *(Linked existing)*")
            else:
                try:
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
                        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, attach_files=True),
                    }
                    new_ch = await guild.create_text_channel(
                        name=c_name,
                        category=category,
                        overwrites=overwrites,
                        topic=f"Rai Centralized Audit • {desc}",
                    )
                    updates[attr_name] = new_ch.id
                    report_lines.append(f"• **#{c_name}**: {new_ch.mention} *(Created)*")
                    await asyncio.sleep(0.35)
                except Exception as ce:
                    report_lines.append(f"• **#{c_name}**: ⚠️ Creation error ({ce})")

        if updates:
            await self.bot.db.update_logging_config(guild.id, **updates)

        embed = create_embed(
            title=f"📁 SERVER LOGS Initialized — {guild.name}",
            description=(
                f"Configured **{len(updates)}** dedicated audit channels under **{category.name}** without duplicates.\n\n"
                + "\n".join(report_lines)
            ),
            color=Colors.SUCCESS,
        )
        embed.set_footer(text="Idempotent Setup Verified • All 14 log categories armed")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @logs_group.command(name="status", description="Display full status of all 14 dedicated log channels")
    @is_admin_or_owner()
    async def logs_status(self, interaction: discord.Interaction):
        await self.logging_status.callback(self, interaction)

    @logs_group.command(name="configure", description="Assign or redirect a specific log category to a channel")
    @is_admin_or_owner()
    @app_commands.describe(
        category="Log category to redirect",
        channel="Destination channel",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="#member-logs (Joins, leaves, profiles)", value="member_channel_id"),
            app_commands.Choice(name="#message-logs (Edits, deletes, purges)", value="message_channel_id"),
            app_commands.Choice(name="#moderation-logs (Bans, kicks, timeouts)", value="moderation_channel_id"),
            app_commands.Choice(name="#security-logs (Threats, alerts)", value="security_channel_id"),
            app_commands.Choice(name="#anti-nuke-logs (Anti-nuke containment)", value="anti_nuke_channel_id"),
            app_commands.Choice(name="#automod-logs (Chat filter triggers)", value="automod_channel_id"),
            app_commands.Choice(name="#role-logs (Role modifications)", value="role_logs_channel_id"),
            app_commands.Choice(name="#channel-logs (Channel updates)", value="channel_logs_channel_id"),
            app_commands.Choice(name="#voice-logs (Voice connections/moves)", value="voice_channel_id"),
            app_commands.Choice(name="#server-settings-logs (Guild updates)", value="server_settings_channel_id"),
            app_commands.Choice(name="#invite-logs (Invite creates/deletes)", value="invite_logs_channel_id"),
            app_commands.Choice(name="#webhook-logs (Webhook activity)", value="webhook_logs_channel_id"),
            app_commands.Choice(name="#bot-logs (Bot additions/commands)", value="bot_logs_channel_id"),
            app_commands.Choice(name="#welcome-logs (Gateway arrivals)", value="welcome_logs_channel_id"),
        ]
    )
    async def logs_configure(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
        channel: discord.TextChannel,
    ):
        updates = {category.value: channel.id}
        await self.bot.db.update_logging_config(interaction.guild.id, **updates)
        await interaction.response.send_message(
            embed=success_embed(f"{category.name} Assigned", f"Successfully redirected log destination to {channel.mention}."),
            ephemeral=True,
        )

    @logs_group.command(name="test", description="Send test diagnostics to configured log channels")
    @is_admin_or_owner()
    @app_commands.describe(category="Optionally test a single category, or leave blank to test all")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="#member-logs", value="member_channel_id"),
            app_commands.Choice(name="#message-logs", value="message_channel_id"),
            app_commands.Choice(name="#moderation-logs", value="moderation_channel_id"),
            app_commands.Choice(name="#security-logs", value="security_channel_id"),
            app_commands.Choice(name="#anti-nuke-logs", value="anti_nuke_channel_id"),
            app_commands.Choice(name="#automod-logs", value="automod_channel_id"),
            app_commands.Choice(name="#role-logs", value="role_logs_channel_id"),
            app_commands.Choice(name="#channel-logs", value="channel_logs_channel_id"),
            app_commands.Choice(name="#voice-logs", value="voice_channel_id"),
            app_commands.Choice(name="#server-settings-logs", value="server_settings_channel_id"),
            app_commands.Choice(name="#invite-logs", value="invite_logs_channel_id"),
            app_commands.Choice(name="#webhook-logs", value="webhook_logs_channel_id"),
            app_commands.Choice(name="#bot-logs", value="bot_logs_channel_id"),
            app_commands.Choice(name="#welcome-logs", value="welcome_logs_channel_id"),
        ]
    )
    async def logs_test(self, interaction: discord.Interaction, category: Optional[app_commands.Choice[str]] = None):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        cfg = await self.bot.db.get_logging_config(guild.id)

        targets = [(category.name, category.value)] if category else [
            (c_name, attr) for c_name, attr, _ in self.LOG_CHANNEL_SPECS
        ]

        success_count = 0
        failure_count = 0
        results = []

        for name, attr in targets:
            cid = getattr(cfg, attr, None)
            ch = guild.get_channel(cid) if cid else None
            if not ch or not isinstance(ch, discord.TextChannel):
                results.append(f"• **{name}**: ⚠️ *Channel not configured or deleted*")
                failure_count += 1
                continue

            test_embed = create_embed(
                title=f"🧪 Logging Diagnostic Test — {name}",
                description=f"This is an automated verification test initiated by {interaction.user.mention}.",
                color=Colors.SUCCESS,
            )
            test_embed.add_field(name="Channel Verified", value=ch.mention, inline=True)
            test_embed.add_field(name="Timestamp", value=discord.utils.format_dt(discord.utils.utcnow(), "T"), inline=True)
            test_embed.set_footer(text="Rai Diagnostic Self-Test • Channel Health Operational")

            try:
                await ch.send(embed=test_embed)
                results.append(f"• **{name}**: ✅ {ch.mention} *(Sent successfully)*")
                success_count += 1
            except Exception as e:
                results.append(f"• **{name}**: ❌ {ch.mention} *(Failed: {e})*")
                failure_count += 1

        embed = create_embed(
            title=f"🧪 Logging Diagnostics Results ({success_count}/{len(targets)} OK)",
            description="\n".join(results[:15]),
            color=Colors.SUCCESS if failure_count == 0 else Colors.WARNING,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @logs_group.command(name="disable", description="Disable logging for a specific category or all categories")
    @is_admin_or_owner()
    @app_commands.describe(category="Category to disable (leave blank to disable all)")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="#member-logs", value="member_channel_id"),
            app_commands.Choice(name="#message-logs", value="message_channel_id"),
            app_commands.Choice(name="#moderation-logs", value="moderation_channel_id"),
            app_commands.Choice(name="#security-logs", value="security_channel_id"),
            app_commands.Choice(name="#anti-nuke-logs", value="anti_nuke_channel_id"),
            app_commands.Choice(name="#automod-logs", value="automod_channel_id"),
            app_commands.Choice(name="#role-logs", value="role_logs_channel_id"),
            app_commands.Choice(name="#channel-logs", value="channel_logs_channel_id"),
            app_commands.Choice(name="#voice-logs", value="voice_channel_id"),
            app_commands.Choice(name="#server-settings-logs", value="server_settings_channel_id"),
            app_commands.Choice(name="#invite-logs", value="invite_logs_channel_id"),
            app_commands.Choice(name="#webhook-logs", value="webhook_logs_channel_id"),
            app_commands.Choice(name="#bot-logs", value="bot_logs_channel_id"),
            app_commands.Choice(name="#welcome-logs", value="welcome_logs_channel_id"),
        ]
    )
    async def logs_disable(self, interaction: discord.Interaction, category: Optional[app_commands.Choice[str]] = None):
        if category:
            updates = {category.value: None}
            await self.bot.db.update_logging_config(interaction.guild.id, **updates)
            await interaction.response.send_message(embed=success_embed(f"Disabled {category.name}", "This log category has been unassigned."), ephemeral=True)
        else:
            all_attrs = {attr: None for _, attr, _ in self.LOG_CHANNEL_SPECS}
            await self.bot.db.update_logging_config(interaction.guild.id, **all_attrs)
            await interaction.response.send_message(embed=success_embed("All Logging Disabled", "All 14 log channel destinations have been unassigned."), ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(LoggingCog(bot))
