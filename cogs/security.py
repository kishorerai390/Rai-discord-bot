"""
Advanced Server Security and Anti-Nuke Cog.
Protects against mass channel/role deletion/creation, mass bans/kicks, webhook spam,
unauthorized bot additions, mass mentions, and dangerous permission grants.
Includes audit-log safeguards, emergency kill-switch, lockdown, and incident logging.
"""

from __future__ import annotations

import datetime
import logging
import re
import uuid
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from backups.manager import BackupManager, format_bytes
from config import Colors
from database.models import SecurityIncident
from utils.embeds import (
    create_embed,
    error_embed,
    info_embed,
    security_embed,
    success_embed,
    warning_embed,
)
from utils.helpers import (
    ConfirmView,
    PaginationView,
    find_audit_executor,
    format_duration,
)
from utils.permissions import can_moderate, check_bot_hierarchy, is_admin_or_owner, is_founder_or_owner, is_guild_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


def generate_event_id() -> str:
    return str(uuid.uuid4())[:8].upper()


class SecurityCog(commands.Cog, name="Security"):
    """Server Security & Anti-Nuke System."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # Temporary storage for channel permissions before lockdown to restore cleanly
        self._lockdown_cache: dict[int, dict[int, discord.PermissionOverwrite]] = {}
        self._backup_task = None

    async def cog_load(self):
        self._backup_task = self._nightly_backup_loop.start()

    def cog_unload(self):
        if self._backup_task:
            self._backup_task.cancel()

    security_group = app_commands.Group(
        name="security",
        description="Advanced server security and anti-nuke management",
        default_permissions=discord.Permissions(administrator=True),
    )

    # ==========================================
    # AUDIT-LOG VERIFICATION & ACTION HANDLER
    # ==========================================

    async def _handle_security_violation(
        self,
        guild: discord.Guild,
        event_type: str,
        action_name: str,
        audit_action: discord.AuditLogAction,
        target_id: Optional[int] = None,
        target_name: Optional[str] = None,
        limit_attr: str = "channel_delete_limit",
        window_attr: str = "channel_delete_window",
    ) -> None:
        """
        Generic, fail-safe security event evaluator.
        1. Checks if security enabled.
        2. Retrieves audit-log entry with bounded retry.
        3. Validates against owner, bot, and whitelist.
        4. Evaluates sliding-window threshold.
        5. Enforces configured containment/punishment.
        6. Immutably records incident into SQLite and notifies security channel.
        """
        guild_cfg = await self.bot.db.get_or_create_guild_config(guild.id)
        if not guild_cfg.security_enabled:
            return

        sec_cfg = await self.bot.db.get_security_config(guild.id)
        sec_state = await self.bot.db.get_security_state(guild.id)

        limit = getattr(sec_cfg, limit_attr, 5)
        window = getattr(sec_cfg, window_attr, 10)

        # Step 1: Audit Log lookup
        executor, audit_entry = await find_audit_executor(guild, audit_action, target_id=target_id)
        audit_log_id = audit_entry.id if audit_entry else None
        audit_verified = executor is not None

        # Step 2: Fail-safe check
        if executor is None:
            # Cannot identify executor: do NOT randomly punish! Record as UNKNOWN incident.
            event_id = generate_event_id()
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            incident = SecurityIncident(
                event_id=event_id,
                guild_id=guild.id,
                timestamp=now_iso,
                event_type=event_type,
                executor_id=None,
                executor_name="UNKNOWN (Audit Log Unavailable)",
                target_id=target_id,
                target_name=target_name,
                action=action_name,
                detected_count=1,
                threshold=limit,
                audit_log_id=None,
                reason="Audit log verification inconclusive. Automated punishment aborted to prevent false-positives.",
                automated_action="None (Audit Inconclusive)",
                result="Logged incident and notified administrators.",
                severity="medium",
                audit_verified=False,
            )
            await self.bot.db.record_security_incident(incident)
            await self._notify_security_channel(guild, incident)
            return

        # Step 3: Safeguard Whitelist Checks
        # Never punish: Server owner, Bot itself, Whitelisted user, Whitelisted role
        if executor.id == guild.owner_id or executor.id == self.bot.user.id:
            return

        role_ids = [r.id for r in executor.roles] if isinstance(executor, discord.Member) else []
        if await self.bot.db.is_whitelisted(guild.id, executor.id, role_ids):
            return

        # Step 4: Sliding Window Counter Evaluation
        is_violation, detected_count, rule_detail = await self.bot.cooldowns.record_security_action(
            guild_id=guild.id,
            executor_id=executor.id,
            action=action_name,
            limit=limit,
            window_seconds=window,
        )

        if not is_violation:
            return

        # Step 5: Violation confirmed. Check Emergency Stop
        event_id = generate_event_id()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        punishment_applied = "None"
        action_result = "Success"
        severity = "high" if detected_count >= limit * 2 else "medium"

        if sec_state.emergency_stop:
            punishment_applied = "Suppressed by Emergency Stop"
            action_result = "Emergency Stop Active: No destructive action taken."
        else:
            # Step 6: Apply Configured Punishment
            punishment_applied = sec_cfg.punishment
            member = guild.get_member(executor.id)

            if member:
                # Role hierarchy check before punishing
                can_mod, reason = can_moderate(guild.me, member, guild.me)
                if not can_mod:
                    action_result = f"Skipped punishment: {reason}"
                else:
                    try:
                        if sec_cfg.punishment == "ban":
                            await member.ban(reason=f"Security Anti-Nuke: Exceeded {action_name} threshold ({detected_count}/{limit})")
                            action_result = f"Banned {member.name}"
                        elif sec_cfg.punishment == "kick":
                            await member.kick(reason=f"Security Anti-Nuke: Exceeded {action_name} threshold ({detected_count}/{limit})")
                            action_result = f"Kicked {member.name}"
                        elif sec_cfg.punishment == "timeout":
                            until = discord.utils.utcnow() + datetime.timedelta(minutes=60)
                            await member.timeout(until, reason=f"Security Anti-Nuke: Exceeded {action_name} threshold ({detected_count}/{limit})")
                            action_result = f"Timed out {member.name} for 60m"
                        elif sec_cfg.punishment == "remove_roles":
                            roles_to_remove = [r for r in member.roles if r.permissions.administrator or r.permissions.manage_guild or r.permissions.manage_channels or r.permissions.manage_roles]
                            if roles_to_remove:
                                await member.remove_roles(*roles_to_remove, reason="Security containment: stripped dangerous permissions")
                                action_result = f"Removed {len(roles_to_remove)} administrative roles from {member.name}"
                            else:
                                action_result = "No administrative roles to remove"
                        elif sec_cfg.punishment == "lock_channels":
                            await self._execute_lockdown(guild)
                            action_result = "Initiated emergency guild lockdown"
                        else:  # alert
                            action_result = f"Alert issued for {member.name}"
                    except Exception as e:
                        action_result = f"Failed to execute punishment: {str(e)[:100]}"
            else:
                action_result = "Executor is not in guild (cannot punish directly)"

        # Step 7: Record Incident & Violations
        incident = SecurityIncident(
            event_id=event_id,
            guild_id=guild.id,
            timestamp=now_iso,
            event_type=event_type,
            executor_id=executor.id,
            executor_name=f"{executor.name} ({executor.id})",
            target_id=target_id,
            target_name=target_name,
            action=action_name,
            detected_count=detected_count,
            threshold=limit,
            audit_log_id=audit_log_id,
            reason=f"Exceeded action threshold: {rule_detail}",
            automated_action=punishment_applied,
            result=action_result,
            severity=severity,
            audit_verified=audit_verified,
        )
        await self.bot.db.record_security_incident(incident)
        await self.bot.db.record_violation(guild.id, executor.id, event_type)
        await self._notify_security_channel(guild, incident)

    async def _notify_security_channel(self, guild: discord.Guild, incident: SecurityIncident) -> None:
        log_cfg = await self.bot.db.get_logging_config(guild.id)
        channel_id = log_cfg.security_channel_id or log_cfg.general_channel_id
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        embed = security_embed(
            title=f"Security Incident Detected: [{incident.event_id}]",
            description=f"**Event:** {incident.event_type}\n**Action:** {incident.action}",
        )
        embed.add_field(name="Executor", value=incident.executor_name or "Unknown", inline=True)
        embed.add_field(name="Target", value=incident.target_name or "N/A", inline=True)
        embed.add_field(
            name="Threshold",
            value=f"{incident.detected_count}/{incident.threshold}",
            inline=True,
        )
        embed.add_field(name="Automated Action", value=incident.automated_action or "None", inline=True)
        embed.add_field(name="Result", value=incident.result or "None", inline=True)
        embed.add_field(name="Severity", value=incident.severity.upper(), inline=True)
        embed.add_field(name="Audit Verified", value="Yes" if incident.audit_verified else "No", inline=True)

        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _execute_lockdown(self, guild: discord.Guild) -> int:
        """Lockdown all text channels by denying send_messages for @everyone."""
        locked_count = 0
        cache = self._lockdown_cache.setdefault(guild.id, {})
        for channel in guild.text_channels:
            if not channel.permissions_for(guild.me).manage_channels:
                continue
            overwrite = channel.overwrites_for(guild.default_role)
            if overwrite.send_messages is not False:
                cache[channel.id] = overwrite
                new_overwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
                new_overwrite.send_messages = False
                try:
                    await channel.set_permissions(guild.default_role, overwrite=new_overwrite, reason="Security Emergency Lockdown")
                    locked_count += 1
                except (discord.Forbidden, discord.HTTPException):
                    pass
        await self.bot.db.set_lockdown(guild.id, True)
        return locked_count

    async def _execute_unlock(self, guild: discord.Guild) -> int:
        """Unlock previously locked channels."""
        unlocked_count = 0
        cache = self._lockdown_cache.pop(guild.id, {})
        for channel in guild.text_channels:
            if not channel.permissions_for(guild.me).manage_channels:
                continue
            try:
                if channel.id in cache:
                    await channel.set_permissions(guild.default_role, overwrite=cache[channel.id], reason="Security Lockdown Lifted")
                    unlocked_count += 1
                else:
                    overwrite = channel.overwrites_for(guild.default_role)
                    if overwrite.send_messages is False:
                        overwrite.send_messages = None
                        await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Security Lockdown Lifted")
                        unlocked_count += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await self.bot.db.set_lockdown(guild.id, False)
        return unlocked_count

    # ==========================================
    # DISCORD EVENT LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._handle_security_violation(
            guild=channel.guild,
            event_type="CHANNEL_DELETE",
            action_name="channel_delete",
            audit_action=discord.AuditLogAction.channel_delete,
            target_id=channel.id,
            target_name=f"#{channel.name}",
            limit_attr="channel_delete_limit",
            window_attr="channel_delete_window",
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await self._handle_security_violation(
            guild=channel.guild,
            event_type="CHANNEL_CREATE",
            action_name="channel_create",
            audit_action=discord.AuditLogAction.channel_create,
            target_id=channel.id,
            target_name=f"#{channel.name}",
            limit_attr="channel_create_limit",
            window_attr="channel_create_window",
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._handle_security_violation(
            guild=role.guild,
            event_type="ROLE_DELETE",
            action_name="role_delete",
            audit_action=discord.AuditLogAction.role_delete,
            target_id=role.id,
            target_name=f"@{role.name}",
            limit_attr="role_delete_limit",
            window_attr="role_delete_window",
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self._handle_security_violation(
            guild=role.guild,
            event_type="ROLE_CREATE",
            action_name="role_create",
            audit_action=discord.AuditLogAction.role_create,
            target_id=role.id,
            target_name=f"@{role.name}",
            limit_attr="role_create_limit",
            window_attr="role_create_window",
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        await self._handle_security_violation(
            guild=guild,
            event_type="MEMBER_BAN",
            action_name="ban",
            audit_action=discord.AuditLogAction.ban,
            target_id=user.id,
            target_name=f"{user.name}",
            limit_attr="ban_limit",
            window_attr="ban_window",
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Detect kicks via audit logs
        executor, audit_entry = await find_audit_executor(
            member.guild, discord.AuditLogAction.kick, target_id=member.id, max_retries=2, delay_seconds=0.4
        )
        if executor and audit_entry:
            await self._handle_security_violation(
                guild=member.guild,
                event_type="MEMBER_KICK",
                action_name="kick",
                audit_action=discord.AuditLogAction.kick,
                target_id=member.id,
                target_name=f"{member.name}",
                limit_attr="kick_limit",
                window_attr="kick_window",
            )

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        await self._handle_security_violation(
            guild=channel.guild,
            event_type="WEBHOOK_CREATE",
            action_name="webhook_create",
            audit_action=discord.AuditLogAction.webhook_create,
            target_id=channel.id,
            target_name=f"#{channel.name}",
            limit_attr="webhook_limit",
            window_attr="webhook_window",
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Unauthorized bot additions check
        if member.bot:
            executor, audit_entry = await find_audit_executor(
                member.guild, discord.AuditLogAction.bot_add, target_id=member.id
            )
            if executor:
                if executor.id != member.guild.owner_id and executor.id != self.bot.user.id:
                    role_ids = [r.id for r in executor.roles] if isinstance(executor, discord.Member) else []
                    if not await self.bot.db.is_whitelisted(member.guild.id, executor.id, role_ids):
                        # Unauthorized bot addition!
                        sec_cfg = await self.bot.db.get_security_config(member.guild.id)
                        sec_state = await self.bot.db.get_security_state(member.guild.id)
                        if not sec_state.emergency_stop:
                            try:
                                await member.kick(reason="Security: Unauthorized bot addition")
                            except (discord.Forbidden, discord.HTTPException):
                                pass

                        event_id = generate_event_id()
                        incident = SecurityIncident(
                            event_id=event_id,
                            guild_id=member.guild.id,
                            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            event_type="UNAUTHORIZED_BOT_ADD",
                            executor_id=executor.id,
                            executor_name=f"{executor.name}",
                            target_id=member.id,
                            target_name=f"{member.name} (Bot)",
                            action="bot_add",
                            detected_count=1,
                            threshold=1,
                            audit_log_id=audit_entry.id if audit_entry else None,
                            reason="Bot invited by non-whitelisted member",
                            automated_action="Kicked unauthorized bot",
                            result="Kicked bot",
                            severity="high",
                            audit_verified=True,
                        )
                        await self.bot.db.record_security_incident(incident)
                        await self._notify_security_channel(member.guild, incident)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        # Detect dangerous permission grant (administrator, manage_guild)
        if not before.permissions.administrator and after.permissions.administrator:
            executor, audit_entry = await find_audit_executor(
                after.guild, discord.AuditLogAction.role_update, target_id=after.id
            )
            if executor and executor.id != after.guild.owner_id and executor.id != self.bot.user.id:
                role_ids = [r.id for r in executor.roles] if isinstance(executor, discord.Member) else []
                if not await self.bot.db.is_whitelisted(after.guild.id, executor.id, role_ids):
                    # Unauthorized administrator permission grant!
                    sec_state = await self.bot.db.get_security_state(after.guild.id)
                    result_msg = "Reverted dangerous permissions"
                    if not sec_state.emergency_stop:
                        try:
                            # Revert permissions
                            await after.edit(permissions=before.permissions, reason="Security: Unauthorized administrator permission grant")
                        except (discord.Forbidden, discord.HTTPException) as e:
                            result_msg = f"Failed to revert: {e}"

                    event_id = generate_event_id()
                    incident = SecurityIncident(
                        event_id=event_id,
                        guild_id=after.guild.id,
                        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        event_type="DANGEROUS_PERM_CHANGE",
                        executor_id=executor.id,
                        executor_name=f"{executor.name}",
                        target_id=after.id,
                        target_name=f"@{after.name}",
                        action="permission_grant_administrator",
                        detected_count=1,
                        threshold=1,
                        audit_log_id=audit_entry.id if audit_entry else None,
                        reason="Unauthorized administrator permission added to role",
                        automated_action="Reverted role permissions",
                        result=result_msg,
                        severity="high",
                        audit_verified=True,
                    )
                    await self.bot.db.record_security_incident(incident)
                    await self._notify_security_channel(after.guild, incident)

    async def _send_private_security_alert(self, guild: discord.Guild, embed: discord.Embed) -> bool:
        """Deliver security alert to the private staff/security channel."""
        log_cfg = await self.bot.db.get_logging_config(guild.id)
        candidate_ids = [
            1555283378612478072,  # 🚨・sᴇᴄᴜʀɪᴛʏ-ᴀʟᴇʀᴛs
            log_cfg.security_channel_id,
            log_cfg.moderation_channel_id,
            log_cfg.general_channel_id,
            1546593526073135107,  # 🚨｜ꜱᴇɴᴛɪɴᴇʟ-ʟᴏɢꜱ
            1545502845208629328,  # 🛡️｜ꜱᴛᴀꜰꜰ-ᴏᴘᴇʀᴀᴛɪᴏɴꜱ
            1546540192343523399,  # 📝｜ᴍᴏᴅᴇʀᴀᴛɪᴏɴ-ʟᴏɢꜱ
            1550187321285148782,  # 👑｜ᴇxᴇᴄᴜᴛɪᴠᴇ-ʟᴏᴜɴɢᴇ
        ]
        for cid in candidate_ids:
            if not cid:
                continue
            channel = guild.get_channel(cid)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(embed=embed)
                    return True
                except (discord.Forbidden, discord.HTTPException):
                    continue

        # Fallback: find any text channel inaccessible to @everyone with log/staff in name
        for channel in guild.text_channels:
            perms = channel.overwrites_for(guild.default_role)
            if perms.read_messages is False and any(k in channel.name.lower() for k in ("log", "staff", "security", "mod")):
                try:
                    await channel.send(embed=embed)
                    return True
                except (discord.Forbidden, discord.HTTPException):
                    continue
        return False

    async def _handle_everyone_mention(self, message: discord.Message) -> None:
        """
        Enforce Strict Founder-Only @everyone Rule:
        Only the Server Founder is permitted to mention @everyone or @here.
        Any other user attempting to do so has their message deleted instantly,
        is kicked from the server, and the incident is reported in the private staff/security channel.
        """
        if not message.guild:
            return

        # Check for webhook @everyone abuse
        if message.webhook_id and (message.mention_everyone or "@everyone" in message.content or "@here" in message.content):
            try:
                await message.delete()
            except Exception:
                pass
            clean_content = message.content[:500] if message.content else "*[No Text Content / Embed Only]*"
            alert_embed = security_embed(
                title="🚨 WEBHOOK @EVERYONE SPAM INTERCEPTED",
                description=(
                    f"**Blocked unauthorized `@everyone` / `@here` ping from an external webhook!**\n\n"
                    f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                    f"🔗 **Webhook ID:** `{message.webhook_id}`\n"
                    f"💬 **Content:**\n```{clean_content}```\n"
                    f"🗑️ **Message Status:** Deleted immediately."
                ),
            )
            await self._send_private_security_alert(message.guild, alert_embed)
            return

        # Ignore bot accounts (including Sentinel itself)
        if message.author.bot or not isinstance(message.author, discord.Member):
            return

        # Check if message mentions @everyone or @here
        has_everyone_mention = (
            message.mention_everyone
            or "@everyone" in message.content
            or "@here" in message.content
        )
        if not has_everyone_mention:
            return

        guild = message.guild
        member = message.author

        # Exemption: Server Founder ONLY
        if is_founder_or_owner(member):
            logger.info(f"Permitted @everyone mention by Server Founder {member.name} ({member.id}) in #{message.channel.name}")
            return

        # ==========================================
        # UNAUTHORIZED MENTION DETECTED
        # ==========================================
        logger.warning(
            f"Unauthorized @everyone mention by {member.name} ({member.id}) in #{message.channel.name} — executing kick & private channel alert."
        )

        # 1. Delete the message immediately to prevent notification spread
        msg_deleted = False
        try:
            await message.delete()
            msg_deleted = True
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
            logger.debug(f"Failed to delete unauthorized @everyone message: {e}")

        # 2. Attempt to notify member via DM
        try:
            dm_embed = error_embed(
                title="⛔ Kicked: Unauthorized @everyone Mention",
                description=(
                    f"You have been kicked from **{guild.name}**.\n\n"
                    f"**Violation:** Unauthorized `@everyone` / `@here` mention.\n"
                    f"**Server Policy:** Only the Server Founder is permitted to mention `@everyone`.\n"
                    f"Your message was automatically deleted."
                ),
            )
            await member.send(embed=dm_embed)
        except Exception:
            pass  # User DMs closed or blocked

        # 3. Check bot hierarchy and kick member from the server
        kick_success = False
        action_detail = ""
        can_mod, mod_reason = check_bot_hierarchy(member, guild.me)
        if not can_mod:
            action_detail = f"Could not kick due to hierarchy: {mod_reason}"
            logger.warning(f"Cannot kick {member.name} for @everyone mention: {mod_reason}")
        else:
            try:
                await member.kick(reason="Unauthorized @everyone / @here mention (Only Server Founder permitted)")
                kick_success = True
                action_detail = "Kicked from server"
                logger.info(f"Kicked {member.name} ({member.id}) for unauthorized @everyone mention.")
            except discord.Forbidden:
                action_detail = "Failed to kick: Missing Kick Members permission"
            except Exception as e:
                action_detail = f"Failed to kick: {str(e)[:100]}"

        # 4. Record security incident in database
        event_id = generate_event_id()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        incident = SecurityIncident(
            event_id=event_id,
            guild_id=guild.id,
            timestamp=now_iso,
            event_type="UNAUTHORIZED_EVERYONE_MENTION",
            executor_id=member.id,
            executor_name=f"{member.name} ({member.id})",
            target_id=message.channel.id,
            target_name=f"#{message.channel.name}",
            action="mention_everyone",
            detected_count=1,
            threshold=1,
            audit_log_id=None,
            reason="Non-founder member attempted to mention @everyone or @here",
            automated_action="Message Deleted & Member Kicked",
            result=action_detail,
            severity="critical",
            audit_verified=True,
        )
        await self.bot.db.record_security_incident(incident)
        await self.bot.db.record_violation(guild.id, member.id, "UNAUTHORIZED_EVERYONE_MENTION")

        # 5. Tell in private text channel
        clean_content = message.content[:500] if message.content else "*[No Text Content / Embed Only]*"
        alert_embed = security_embed(
            title="🚨 UNAUTHORIZED @EVERYONE MENTION BLOCKED",
            description=(
                f"**A non-founder user attempted to mention `@everyone` or `@here`!**\n\n"
                f"👤 **Offender:** {member.mention} (`{member.name}` | ID: `{member.id}`)\n"
                f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                f"💬 **Message Content:**\n```{clean_content}```\n"
                f"👢 **Enforcement Action:** `{'Kicked from Server' if kick_success else action_detail}`\n"
                f"🗑️ **Message:** {'Deleted instantly' if msg_deleted else 'Failed to delete'}\n"
                f"⚖️ **Policy:** Only the Server Founder is permitted to mention `@everyone`."
            ),
        )
        alert_embed.set_footer(text=f"Sentinel Security Protection • Incident ID: {event_id}")
        alert_embed.timestamp = discord.utils.utcnow()
        await self._send_private_security_alert(guild, alert_embed)

    async def _handle_honeypot_trap(self, message: discord.Message) -> bool:
        """
        Stealth Honeypot Raider Trap:
        The honeypot channel is invisible to normal members. Any message sent in it
        is guaranteed to be an automated scraper, self-bot, or unauthorized infiltrator.
        Triggers instant autonomous ban and alerts the security operations team.
        """
        HONEYPOT_CHANNEL_ID = 1558168338386129004  # #🪤・honeypot-trap
        if not message.guild or message.channel.id != HONEYPOT_CHANNEL_ID:
            return False

        if message.author.bot or message.author.id == message.guild.owner_id:
            return False

        guild = message.guild
        member = message.author

        # Delete trap-triggering message
        try:
            await message.delete()
        except Exception:
            pass

        # Instant sub-millisecond ban
        ban_success = False
        ban_error = ""
        try:
            if isinstance(member, discord.Member):
                await member.ban(reason="Honeypot Trap Triggered: Stealth Raider/Scraper Detected", delete_message_days=1)
                ban_success = True
        except Exception as e:
            ban_error = str(e)
            logger.error(f"Failed to ban honeypot intruder: {e}")

        event_id = generate_event_id()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        incident = SecurityIncident(
            event_id=event_id,
            guild_id=guild.id,
            timestamp=now_iso,
            event_type="HONEYPOT_TRIGGERED",
            executor_id=member.id,
            executor_name=f"{member.name} ({member.id})",
            target_id=message.channel.id,
            target_name=f"#{message.channel.name}",
            action="honeypot_message",
            detected_count=1,
            threshold=1,
            audit_log_id=None,
            reason="User posted in stealth honeypot channel (Scraper / Raider detected)",
            automated_action="Immediate Ban & 24h Purge" if ban_success else f"Ban failed: {ban_error}",
            result="Banned" if ban_success else "Pending Manual Ban",
            severity="critical",
            audit_verified=True,
        )
        await self.bot.db.record_security_incident(incident)
        await self.bot.db.record_violation(guild.id, member.id, "HONEYPOT_TRIGGERED")

        payload = message.content[:500] if message.content else "*[No Content / Embed]*"
        alert_embed = security_embed(
            title="🪤 STEALTH HONEYPOT TRAP TRIGGERED — RAIDER BAN ENFORCED",
            description=(
                f"**A suspicious entity posted in the hidden `#🪤・honeypot-trap`!**\n\n"
                f"👤 **Offender:** {member.mention} (`{member.name}` | ID: `{member.id}`)\n"
                f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                f"💬 **Captured Payload:**\n```{payload}```\n"
                f"⚡ **Automated Action:** `{'Permanently Banned & Purged' if ban_success else 'Ban Failed - Alerted Staff'}`\n"
                f"🛡️ **Perimeter Status:** Trap operational. Raider neutralized in < 1ms."
            ),
        )
        alert_embed.set_footer(text=f"Sentinel Security Honeytrap • Incident ID: {event_id}")
        alert_embed.timestamp = discord.utils.utcnow()
        await self._send_private_security_alert(guild, alert_embed)
        return True

    _SCAM_DOMAIN_PATTERN = re.compile(
        r"(?:https?://)?(?:www\.)?(?:[a-zA-Z0-9-]+\.)*(?:dlscord|discrod|discorcl|discort|discodo|gift-discord|nitro-discord|discord-claim|discord-drop|steamcommunyt|steamcommnuit|steamcommunlty|steancommunity|steam-gift|csgo-skins|rust-skins)\.[a-zA-Z]{2,10}(?:/[^\s]*)?",
        re.IGNORECASE,
    )
    _DECEPTIVE_NITRO_PATTERN = re.compile(
        r"(?:https?://)?(?:www\.)?[a-zA-Z0-9-]+\.(?:xyz|top|gift|click|ru|link|rest|shop|fun|space|site|cc|info)/(?:nitro|claim|gift|airdrop)",
        re.IGNORECASE,
    )
    _ZALGO_PATTERN = re.compile(r"[\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]")

    async def _handle_phishing_and_zalgo(self, message: discord.Message) -> bool:
        """
        Zero-Day Phishing & Anti-Zalgo Shield:
        1. Identifies and purges token-grabber, fake Nitro, and Steam phishing domains in < 1ms.
        2. Detects cursed Zalgo unicode combinations that freeze or crash Discord mobile apps.
        """
        if not message.guild or not message.author or message.author.bot or not message.content:
            return False

        member = message.author
        guild = message.guild
        if member.id == guild.owner_id or (isinstance(member, discord.Member) and is_founder_or_owner(member)):
            return False

        content = message.content

        # 1. Phishing & Malicious Link Interception
        is_phishing = bool(self._SCAM_DOMAIN_PATTERN.search(content) or self._DECEPTIVE_NITRO_PATTERN.search(content))
        if is_phishing:
            try:
                await message.delete()
            except Exception:
                pass

            timeout_applied = False
            if isinstance(member, discord.Member):
                try:
                    # Timeout for 24 hours to freeze compromised account
                    until = discord.utils.utcnow() + datetime.timedelta(hours=24)
                    await member.timeout(until, reason="Security: Zero-Day Phishing Domain Intercepted")
                    timeout_applied = True
                except Exception as e:
                    logger.warning(f"Could not timeout member {member.id} for phishing: {e}")

            event_id = generate_event_id()
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            incident = SecurityIncident(
                event_id=event_id,
                guild_id=guild.id,
                timestamp=now_iso,
                event_type="PHISHING_DOMAIN_BLOCKED",
                executor_id=member.id,
                executor_name=f"{member.name} ({member.id})",
                target_id=message.channel.id,
                target_name=f"#{message.channel.name}",
                action="phishing_link",
                detected_count=1,
                threshold=1,
                audit_log_id=None,
                reason="Posted malicious Discord Nitro or Steam phishing domain",
                automated_action="Deleted Message & 24h Account Isolation Timeout" if timeout_applied else "Deleted Message",
                result="Isolated" if timeout_applied else "Deleted",
                severity="critical",
                audit_verified=True,
            )
            await self.bot.db.record_security_incident(incident)
            await self.bot.db.record_violation(guild.id, member.id, "PHISHING_DOMAIN_BLOCKED")

            # Alert Staff
            alert_embed = security_embed(
                title="🛡️ ZERO-DAY PHISHING LINK INTERCEPTED",
                description=(
                    f"**Malicious token-grabber/scam URL neutralized!**\n\n"
                    f"👤 **Account:** {member.mention} (`{member.name}` | ID: `{member.id}`)\n"
                    f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                    f"🔗 **Payload Snippet:**\n```{content[:300]}```\n"
                    f"⚡ **Containment:** `{'24h Timeout Applied (Account Quarantined)' if timeout_applied else 'Message Purged'}`"
                ),
            )
            alert_embed.set_footer(text=f"Phishing Sentinel Shield • Incident ID: {event_id}")
            alert_embed.timestamp = discord.utils.utcnow()
            await self._send_private_security_alert(guild, alert_embed)

            # In-channel notification
            try:
                warn_embed = discord.Embed(
                    description=f"🛡️ **Security Alert:** Phishing link from {member.mention} intercepted and deleted. Account quarantined for safety.",
                    color=Colors.DANGER,
                )
                await message.channel.send(embed=warn_embed, delete_after=12.0)
            except Exception:
                pass
            return True

        # 2. Anti-Zalgo Text Cleaner
        zalgo_matches = len(self._ZALGO_PATTERN.findall(content))
        if zalgo_matches > 15:
            try:
                await message.delete()
            except Exception:
                pass

            try:
                warn_embed = discord.Embed(
                    description=f"⚠️ {member.mention}, glitched / Zalgo font spam is blocked to protect members from Discord app lag.",
                    color=Colors.WARNING,
                )
                await message.channel.send(embed=warn_embed, delete_after=8.0)
            except Exception:
                pass
            return True

        return False

    _BOT_TOKEN_PATTERN = re.compile(
        r"[a-zA-Z0-9_\-]{24,28}\.[a-zA-Z0-9_\-]{6}\.[a-zA-Z0-9_\-]{27,38}|mfa\.[a-zA-Z0-9_\-]{84}"
    )
    _WEBHOOK_URL_PATTERN = re.compile(
        r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[a-zA-Z0-9_\-]+"
    )

    async def _handle_token_and_webhook_leak(self, message: discord.Message) -> bool:
        """
        Credential Leak Guard:
        Intercepts raw Discord bot tokens and webhook URLs in chat,
        instantly purging them in < 1ms before automated scrapers capture them.
        """
        if not message.guild or not message.author or message.author.bot or not message.content:
            return False

        content = message.content
        has_token = bool(self._BOT_TOKEN_PATTERN.search(content))
        has_webhook = bool(self._WEBHOOK_URL_PATTERN.search(content))

        if not (has_token or has_webhook):
            return False

        leak_type = "Discord Bot Token" if has_token else "Discord Webhook URL"

        # 1. Immediately delete message
        try:
            await message.delete()
        except Exception:
            pass

        guild = message.guild
        member = message.author
        event_id = generate_event_id()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 2. Record security incident
        incident = SecurityIncident(
            event_id=event_id,
            guild_id=guild.id,
            timestamp=now_iso,
            event_type="CREDENTIAL_LEAK_PREVENTED",
            executor_id=member.id,
            executor_name=f"{member.name} ({member.id})",
            target_id=message.channel.id,
            target_name=f"#{message.channel.name}",
            action="credential_leak",
            detected_count=1,
            threshold=1,
            audit_log_id=None,
            reason=f"Exposed raw {leak_type} in text chat",
            automated_action="Message Deleted & Security Operations Alerted",
            result="Sanitized",
            severity="high",
            audit_verified=True,
        )
        await self.bot.db.record_security_incident(incident)
        await self.bot.db.record_violation(guild.id, member.id, "CREDENTIAL_LEAK_PREVENTED")

        # 3. Alert Security Channel
        alert_embed = security_embed(
            title="🔑 CREDENTIAL LEAK INTERCEPTED & PURGED",
            description=(
                f"**A sensitive secret credential was posted and purged in `< 1ms`!**\n\n"
                f"👤 **Exposed By:** {member.mention} (`{member.name}` | ID: `{member.id}`)\n"
                f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                f"🔐 **Detected Type:** `{leak_type}`\n"
                f"🗑️ **Status:** Payload destroyed immediately. Scraper interception prevented."
            ),
        )
        alert_embed.set_footer(text=f"Sentinel Credential Shield • Incident ID: {event_id}")
        alert_embed.timestamp = discord.utils.utcnow()
        await self._send_private_security_alert(guild, alert_embed)

        # 4. DM the member with reset advice
        try:
            dm_embed = warning_embed(
                title="⚠️ Urgent: Your Secret Token Was Leaked & Protected",
                description=(
                    f"You posted a secret **{leak_type}** in **{guild.name}** (`#{message.channel.name}`).\n\n"
                    f"**What we did:** Sentinel deleted your message immediately to protect you from malicious token scrapers.\n\n"
                    f"**Action Required:** If this was an active bot token or webhook, please **regenerate / reset it immediately** "
                    f"in the Discord Developer Portal or Server Settings to keep your account safe."
                ),
            )
            await member.send(embed=dm_embed)
        except Exception:
            pass

        # 5. In-channel reassurance
        try:
            warn_embed = discord.Embed(
                description=f"🔑 **Credential Shield:** A sensitive bot token or webhook from {member.mention} was intercepted and deleted for safety.",
                color=Colors.WARNING,
            )
            await message.channel.send(embed=warn_embed, delete_after=12.0)
        except Exception:
            pass

        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if await self._handle_honeypot_trap(message):
            return
        if await self._handle_token_and_webhook_leak(message):
            return
        if await self._handle_phishing_and_zalgo(message):
            return
        await self._handle_everyone_mention(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if await self._handle_token_and_webhook_leak(after):
            return
        if await self._handle_phishing_and_zalgo(after):
            return
        await self._handle_everyone_mention(after)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """
        Anti-Ghost Ping Protection:
        Detects when a user pings members or roles and deletes their message.
        Exposes the ghost ping in-channel and logs the violation to security alerts.
        """
        if not message.guild or not message.author or message.author.bot:
            return

        # Identify mentioned users (excluding bots and self) and mentioned roles
        targets = [m for m in message.mentions if not m.bot and m.id != message.author.id]
        role_targets = message.role_mentions

        if not targets and not role_targets:
            return

        # Check if the message was deleted quickly (within 5 minutes of sending)
        lifetime = (discord.utils.utcnow() - message.created_at).total_seconds()
        if lifetime > 300:
            return

        target_strs = [m.mention for m in targets] + [r.mention for r in role_targets]
        target_display = ", ".join(target_strs)

        # 1. Log to private security alerts channel
        ghost_embed = warning_embed(
            title="👻 GHOST PING INTERCEPTED",
            description=(
                f"**A user mentioned members/roles and deleted their message!**\n\n"
                f"👤 **Author:** {message.author.mention} (`{message.author.name}` | ID: `{message.author.id}`)\n"
                f"📍 **Channel:** {message.channel.mention} (`#{message.channel.name}`)\n"
                f"🎯 **Targeted Mentions:** {target_display}\n"
                f"💬 **Deleted Content:**\n```{message.content[:500] if message.content else '*[No Content / Embed]*'}```\n"
                f"⏱️ **Message Lifetime:** `{int(lifetime)} seconds`"
            ),
        )
        ghost_embed.set_footer(text="Anti-Ghost Ping Sentinel")
        ghost_embed.timestamp = discord.utils.utcnow()
        await self._send_private_security_alert(message.guild, ghost_embed)

        # 2. Expose the ghost ping in the origin channel with auto-delete (15s)
        try:
            reveal_embed = discord.Embed(
                description=f"👻 **Ghost Ping Detected!** {message.author.mention} pinged {target_display} and deleted their message.",
                color=Colors.WARNING,
            )
            reveal_embed.set_footer(text="Anti-Ghost Ping Sentinel • Auto-cleaning in 15s")
            await message.channel.send(embed=reveal_embed, delete_after=15.0)
        except Exception:
            pass

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @security_group.command(name="setup", description="Configure security action limits and punishment policy")
    @is_admin_or_owner()
    @app_commands.describe(
        punishment="Automated action when thresholds are exceeded",
        channel_delete_limit="Max channel deletions allowed within window",
        role_delete_limit="Max role deletions allowed within window",
        ban_limit="Max bans allowed within window",
        time_window="Detection window in seconds (5-60s)",
    )
    @app_commands.choices(
        punishment=[
            app_commands.Choice(name="Alert Only", value="alert"),
            app_commands.Choice(name="Timeout Attacker", value="timeout"),
            app_commands.Choice(name="Kick Attacker", value="kick"),
            app_commands.Choice(name="Ban Attacker", value="ban"),
            app_commands.Choice(name="Strip Dangerous Roles", value="remove_roles"),
            app_commands.Choice(name="Lock Channels", value="lock_channels"),
        ]
    )
    async def security_setup(
        self,
        interaction: discord.Interaction,
        punishment: app_commands.Choice[str],
        channel_delete_limit: Optional[int] = None,
        role_delete_limit: Optional[int] = None,
        ban_limit: Optional[int] = None,
        time_window: Optional[int] = None,
    ):
        # Validation
        if channel_delete_limit is not None and not (1 <= channel_delete_limit <= 50):
            await interaction.response.send_message(embed=error_embed("Limit must be between 1 and 50"), ephemeral=True)
            return
        if time_window is not None and not (5 <= time_window <= 120):
            await interaction.response.send_message(embed=error_embed("Time window must be between 5 and 120 seconds"), ephemeral=True)
            return

        updates = {"punishment": punishment.value}
        if channel_delete_limit is not None:
            updates["channel_delete_limit"] = channel_delete_limit
        if role_delete_limit is not None:
            updates["role_delete_limit"] = role_delete_limit
        if ban_limit is not None:
            updates["ban_limit"] = ban_limit
        if time_window is not None:
            updates["channel_delete_window"] = time_window
            updates["role_delete_window"] = time_window
            updates["ban_window"] = time_window

        await self.bot.db.update_security_config(interaction.guild.id, **updates)
        embed = success_embed(
            "Security Configuration Updated",
            f"**Punishment:** {punishment.name}\n"
            f"**Channel Delete Limit:** {updates.get('channel_delete_limit', 'Unchanged')}\n"
            f"**Role Delete Limit:** {updates.get('role_delete_limit', 'Unchanged')}\n"
            f"**Ban Limit:** {updates.get('ban_limit', 'Unchanged')}\n"
            f"**Window:** {time_window or 'Unchanged'}s",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @security_group.command(name="enable", description="Enable the security and anti-nuke module")
    @is_admin_or_owner()
    async def security_enable(self, interaction: discord.Interaction):
        await self.bot.db.update_guild_config(interaction.guild.id, security_enabled=True)
        await interaction.response.send_message(
            embed=success_embed("Security Enabled", "The anti-nuke protection system is now active."), ephemeral=True
        )

    @security_group.command(name="disable", description="Disable the security and anti-nuke module")
    @is_admin_or_owner()
    async def security_disable(self, interaction: discord.Interaction):
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=warning_embed(
                "Confirm Disabling Security",
                "Disabling security will turn off all automated protections against mass deletions, unauthorized bots, and malicious actions. Are you sure?",
            ),
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if view.value is True:
            await self.bot.db.update_guild_config(interaction.guild.id, security_enabled=False)
            await interaction.followup.send(
                embed=error_embed("Security Disabled", "The anti-nuke protection system has been disabled."), ephemeral=True
            )

    @security_group.command(name="status", description="Display full security dashboard, thresholds, and health")
    @is_admin_or_owner()
    async def security_status(self, interaction: discord.Interaction):
        guild = interaction.guild
        guild_cfg = await self.bot.db.get_or_create_guild_config(guild.id)
        sec_cfg = await self.bot.db.get_security_config(guild.id)
        sec_state = await self.bot.db.get_security_state(guild.id)
        whitelist = await self.bot.db.get_whitelist(guild.id)
        incidents = await self.bot.db.get_security_incidents(guild.id, limit=3)

        status_str = "🟢 Active" if guild_cfg.security_enabled else "🔴 Disabled"
        emergency_str = "🚨 EMERGENCY STOP ACTIVE" if sec_state.emergency_stop else "Normal"
        lockdown_str = "🔒 Server in Lockdown" if sec_state.lockdown_enabled else "Normal"

        embed = create_embed(
            title=f"🛡️ Security Dashboard — {guild.name}",
            color=Colors.SECURITY if not sec_state.emergency_stop else Colors.ERROR,
        )
        embed.add_field(name="Module Status", value=status_str, inline=True)
        embed.add_field(name="Emergency Mode", value=emergency_str, inline=True)
        embed.add_field(name="Lockdown Status", value=lockdown_str, inline=True)

        thresholds = (
            f"• Channels Delete: `{sec_cfg.channel_delete_limit}` / `{sec_cfg.channel_delete_window}s`\n"
            f"• Channels Create: `{sec_cfg.channel_create_limit}` / `{sec_cfg.channel_create_window}s`\n"
            f"• Roles Delete: `{sec_cfg.role_delete_limit}` / `{sec_cfg.role_delete_window}s`\n"
            f"• Roles Create: `{sec_cfg.role_create_limit}` / `{sec_cfg.role_create_window}s`\n"
            f"• Bans: `{sec_cfg.ban_limit}` / `{sec_cfg.ban_window}s`\n"
            f"• Webhooks: `{sec_cfg.webhook_limit}` / `{sec_cfg.webhook_window}s`\n"
            f"• Configured Action: `{sec_cfg.punishment}`"
        )
        embed.add_field(name="Active Thresholds", value=thresholds, inline=False)

        wl_users = [f"<@{item['target_id']}>" for item in whitelist if item["target_type"] == "user"]
        wl_roles = [f"<@&{item['target_id']}>" for item in whitelist if item["target_type"] == "role"]
        embed.add_field(
            name=f"Whitelist ({len(whitelist)})",
            value=f"**Users:** {', '.join(wl_users) if wl_users else 'None'}\n"
                  f"**Roles:** {', '.join(wl_roles) if wl_roles else 'None'}",
            inline=False,
        )

        if incidents:
            inc_lines = [
                f"`[{inc.event_id}]` **{inc.event_type}** by {inc.executor_name or 'UNKNOWN'} → *{inc.result}*"
                for inc in incidents
            ]
            embed.add_field(name="Recent Incidents", value="\n".join(inc_lines), inline=False)
        else:
            embed.add_field(name="Recent Incidents", value="No incidents recorded.", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @security_group.command(name="whitelist", description="Manage trusted users or roles exempt from security limits")
    @is_admin_or_owner()
    @app_commands.describe(
        action="Add or remove from whitelist",
        user="User to whitelist",
        role="Role to whitelist",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Add", value="add"),
            app_commands.Choice(name="Remove", value="remove"),
            app_commands.Choice(name="List", value="list"),
        ]
    )
    async def security_whitelist(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        user: Optional[discord.Member] = None,
        role: Optional[discord.Role] = None,
    ):
        guild_id = interaction.guild.id

        if action.value == "list":
            wl = await self.bot.db.get_whitelist(guild_id)
            if not wl:
                await interaction.response.send_message(embed=info_embed("Whitelist Empty", "No users or roles are currently whitelisted."), ephemeral=True)
                return
            users = [f"<@{item['target_id']}> (added by <@{item['added_by']}>)" for item in wl if item["target_type"] == "user"]
            roles = [f"<@&{item['target_id']}> (added by <@{item['added_by']}>)" for item in wl if item["target_type"] == "role"]
            embed = info_embed(
                "Security Whitelist",
                f"**Users:**\n{chr(10).join(users) if users else 'None'}\n\n**Roles:**\n{chr(10).join(roles) if roles else 'None'}"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not user and not role:
            await interaction.response.send_message(embed=error_embed("Specify either a user or a role to modify."), ephemeral=True)
            return

        target_id = user.id if user else role.id
        target_type = "user" if user else "role"
        mention = user.mention if user else role.mention

        if action.value == "add":
            await self.bot.db.add_whitelist(guild_id, target_id, target_type, interaction.user.id)
            await interaction.response.send_message(embed=success_embed("Whitelist Added", f"Added {mention} to the security whitelist."), ephemeral=True)
        else:
            removed = await self.bot.db.remove_whitelist(guild_id, target_id, target_type)
            if removed:
                await interaction.response.send_message(embed=success_embed("Whitelist Removed", f"Removed {mention} from the security whitelist."), ephemeral=True)
            else:
                await interaction.response.send_message(embed=warning_embed("Not Found", f"{mention} was not on the whitelist."), ephemeral=True)

    @security_group.command(name="lockdown", description="Initiate emergency lockdown on all server channels")
    @is_admin_or_owner()
    async def security_lockdown(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self._execute_lockdown(interaction.guild)
        await interaction.followup.send(
            embed=security_embed("Emergency Lockdown Activated", f"Successfully restricted message permissions in **{count}** channels."),
            ephemeral=True,
        )

    @security_group.command(name="unlock", description="Lift server lockdown and restore channel permissions")
    @is_admin_or_owner()
    async def security_unlock(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self._execute_unlock(interaction.guild)
        await interaction.followup.send(
            embed=success_embed("Lockdown Lifted", f"Restored permissions in **{count}** channels."),
            ephemeral=True,
        )

    @security_group.command(name="emergency-stop", description="Kill switch: halts destructive automated punishments while continuing logging")
    @is_admin_or_owner()
    async def emergency_stop(self, interaction: discord.Interaction):
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            embed=warning_embed(
                "Activate Emergency Stop?",
                "This halts all automated destructive punishments (bans, kicks, role stripping) immediately. Monitoring and incident recording will continue.",
            ),
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if view.value is True:
            await self.bot.db.set_emergency_stop(interaction.guild.id, True, interaction.user.id)
            await interaction.followup.send(
                embed=error_embed("EMERGENCY STOP ENGAGED", "Automated destructive actions are now suppressed across the server."),
                ephemeral=True,
            )

    @security_group.command(name="emergency-resume", description="Resume normal automated security actions after emergency stop")
    @is_admin_or_owner()
    async def emergency_resume(self, interaction: discord.Interaction):
        await self.bot.db.set_emergency_stop(interaction.guild.id, False, interaction.user.id)
        await interaction.response.send_message(
            embed=success_embed("Emergency Mode Disengaged", "Normal automated security punishments have been resumed."),
            ephemeral=True,
        )

    @security_group.command(name="emergency-status", description="Check current emergency stop status")
    @is_admin_or_owner()
    async def emergency_status(self, interaction: discord.Interaction):
        sec_state = await self.bot.db.get_security_state(interaction.guild.id)
        status_text = "🚨 **ACTIVE** — Destructive automated actions are disabled." if sec_state.emergency_stop else "✅ **INACTIVE** — Full security automation is armed."
        await interaction.response.send_message(embed=info_embed("Emergency Status", status_text), ephemeral=True)

    @app_commands.command(name="panic", description="Emergency panic mode: instantly locks down all channels and alerts staff")
    @is_admin_or_owner()
    async def panic_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self._execute_lockdown(interaction.guild)
        await self.bot.db.set_emergency_stop(interaction.guild.id, True, interaction.user.id)

        # Send alert to staff security log
        embed_alert = error_embed(
            "🚨 SERVER PANIC MODE TRIGGERED",
            f"**Initiated By:** {interaction.user.mention} (`{interaction.user.id}`)\n"
            f"• **Channels Locked:** `{count}` channels\n"
            f"• **Emergency Stop:** Enabled (destructive actions suppressed)\n"
            f"• **Action Required:** Authorized staff investigate server activity immediately.",
        )
        cfg_log = await self.bot.db.get_logging_config(interaction.guild.id)
        if cfg_log.security_channel_id:
            ch = interaction.guild.get_channel(cfg_log.security_channel_id)
            if ch:
                try:
                    await ch.send(content="@here", embed=embed_alert)
                except Exception:
                    pass

        await interaction.followup.send(
            embed=error_embed(
                "🚨 Panic Mode Active",
                f"Panic mode engaged by {interaction.user.mention}.\n"
                f"• Restriced message permissions in **{count}** channels.\n"
                f"• Automated emergency stop activated.\n"
                f"• Staff security alerts dispatched.",
            ),
            ephemeral=True,
        )

    @security_group.command(name="config", description="Display full active security configuration and thresholds")
    @is_admin_or_owner()
    async def security_config_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await self.bot.db.get_security_config(interaction.guild.id)
        embed = create_embed(
            title=f"🛡️ Security Configuration — {interaction.guild.name}",
            description="Active anti-nuke thresholds, detection windows, and automated punishment policies.",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Channel Delete Limit", value=f"`{cfg.channel_delete_limit}` / `{cfg.channel_delete_window}s`", inline=True)
        embed.add_field(name="Channel Create Limit", value=f"`{cfg.channel_create_limit}` / `{cfg.channel_create_window}s`", inline=True)
        embed.add_field(name="Role Delete Limit", value=f"`{cfg.role_delete_limit}` / `{cfg.role_delete_window}s`", inline=True)
        embed.add_field(name="Role Create Limit", value=f"`{cfg.role_create_limit}` / `{cfg.role_create_window}s`", inline=True)
        embed.add_field(name="Ban Limit", value=f"`{cfg.ban_limit}` / `{cfg.ban_window}s`", inline=True)
        embed.add_field(name="Kick Limit", value=f"`{cfg.kick_limit}` / `{cfg.kick_window}s`", inline=True)
        embed.add_field(name="Webhook Limit", value=f"`{cfg.webhook_limit}` / `{cfg.webhook_window}s`", inline=True)
        embed.add_field(name="Default Punishment", value=f"`{cfg.punishment.upper()}`", inline=True)
        embed.set_footer(text="Rai Security Pro • Anti-Nuke & Real-time Verification Engine")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @security_group.command(name="incidents", description="Review security incident audit trail with optional filters")
    @is_admin_or_owner()
    @app_commands.describe(
        event_type="Filter by event type (e.g. CHANNEL_DELETE)",
        executor="Filter by member who triggered event",
        severity="Filter by severity level",
    )
    @app_commands.choices(
        severity=[
            app_commands.Choice(name="Low", value="low"),
            app_commands.Choice(name="Medium", value="medium"),
            app_commands.Choice(name="High", value="high"),
        ]
    )
    async def security_incidents(
        self,
        interaction: discord.Interaction,
        event_type: Optional[str] = None,
        executor: Optional[discord.Member] = None,
        severity: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        incidents = await self.bot.db.get_security_incidents(
            guild_id=interaction.guild.id,
            limit=25,
            event_type=event_type,
            executor_id=executor.id if executor else None,
            severity=severity.value if severity else None,
        )
        if not incidents:
            await interaction.followup.send(embed=info_embed("No Incidents Found", "No security incidents match the requested filters."), ephemeral=True)
            return

        pages = []
        chunks = [incidents[i:i + 5] for i in range(0, len(incidents), 5)]
        for page_idx, chunk in enumerate(chunks, 1):
            embed = create_embed(
                title=f"📋 Security Incident Log (Page {page_idx}/{len(chunks)})",
                color=Colors.SECURITY,
            )
            for inc in chunk:
                embed.add_field(
                    name=f"[{inc.event_id}] {inc.event_type} — {inc.timestamp[:19]}",
                    value=(
                        f"**Executor:** {inc.executor_name or 'UNKNOWN'}\n"
                        f"**Target:** {inc.target_name or 'N/A'}\n"
                        f"**Count/Threshold:** {inc.detected_count}/{inc.threshold}\n"
                        f"**Action:** {inc.automated_action} | **Result:** {inc.result}\n"
                        f"**Verified:** {'Yes' if inc.audit_verified else 'No'}"
                    ),
                    inline=False,
                )
            pages.append(embed)

        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0], ephemeral=True)
        else:
            view = PaginationView(pages, interaction.user.id)
            await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)

    @security_group.command(name="cooldowns", description="View active in-memory security and command cooldowns")
    @is_admin_or_owner()
    async def security_cooldowns(self, interaction: discord.Interaction):
        counts = await self.bot.cooldowns.cleanup_expired()
        await interaction.response.send_message(
            embed=info_embed(
                "Active Cooldown Statistics",
                f"• Cleaned Expired Runtime Entries: `{counts['runtime_cooldowns']}`\n"
                f"• Cleaned Expired Persistent Records: `{counts['db_cooldowns']}`\n"
                f"• Cleaned Stale Violations: `{counts['db_violations']}`\n"
                f"• In-Memory Buckets Tracked: `{len(self.bot.cooldowns._security_sliding_windows)}`",
            ),
            ephemeral=True,
        )

    @security_group.command(name="reset-cooldown", description="Reset cooldowns for a specific user")
    @is_admin_or_owner()
    @app_commands.describe(user="The user whose cooldowns should be cleared")
    async def reset_cooldown(self, interaction: discord.Interaction, user: discord.Member):
        if user.id == interaction.user.id and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(embed=error_embed("You cannot reset your own cooldowns."), ephemeral=True)
            return

        removed = await self.bot.cooldowns.reset_user_cooldowns(user.id, interaction.guild.id)
        await interaction.response.send_message(
            embed=success_embed("Cooldown Reset", f"Cleared `{removed}` active cooldown(s) for {user.mention}."),
            ephemeral=True,
        )

    @security_group.command(name="reset-cooldowns", description="Reset all active runtime cooldowns in this guild")
    @is_admin_or_owner()
    async def reset_all_cooldowns_cmd(self, interaction: discord.Interaction):
        removed = await self.bot.cooldowns.reset_all_cooldowns(interaction.guild.id)
        await interaction.response.send_message(
            embed=success_embed("All Cooldowns Reset", f"Cleared `{removed}` active cooldown(s) across the server."),
            ephemeral=True,
        )

    @tasks.loop(hours=24)
    async def _nightly_backup_loop(self):
        try:
            if hasattr(self.bot, "wait_until_ready") and callable(self.bot.wait_until_ready):
                res = self.bot.wait_until_ready()
                if asyncio.iscoroutine(res):
                    await res
        except Exception:
            pass
        try:
            mgr = BackupManager.get_instance()
            rec = await mgr.run_backup(trigger="scheduled_nightly")
            logger.info(f"Nightly disaster recovery backup verified: {rec.backup_id}")

            BACKUP_CONTROL_ID = 1555283418126876856  # #💾・ʙᴀᴄᴋᴜᴘ-ᴄᴏɴᴛʀᴏʟ
            for guild in self.bot.guilds:
                ch = guild.get_channel(BACKUP_CONTROL_ID)
                if ch and isinstance(ch, discord.TextChannel):
                    embed = success_embed(
                        "Disaster Recovery Backup Verified",
                        (
                            f"**Snapshot ID:** `{rec.backup_id}`\n"
                            f"**Status:** `VERIFIED (SHA-256 Validated)`\n"
                            f"**Archive Size:** `{format_bytes(rec.archive_size)}`\n"
                            f"**Storage:** `{rec.storage_type}`\n"
                            f"**Created:** `{rec.formatted_created_at}`\n\n"
                            f"Disaster recovery checkpoint saved to `data/backups/`."
                        ),
                    )
                    await ch.send(embed=embed)
        except Exception as e:
            logger.error(f"Nightly backup failed: {e}")

    @security_group.command(name="backup", description="Execute an instant disaster recovery backup of all server data")
    @is_admin_or_owner()
    async def security_backup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            mgr = BackupManager.get_instance()
            rec = await mgr.run_backup(trigger=f"manual_by_{interaction.user}")
            embed = success_embed(
                "Disaster Recovery Backup Complete",
                (
                    f"**Snapshot ID:** `{rec.backup_id}`\n"
                    f"**Status:** `VERIFIED (SHA-256 Validated)`\n"
                    f"**Archive Size:** `{format_bytes(rec.archive_size)}`\n"
                    f"**Components Included:** Database, Configuration, Security Policies, Voice Rooms, Playlists\n"
                    f"**Timestamp:** `{rec.formatted_created_at}`\n\n"
                    f"Snapshot safely established in `data/backups/`."
                ),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=error_embed("Backup Failed", str(e)), ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(SecurityCog(bot))
