"""
AI Incident Analysis & One-Click DM Action Subsystem for Rai.

Features:
- Heuristic and context-driven AI incident analysis (threat level, impact assessment, remediation recommendation).
- Generates contextual interactive Discord UI buttons sent EXCLUSIVELY to the Founder / Owner in DM.
- Directly executes safe, authoritative actions from DM (e.g. Delete Channel, Lock Channel, Timeout User, Kick/Ban, Panic Mode, Approve).
- Prevents public channel pollution (buttons and AI resolution controls are isolated strictly to Owner DM).
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord

from config import Colors

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class IncidentAlertTracker:
    """Tracks active, unacknowledged incident alerts sent to users' DMs."""
    _alerts: Dict[int, List[discord.Message]] = {}

    @classmethod
    def add_alert(cls, user_id: int, message: discord.Message) -> None:
        if user_id not in cls._alerts:
            cls._alerts[user_id] = []
        cls._alerts[user_id].append(message)
        if len(cls._alerts[user_id]) > 50:
            cls._alerts[user_id] = cls._alerts[user_id][-50:]

    @classmethod
    def get_pending_count(cls, user_id: int) -> int:
        return len(cls._alerts.get(user_id, []))

    @classmethod
    def get_and_clear_alerts(cls, user_id: int) -> List[discord.Message]:
        return cls._alerts.pop(user_id, [])

    @classmethod
    def reset(cls) -> None:
        cls._alerts.clear()


class IncidentAnalysisResult:
    def __init__(
        self,
        threat_level: str,
        assessment: str,
        recommendation: str,
        actions: List[str],
    ):
        self.threat_level = threat_level  # "🟢 LOW", "🟡 MEDIUM", "🟠 HIGH", "🔴 CRITICAL"
        self.assessment = assessment
        self.recommendation = recommendation
        self.actions = actions


class AIIncidentAnalyzer:
    """Intelligent triage engine for server events and security alerts."""

    @staticmethod
    def analyze(
        event_type: str,
        title: str,
        description: str,
        actor: Optional[discord.User | discord.Member] = None,
        target_name: Optional[str] = None,
    ) -> IncidentAnalysisResult:
        low_title = title.lower()

        # 0. TEMPORARY VOICE ROOM LIFECYCLE
        if "room closed" in low_title or event_type in ("room_delete", "room_lifecycle") or ("room" in (target_name or "").lower() and event_type == "room_delete"):
            threat = "🟢 LOW"
            assessment = f"Temporary voice room `{target_name or 'room'}` was cleaned up as members departed."
            recommendation = "Normal voice suite lifecycle event. No action required."
            actions = ["mark_safe"]

        # 1. CHANNEL CREATED
        elif "channel created" in low_title or event_type == "channel_create":
            is_bot = getattr(actor, "bot", False) if actor else False
            threat = "🟡 MEDIUM" if is_bot else "🟢 LOW"
            assessment = (
                f"A new channel `{target_name or 'channel'}` was created"
                + (f" by bot `{actor.name}`." if is_bot else " on the server.")
                + " Unplanned channel creation can disrupt server layout or indicate unauthorized integration activity."
            )
            recommendation = "If this channel was unexpected, lock it immediately or delete it to maintain layout hygiene."
            actions = ["delete_channel", "lock_channel", "mark_safe"]

        # 2. CHANNEL DELETED
        elif "channel deleted" in low_title or event_type == "channel_delete":
            threat = "🟠 HIGH"
            assessment = f"Channel `{target_name or 'channel'}` was permanently removed. Multiple deletions could signify a destructive nuke attempt."
            recommendation = "Review audit logs. If unauthorized, lock down the server immediately to stop data loss."
            actions = ["lockdown_category", "mark_safe"]

        # 3. CHANNEL UPDATED
        elif "channel updated" in low_title or event_type == "channel_update":
            threat = "🟢 LOW"
            assessment = f"Channel `{target_name or 'channel'}` configuration, name, or topic was modified."
            recommendation = "Verify that the modifications align with your community guidelines."
            actions = ["lock_channel", "mark_safe"]

        # 4. ROLE CREATED OR UPDATED
        elif "role" in low_title or event_type in ("role_create", "role_delete", "role_update"):
            threat = "🟠 HIGH"
            assessment = f"Role `{target_name or 'role'}` was modified or created. Unauthorized roles can lead to privilege escalation or admin leaks."
            recommendation = "Inspect permissions. Ensure Administrator and Mention Everyone remain strictly isolated."
            actions = ["delete_role", "strip_role_perms", "mark_safe"]

        # 5. UNAUTHORIZED MENTIONS / SPAM / RAID
        elif "mention" in low_title or "spam" in low_title or "raid" in low_title or event_type in ("everyone_mention", "anti_raid", "anti_spam"):
            threat = "🔴 CRITICAL"
            assessment = f"Security trigger activated for `{target_name or 'member'}`. Unauthorized ping or rapid spam pattern detected."
            recommendation = "Isolate the actor immediately via 1h Timeout or Ban to preserve chat tranquility."
            actions = ["ban_user", "timeout_user", "kick_user", "mark_safe"]

        # 6. MEMBER ACTIONS (JOIN / LEAVE / KICK / BAN)
        elif "member" in low_title or event_type in ("member_join", "member_remove", "member_kick", "member_ban"):
            threat = "🟢 LOW"
            assessment = f"Member activity recorded for `{target_name or 'user'}`."
            recommendation = "Monitor new accounts for rapid multi-joins or spam links."
            actions = ["timeout_user", "kick_user", "mark_safe"]

        # 7. DEFAULT / GENERIC INCIDENT
        else:
            threat = "🟡 MEDIUM"
            assessment = f"Activity detected: {description[:150]}"
            recommendation = "Review the event details and confirm if authorized."
            actions = ["mark_safe"]

        return IncidentAnalysisResult(
            threat_level=threat,
            assessment=assessment,
            recommendation=recommendation,
            actions=actions,
        )


class OwnerIncidentActionView(discord.ui.View):
    """
    Action view sent strictly to the Founder / Owner in DM.
    Executes authoritative resolution actions on the server directly from DM.
    """

    def __init__(
        self,
        bot: SentinelBot,
        guild_id: int,
        target_id: Optional[int],
        target_name: Optional[str],
        actor_id: Optional[int],
        event_type: str,
        owner_id: int,
        analysis: IncidentAnalysisResult,
        pending_count: int = 1,
    ):
        super().__init__(timeout=86400.0)  # 24 hour lifespan
        self.bot = bot
        self.guild_id = guild_id
        self.target_id = target_id
        self.target_name = target_name or "Target"
        self.actor_id = actor_id
        self.event_type = event_type
        self.owner_id = owner_id
        self.analysis = analysis
        self.pending_count = pending_count

        self._build_buttons()

    def _build_buttons(self):
        actions = self.analysis.actions

        if "delete_channel" in actions and self.target_id:
            btn = discord.ui.Button(
                label="Delete Channel",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
                custom_id=f"inc_del_ch_{self.target_id}",
            )
            btn.callback = self._handle_delete_channel
            self.add_item(btn)

        if "lock_channel" in actions and self.target_id:
            btn = discord.ui.Button(
                label="Lock Channel",
                style=discord.ButtonStyle.secondary,
                emoji="🔒",
                custom_id=f"inc_lock_ch_{self.target_id}",
            )
            btn.callback = self._handle_lock_channel
            self.add_item(btn)

        if "timeout_user" in actions and (self.target_id or self.actor_id):
            uid = self.actor_id or self.target_id
            btn = discord.ui.Button(
                label="Timeout 1h",
                style=discord.ButtonStyle.secondary,
                emoji="⏳",
                custom_id=f"inc_to_{uid}",
            )
            btn.callback = self._handle_timeout_user
            self.add_item(btn)

        if "kick_user" in actions and (self.target_id or self.actor_id):
            uid = self.actor_id or self.target_id
            btn = discord.ui.Button(
                label="Kick User",
                style=discord.ButtonStyle.secondary,
                emoji="👢",
                custom_id=f"inc_kick_{uid}",
            )
            btn.callback = self._handle_kick_user
            self.add_item(btn)

        if "ban_user" in actions and (self.target_id or self.actor_id):
            uid = self.actor_id or self.target_id
            btn = discord.ui.Button(
                label="Ban User",
                style=discord.ButtonStyle.danger,
                emoji="🔨",
                custom_id=f"inc_ban_{uid}",
            )
            btn.callback = self._handle_ban_user
            self.add_item(btn)

        if "delete_role" in actions and self.target_id:
            btn = discord.ui.Button(
                label="Delete Role",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
                custom_id=f"inc_del_role_{self.target_id}",
            )
            btn.callback = self._handle_delete_role
            self.add_item(btn)

        # Always offer "Mark as Safe / Dismiss"
        safe_btn = discord.ui.Button(
            label="Mark as Safe",
            style=discord.ButtonStyle.success,
            emoji="✅",
            custom_id="inc_safe_ack",
        )
        safe_btn.callback = self._handle_mark_safe
        self.add_item(safe_btn)

        # If there are multiple alerts or pending backlog, provide "Mark All as Read"
        if self.pending_count > 1:
            mark_all_btn = discord.ui.Button(
                label=f"Mark All as Read ({self.pending_count})",
                style=discord.ButtonStyle.primary,
                emoji="📑",
                custom_id="inc_mark_all_read",
            )
            mark_all_btn.callback = self._handle_mark_all_read
            self.add_item(mark_all_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This incident action console is private to the server owner.", ephemeral=True)
            return False
        return True

    def _disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    async def _update_dm_embed(self, interaction: discord.Interaction, resolution_text: str, success: bool = True):
        self._disable_all_buttons()
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed(title="Incident")
        embed.color = Colors.SUCCESS if success else Colors.ERROR
        embed.add_field(
            name="🛡️ Founder Action Taken",
            value=f"{resolution_text}\n*Resolved by {interaction.user.mention}*",
            inline=False,
        )
        try:
            await interaction.message.edit(embed=embed, view=self)
        except Exception:
            pass

    async def _handle_delete_channel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            await interaction.followup.send("❌ Server not found.", ephemeral=True)
            return

        channel = guild.get_channel(self.target_id)
        if not channel:
            try:
                channel = await guild.fetch_channel(self.target_id)
            except Exception:
                channel = None

        if not channel:
            await self._update_dm_embed(interaction, "⚠️ Channel was already deleted or not found.", success=False)
            await interaction.followup.send("⚠️ Channel not found on server.", ephemeral=True)
            return

        ch_name = channel.name
        try:
            await channel.delete(reason=f"Rai Incident Action: Deleted by Owner {interaction.user}")
            await self._update_dm_embed(interaction, f"✅ Successfully deleted channel `#{ch_name}` from **{guild.name}**.")
            await interaction.followup.send(f"✅ Deleted channel `#{ch_name}` from the server.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to delete channel from DM: {e}")
            await interaction.followup.send(f"❌ Failed to delete channel: {e}", ephemeral=True)

    async def _handle_lock_channel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            await interaction.followup.send("❌ Server not found.", ephemeral=True)
            return

        channel = guild.get_channel(self.target_id)
        if not channel:
            await interaction.followup.send("❌ Channel not found.", ephemeral=True)
            return

        try:
            # Deny @everyone sending and connecting
            await channel.set_permissions(
                guild.default_role,
                send_messages=False,
                connect=False,
                reason=f"Rai Incident Action: Locked by Owner {interaction.user}",
            )
            await self._update_dm_embed(interaction, f"🔒 Channel `#{channel.name}` has been locked (@everyone send/connect denied).")
            await interaction.followup.send(f"🔒 Channel `#{channel.name}` has been locked.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to lock channel: {e}", ephemeral=True)

    async def _handle_timeout_user(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = self.bot.get_guild(self.guild_id)
        uid = self.actor_id or self.target_id
        if not guild or not uid:
            await interaction.followup.send("❌ User or Guild not found.", ephemeral=True)
            return

        member = guild.get_member(uid)
        if not member:
            try:
                member = await guild.fetch_member(uid)
            except Exception:
                member = None

        if not member:
            await interaction.followup.send("❌ Member not found in server.", ephemeral=True)
            return

        try:
            await member.timeout(
                datetime.timedelta(hours=1),
                reason=f"Rai Incident Action: Timed out 1h by Owner {interaction.user}",
            )
            await self._update_dm_embed(interaction, f"⏳ Member {member.mention} (`{member.id}`) was timed out for 1 hour.")
            await interaction.followup.send(f"⏳ Timed out {member.name} for 1 hour.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to timeout user: {e}", ephemeral=True)

    async def _handle_kick_user(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = self.bot.get_guild(self.guild_id)
        uid = self.actor_id or self.target_id
        if not guild or not uid:
            await interaction.followup.send("❌ User not found.", ephemeral=True)
            return

        member = guild.get_member(uid)
        if not member:
            try:
                member = await guild.fetch_member(uid)
            except Exception:
                member = None

        if not member:
            await interaction.followup.send("❌ Member not found in server.", ephemeral=True)
            return

        try:
            await member.kick(reason=f"Rai Incident Action: Kicked by Owner {interaction.user}")
            await self._update_dm_embed(interaction, f"👢 Member `{member.name}` (`{member.id}`) was kicked from **{guild.name}**.")
            await interaction.followup.send(f"👢 Kicked {member.name} from the server.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to kick user: {e}", ephemeral=True)

    async def _handle_ban_user(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = self.bot.get_guild(self.guild_id)
        uid = self.actor_id or self.target_id
        if not guild or not uid:
            await interaction.followup.send("❌ User not found.", ephemeral=True)
            return

        try:
            await guild.ban(
                discord.Object(id=uid),
                reason=f"Rai Incident Action: Banned by Owner {interaction.user}",
                delete_message_days=1,
            )
            await self._update_dm_embed(interaction, f"🔨 User ID `{uid}` was permanently banned from **{guild.name}**.")
            await interaction.followup.send(f"🔨 Banned user `{uid}` from the server.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to ban user: {e}", ephemeral=True)

    async def _handle_delete_role(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = self.bot.get_guild(self.guild_id)
        if not guild or not self.target_id:
            await interaction.followup.send("❌ Role not found.", ephemeral=True)
            return

        role = guild.get_role(self.target_id)
        if not role:
            await interaction.followup.send("❌ Role not found.", ephemeral=True)
            return

        role_name = role.name
        try:
            await role.delete(reason=f"Rai Incident Action: Deleted by Owner {interaction.user}")
            await self._update_dm_embed(interaction, f"🗑️ Role `@{role_name}` was deleted from **{guild.name}**.")
            await interaction.followup.send(f"🗑️ Deleted role `@{role_name}`.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to delete role: {e}", ephemeral=True)

    async def _handle_mark_safe(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._update_dm_embed(interaction, "✅ Incident reviewed and marked as safe. Auto-deleting from DM...")
        try:
            await asyncio.sleep(2.0)
            if interaction.message:
                await interaction.message.delete()
        except Exception:
            pass

    async def _handle_mark_all_read(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cleared_count = 0

        # 1. Update the triggering message immediately to show progress
        self._disable_all_buttons()
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed(title="Incidents")
        embed.color = Colors.SUCCESS
        embed.add_field(
            name="🛡️ Founder Action Taken",
            value=f"✅ **All incident alerts marked as read & safe.**\n*Auto-deleting from DM...*",
            inline=False,
        )
        try:
            await interaction.message.edit(embed=embed, view=self)
        except Exception:
            pass

        # 2. Get tracked alerts
        tracked = IncidentAlertTracker.get_and_clear_alerts(self.owner_id)
        tracked_ids = {m.id for m in tracked if hasattr(m, "id")}

        # 3. Purge older redundant incident alert messages from the bot in DM
        channel = interaction.channel
        if channel:
            try:
                async for msg in channel.history(limit=75):
                    if msg.id == interaction.message.id:
                        continue
                    if msg.author.id == self.bot.user.id:
                        is_incident = msg.id in tracked_ids
                        if not is_incident and msg.embeds:
                            first_emb = msg.embeds[0]
                            emb_text = (first_emb.title or "") + (first_emb.footer.text if first_emb.footer else "")
                            if any(k in emb_text for k in ["Incident", "Channel Deleted", "AI Security Console", "Channel Created", "Member", "Role"]):
                                is_incident = True
                        if is_incident:
                            try:
                                await msg.delete()
                                cleared_count += 1
                                await asyncio.sleep(0.08)
                            except Exception:
                                pass
            except Exception as e:
                logger.error(f"Error purging older DM incident messages: {e}")

        # 4. Auto-delete the triggering message as well
        try:
            await asyncio.sleep(2.0)
            if interaction.message:
                await interaction.message.delete()
        except Exception:
            pass


async def handle_incident_interaction(bot: SentinelBot, interaction: discord.Interaction) -> bool:
    """
    Global interaction dispatcher for persistent AI incident action buttons.
    Ensures buttons function reliably across bot reboots and REST-dispatched consoles.
    """
    cid = interaction.data.get("custom_id", "")
    if not cid.startswith("inc_"):
        return False

    # 1. Authorize: Only guild owners / founder / administrators
    founder_id = 1457380609641938981
    is_authorized = (interaction.user.id == founder_id)
    if not is_authorized and interaction.guild:
        is_authorized = (interaction.user.id == getattr(interaction.guild, "owner_id", None))
    if not is_authorized and getattr(interaction.user, "guild_permissions", None) and getattr(interaction.user.guild_permissions, "administrator", False):
        is_authorized = True

    if not is_authorized:
        try:
            await interaction.response.send_message("❌ This incident console is private to the server owner.", ephemeral=True)
        except Exception:
            pass
        return True

    # Immediate deferral to prevent Discord 3-second interaction timeout
    if not interaction.response.is_done():
        try:
            await interaction.response.defer()
        except Exception:
            pass

        # Update current message
        cleared_count = 0
        if interaction.message:
            embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed(title="Incidents")
            embed.color = Colors.SUCCESS
            embed.add_field(
                name="🛡️ Founder Action Taken",
                value=f"✅ **All incident alerts marked as read and safe.**\n*Resolved by {interaction.user.mention}*",
                inline=False,
            )
            try:
                await interaction.message.edit(embed=embed, view=None)
            except Exception:
                pass

        # Purge past bot alerts in DM
        channel = interaction.channel
        if channel:
            try:
                async for msg in channel.history(limit=80):
                    if interaction.message and msg.id == interaction.message.id:
                        continue
                    if msg.author.id == bot.user.id:
                        is_inc = False
                        if msg.embeds:
                            first_emb = msg.embeds[0]
                            emb_text = (first_emb.title or "") + " " + (first_emb.footer.text if first_emb.footer else "")
                            if any(k in emb_text for k in ["Incident", "Channel Deleted", "AI Security Console", "Channel Created"]):
                                is_inc = True
                        if is_inc:
                            try:
                                await msg.delete()
                                cleared_count += 1
                                await asyncio.sleep(0.08)
                            except Exception:
                                pass
            except Exception as e:
                logger.error(f"Error purging older DM messages in persistent handler: {e}")

        # Auto-delete triggering message after purging
        try:
            await asyncio.sleep(2.0)
            if interaction.message:
                await interaction.message.delete()
        except Exception:
            pass
        return True

    # 3. Mark as Safe
    if cid == "inc_safe_ack":
        try:
            await interaction.response.defer()
        except Exception:
            pass
        if interaction.message:
            embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed(title="Incident")
            embed.color = Colors.SUCCESS
            embed.add_field(
                name="🛡️ Founder Action Taken",
                value=f"✅ Incident reviewed and marked as safe.\n*Auto-deleting from DM...*",
                inline=False,
            )
            try:
                await interaction.message.edit(embed=embed, view=None)
            except Exception:
                pass
        try:
            await asyncio.sleep(2.0)
            if interaction.message:
                await interaction.message.delete()
        except Exception:
            pass
        return True

    return False
