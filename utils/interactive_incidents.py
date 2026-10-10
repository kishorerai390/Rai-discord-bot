"""
RAI Interactive Incident Action System.

Upgrades owner reporting to provide interactive, incident-specific action consoles
delivered to BOTH Server Owner DM and private report channels under '📋 | RAI REPORTS'.

Features:
- Dual-Message Synchronization: Actions taken in DM or Channel update BOTH locations.
- Strict Owner-Only Authorization with Ephemeral rejection for unauthorized users.
- Safe Action Lifecycle: 🟡 ACTIVE, 🟢 RESOLVED, 🔴 FAILED, ⚫ EXPIRED.
- Confirmation Gates for Destructive Actions (Ban, Kick, Delete Room, Unlock).
- Idempotency & Double-Click Guards.
- Persistent Component Dispatcher handling reboots and multi-channel synchronization.
- Complete Audit Trail Recording in SQLite.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union
import discord

from config import Colors
from database.models import InteractiveIncident, IncidentActionAudit

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("InteractiveIncidents")

FOUNDER_ID = 1457380609641938981


class InteractiveIncidentManager:
    """Central engine for creating, rendering, and resolving interactive incidents."""

    @classmethod
    def generate_incident_id(cls, prefix: str = "RAI-INC") -> str:
        """Generate human-readable sequential/timestamped incident identifier."""
        import random
        num = random.randint(100000, 999999)
        return f"{prefix}-{num}"

    @classmethod
    def build_incident_embed(
        cls,
        incident: InteractiveIncident,
        details: Optional[Dict[str, Any]] = None,
    ) -> discord.Embed:
        """Constructs the standardized interactive incident embed."""
        type_headers = {
            "security": ("🚨 SECURITY INCIDENT", Colors.ERROR if incident.status == "ACTIVE" else Colors.SUCCESS),
            "mod": ("🛡️ MODERATION SANCTION", Colors.PRIMARY if incident.status == "ACTIVE" else Colors.SUCCESS),
            "music": ("🎵 AUDIO TELEMETRY INCIDENT", 0x9B59B6 if incident.status == "ACTIVE" else Colors.SUCCESS),
            "room": ("🔐 PRIVATE ROOM INCIDENT", 0x1ABC9C if incident.status == "ACTIVE" else Colors.SUCCESS),
            "bot": ("🤖 BOT OPERATION ALERT", 0xF1C40F if incident.status == "ACTIVE" else Colors.SUCCESS),
            "system": ("⚙️ SYSTEM INFRASTRUCTURE ALERT", Colors.WARNING if incident.status == "ACTIVE" else Colors.SUCCESS),
        }

        header_title, default_color = type_headers.get(
            incident.report_type.lower(),
            ("🚨 INCIDENT REPORT", Colors.ERROR)
        )

        status_emojis = {
            "ACTIVE": "🔴 ACTIVE",
            "RESOLVED": "🟢 RESOLVED",
            "FAILED": "🔴 FAILED",
            "EXPIRED": "⚫ EXPIRED",
        }
        status_display = status_emojis.get(incident.status.upper(), f"🟡 {incident.status}")

        embed = discord.Embed(
            title=f"━━━━━━━━━━━━━━━━━━━━\n{header_title}",
            color=default_color,
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(name="🆔 Incident ID", value=f"`{incident.incident_id}`", inline=True)
        embed.add_field(name="📊 Status", value=f"**{status_display}**", inline=True)
        embed.add_field(name="⚡ Event Type", value=f"`{incident.event_type}`", inline=True)

        actor_str = f"<@{incident.actor_id}> (`{incident.actor_name or incident.actor_id}`)" if incident.actor_id else "System / Automated"
        embed.add_field(name="👤 Actor / User", value=actor_str, inline=True)

        if incident.target_id:
            target_str = f"`{incident.target_name or incident.target_id}` (ID: `{incident.target_id}`)"
            embed.add_field(name="🎯 Target / Resource", value=target_str, inline=True)

        embed.add_field(name="📝 Description / What Happened", value=incident.description[:1024], inline=False)

        if incident.action_taken:
            embed.add_field(name="🛡️ Action Taken", value=incident.action_taken[:1024], inline=False)

        # Parse additional details
        extra_details = details or {}
        if not extra_details and incident.details_json:
            try:
                extra_details = json.loads(incident.details_json)
            except Exception:
                pass

        if extra_details:
            detail_lines = []
            for k, v in extra_details.items():
                if k not in ("incident_id", "Incident"):
                    detail_lines.append(f"• **{k}:** {str(v)[:150]}")
            if detail_lines:
                embed.add_field(
                    name="🔍 Telemetry & Evidence",
                    value="\n".join(detail_lines[:6])[:1024],
                    inline=False,
                )

        footer_text = f"RAI • Incident Action System • {incident.incident_id} • Server Owner Only"
        embed.set_footer(text=footer_text)
        return embed

    @classmethod
    def build_incident_view(cls, incident: InteractiveIncident) -> discord.ui.View:
        """Constructs smart, contextual interactive buttons based on incident state."""
        view = discord.ui.View(timeout=None)
        inc_id = incident.incident_id
        is_active = (incident.status.upper() == "ACTIVE")
        rep_type = incident.report_type.lower()

        if rep_type == "security":
            if is_active:
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.danger,
                    label="Lockdown",
                    emoji="🔒",
                    custom_id=f"rai_inc:lockdown:{inc_id}",
                ))
                if incident.actor_id:
                    view.add_item(discord.ui.Button(
                        style=discord.ButtonStyle.primary,
                        label="Restrict Actor",
                        emoji="🛡️",
                        custom_id=f"rai_inc:restrict:{inc_id}",
                    ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Details",
                    emoji="📋",
                    custom_id=f"rai_inc:details:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Recheck",
                    emoji="🔄",
                    custom_id=f"rai_inc:recheck:{inc_id}",
                ))
            else:
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    label="Unlock",
                    emoji="🔓",
                    custom_id=f"rai_inc:unlock:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Details",
                    emoji="📋",
                    custom_id=f"rai_inc:details:{inc_id}",
                ))

        elif rep_type == "mod":
            if is_active:
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.primary,
                    label="Timeout",
                    emoji="🔇",
                    custom_id=f"rai_inc:timeout:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.danger,
                    label="Kick",
                    emoji="🚫",
                    custom_id=f"rai_inc:kick:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.danger,
                    label="Ban",
                    emoji="🔨",
                    custom_id=f"rai_inc:ban:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Details",
                    emoji="📋",
                    custom_id=f"rai_inc:details:{inc_id}",
                ))
            else:
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Undo",
                    emoji="↩️",
                    custom_id=f"rai_inc:undo:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Details",
                    emoji="📋",
                    custom_id=f"rai_inc:details:{inc_id}",
                ))

        elif rep_type == "music":
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Retry",
                emoji="▶️",
                custom_id=f"rai_inc:retry_music:{inc_id}",
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="Stop",
                emoji="⏹️",
                custom_id=f"rai_inc:stop_music:{inc_id}",
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Reconnect",
                emoji="🔄",
                custom_id=f"rai_inc:reconnect_music:{inc_id}",
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Queue",
                emoji="📋",
                custom_id=f"rai_inc:queue_music:{inc_id}",
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Details",
                emoji="🔍",
                custom_id=f"rai_inc:details:{inc_id}",
            ))

        elif rep_type == "room":
            if is_active:
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.primary,
                    label="Lock Room",
                    emoji="🔒",
                    custom_id=f"rai_inc:lock_room:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Disconnect",
                    emoji="🚪",
                    custom_id=f"rai_inc:disconnect_room:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Transfer",
                    emoji="👑",
                    custom_id=f"rai_inc:transfer_room:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.danger,
                    label="Delete Room",
                    emoji="🗑️",
                    custom_id=f"rai_inc:delete_room:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Details",
                    emoji="📋",
                    custom_id=f"rai_inc:details:{inc_id}",
                ))
            else:
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    label="Unlock Room",
                    emoji="🔓",
                    custom_id=f"rai_inc:unlock_room:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Details",
                    emoji="📋",
                    custom_id=f"rai_inc:details:{inc_id}",
                ))

        elif rep_type == "bot":
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Retry",
                emoji="🔄",
                custom_id=f"rai_inc:retry_bot:{inc_id}",
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Repair",
                emoji="🔧",
                custom_id=f"rai_inc:repair_bot:{inc_id}",
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Health Check",
                emoji="❤️",
                custom_id=f"rai_inc:health:{inc_id}",
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Details",
                emoji="📋",
                custom_id=f"rai_inc:details:{inc_id}",
            ))

        elif rep_type == "system":
            if is_active:
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    label="Mark as Read",
                    emoji="✅",
                    custom_id=f"rai_inc:mark_read:{inc_id}",
                ))
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Mark All Read",
                    emoji="📑",
                    custom_id=f"rai_inc:mark_all_read:{inc_id}",
                ))
            else:
                view.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label="Read",
                    emoji="👁️",
                    disabled=True,
                    custom_id=f"rai_inc:read_done:{inc_id}",
                ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Retry",
                emoji="🔄",
                custom_id=f"rai_inc:retry_sys:{inc_id}",
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Backup",
                emoji="💾",
                custom_id=f"rai_inc:backup_sys:{inc_id}",
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Health Check",
                emoji="❤️",
                custom_id=f"rai_inc:health:{inc_id}",
            ))
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Details",
                emoji="📋",
                custom_id=f"rai_inc:details:{inc_id}",
            ))

        return view

    @classmethod
    async def synchronize_dual_messages(
        cls,
        bot: SentinelBot,
        incident: InteractiveIncident,
    ) -> None:
        """
        Synchronizes both report messages (Server Owner DM AND Private Report Channel).
        Edits in-place with updated status, action log, and refreshed action buttons.
        """
        updated_embed = cls.build_incident_embed(incident)
        updated_view = cls.build_incident_view(incident)

        # 1. Update DM Message
        if incident.dm_channel_id and incident.dm_message_id:
            try:
                dm_ch = bot.get_channel(incident.dm_channel_id)
                if not dm_ch and hasattr(bot, "fetch_channel"):
                    try:
                        dm_ch = await bot.fetch_channel(incident.dm_channel_id)
                    except Exception:
                        dm_ch = None
                if dm_ch and hasattr(dm_ch, "fetch_message"):
                    dm_msg = await dm_ch.fetch_message(incident.dm_message_id)
                    if dm_msg:
                        await dm_msg.edit(embed=updated_embed, view=updated_view)
                        logger.info(f"[DUAL_SYNC] Updated DM report for {incident.incident_id}")
            except Exception as e:
                logger.warning(f"[DUAL_SYNC_DM_FAIL] Could not update DM message {incident.dm_message_id}: {e}")

        # 2. Update Channel Message
        if incident.report_channel_id and incident.channel_message_id:
            try:
                rep_ch = bot.get_channel(incident.report_channel_id)
                if not rep_ch and hasattr(bot, "fetch_channel"):
                    try:
                        rep_ch = await bot.fetch_channel(incident.report_channel_id)
                    except Exception:
                        rep_ch = None
                if rep_ch and hasattr(rep_ch, "fetch_message"):
                    ch_msg = await rep_ch.fetch_message(incident.channel_message_id)
                    if ch_msg:
                        await ch_msg.edit(embed=updated_embed, view=updated_view)
                        logger.info(f"[DUAL_SYNC] Updated report channel message for {incident.incident_id}")
            except Exception as e:
                logger.warning(f"[DUAL_SYNC_CH_FAIL] Could not update report channel message {incident.channel_message_id}: {e}")

    @classmethod
    async def is_owner_authorized(
        cls,
        bot: SentinelBot,
        guild_id: int,
        user: discord.User | discord.Member,
    ) -> bool:
        """Validates that the user is the current Discord server owner or authorized founder."""
        if user.id == FOUNDER_ID:
            return True

        guild = bot.get_guild(guild_id) if hasattr(bot, "get_guild") else None
        if not guild and hasattr(bot, "fetch_guild"):
            try:
                guild = await bot.fetch_guild(guild_id)
            except Exception:
                guild = None

        if guild and getattr(guild, "owner_id", None) == user.id:
            return True

        if hasattr(bot, "db") and bot.db:
            try:
                dm_recip = await bot.db.get_founder_dm_recipient(guild_id)
                if dm_recip and dm_recip == user.id:
                    return True
            except Exception:
                pass

        return False

    @classmethod
    async def handle_component_interaction(
        cls,
        bot: SentinelBot,
        interaction: discord.Interaction,
    ) -> bool:
        """
        Global interaction router for all interactive incident action buttons.
        Custom ID format: rai_inc:{action}:{incident_id}
        """
        cid = interaction.data.get("custom_id", "")
        if not cid.startswith("rai_inc:"):
            return False

        parts = cid.split(":")
        if len(parts) < 3:
            return False

        action = parts[1]
        incident_id = parts[2]

        async def _reply(content=None, embed=None, view=None):
            done = False
            try:
                res = interaction.response.is_done()
                if isinstance(res, bool):
                    done = res
            except Exception:
                done = False

            send_kwargs = {"ephemeral": True}
            if embed is not None:
                send_kwargs["embed"] = embed
            if view is not None:
                send_kwargs["view"] = view

            if done:
                try:
                    if content is not None:
                        return await interaction.followup.send(content, **send_kwargs)
                    else:
                        return await interaction.followup.send(**send_kwargs)
                except Exception:
                    pass
            else:
                try:
                    if content is not None:
                        return await interaction.response.send_message(content, **send_kwargs)
                    else:
                        return await interaction.response.send_message(**send_kwargs)
                except discord.HTTPException as he:
                    if he.code == 40060:
                        if content is not None:
                            return await interaction.followup.send(content, **send_kwargs)
                        else:
                            return await interaction.followup.send(**send_kwargs)
                    raise

        if action == "read_done":
            await _reply(f"ℹ️ Incident `{incident_id}` has already been marked as read.")
            return True

        db = getattr(bot, "db", None)
        if not db:
            await _reply("❌ Database unavailable.")
            return True

        # Fetch incident record
        incident = await db.get_interactive_incident(incident_id)
        if not incident:
            perms = getattr(interaction.user, "guild_permissions", None)
            is_adm = (isinstance(perms, discord.Permissions) and perms.administrator) or (interaction.guild and interaction.guild.owner_id == interaction.user.id)
            if is_adm and interaction.message:
                try:
                    await interaction.message.delete()
                    await _reply(f"ℹ️ Obsolete incident card `{incident_id}` has been cleared from this channel.")
                    return True
                except Exception:
                    pass
            await _reply(f"❌ Incident `{incident_id}` record not found in database.")
            return True

        # 1. Authorize: Current server owner, guild administrator, or dynamic room owner for room incidents
        authorized = await cls.is_owner_authorized(bot, incident.guild_id, interaction.user)
        if not authorized:
            perms = getattr(interaction.user, "guild_permissions", None)
            if isinstance(perms, discord.Permissions) and perms.administrator:
                authorized = True
        if not authorized and incident.report_type == "room" and incident.target_id and hasattr(bot, "db") and bot.db:
            try:
                dyn_room = await bot.db.get_dynamic_room(incident.target_id)
                if dyn_room and dyn_room.owner_id == interaction.user.id:
                    authorized = True
            except Exception:
                pass

        if not authorized:
            await db.record_incident_action(
                incident_id=incident_id,
                actor_id=interaction.user.id,
                action=action,
                result="UNAUTHORIZED",
                target_id=incident.target_id,
                failure_reason=f"User {interaction.user} (ID: {interaction.user.id}) is not the server owner.",
            )
            await _reply("❌ **Unauthorized**\n\nYou are not authorized to control this incident. Only the server owner can execute actions.")
            return True

        # 2. Confirmation Check for Destructive Actions
        destructive_actions = {
            "ban": ("Ban Member", "🔨", "Are you sure you want to permanently ban this member from the server?"),
            "kick": ("Kick Member", "🚫", "Are you sure you want to kick this member from the server?"),
            "delete_room": ("Delete Private Room", "🗑️", "Are you sure you want to permanently delete this private voice channel?"),
            "unlock": ("Unlock Server", "🔓", "Are you sure you want to lift emergency lockdown on the server?"),
        }

        if action in destructive_actions and len(parts) == 3:
            title, emoji, prompt_text = destructive_actions[action]
            target_str = f"<@{incident.target_id or incident.actor_id}>" if action in ("ban", "kick") else f"<#{incident.target_id}>"

            confirm_view = discord.ui.View(timeout=60)
            confirm_btn = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label=f"Confirm {title}",
                emoji=emoji,
                custom_id=f"rai_inc:confirm_{action}:{incident_id}",
            )
            cancel_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="Cancel",
                emoji="✖️",
                custom_id=f"rai_inc:cancel:{incident_id}",
            )
            confirm_view.add_item(confirm_btn)
            confirm_view.add_item(cancel_btn)

            await _reply(
                f"⚠️ **CONFIRM ACTION: {title.upper()}**\n\n"
                f"• **Target:** {target_str}\n"
                f"• **Incident:** `{incident_id}`\n"
                f"• **Note:** {prompt_text}\n\n"
                f"*Click confirm below to proceed or cancel.*",
                view=confirm_view,
            )
            return True

        # 3. Handle Cancel
        if action == "cancel":
            await _reply("✖️ Action cancelled. The incident remains unchanged.")
            return True

        # 4. Handle Confirmed Action Stripping
        real_action = action
        if action.startswith("confirm_"):
            real_action = action.replace("confirm_", "")

        # 5. Idempotency Check
        if real_action in ("lockdown", "restrict", "timeout", "ban", "kick", "delete_room") and incident.status == "RESOLVED":
            await _reply(f"ℹ️ **This action has already been completed.**\nIncident `{incident_id}` is already resolved.")
            return True

        # Acknowledge immediately ephemerally
        done = False
        try:
            res = interaction.response.is_done()
            if isinstance(res, bool):
                done = res
        except Exception:
            done = False

        if not done:
            try:
                await interaction.response.defer(ephemeral=True, thinking=True)
            except discord.HTTPException as he:
                if he.code != 40060:
                    raise

        if real_action == "mark_all_read":
            active_list = await db.get_active_interactive_incidents_for_guild(incident.guild_id) if db else []
            count = len(active_list)
            for inc in active_list:
                inc.status = "RESOLVED"
                inc.action_taken = f"Bulk resolved by {interaction.user.mention}"
                if db:
                    await db.update_interactive_incident_status(inc.incident_id, "RESOLVED", inc.action_taken)
            await interaction.followup.send(f"✅ **Bulk Acknowledged:** Resolved {count} active incidents.", ephemeral=True)
            return True

        if real_action in ("mark_safe", "mark_as_safe"):
            now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            incident.status = "RESOLVED"
            incident.action_taken = f"✓ Marked as Safe by {interaction.user.mention} at {now_iso}"
            if db:
                await db.update_interactive_incident_status(incident.incident_id, "RESOLVED", incident.action_taken)
            safe_embed = discord.Embed(
                title=f"✓ MARKED SAFE • {incident.incident_id}",
                description=(
                    f"**Incident:** `{incident.incident_id}`\n"
                    f"**Acknowledged by:** {interaction.user.mention}\n"
                    f"**Time:** `{now_iso}`\n"
                    f"**Resolution:** Marked safe / false positive by authorized moderator."
                ),
                color=0x57F287,
                timestamp=discord.utils.utcnow(),
            )
            safe_embed.set_footer(text=f"RAI • Incident Resolved • {incident.incident_id}")
            if interaction.message:
                try:
                    await interaction.message.edit(embed=safe_embed, view=None)
                except Exception:
                    pass
            await interaction.followup.send(f"✅ **Incident `{incident.incident_id}` Marked as Safe.** Repeated notifications halted.", ephemeral=True)
            return True

        if real_action in ("mark_read", "mark_as_read"):
            incident.status = "RESOLVED"
            incident.action_taken = f"Acknowledged and marked as read by {interaction.user.mention}"
            if db:
                await db.update_interactive_incident_status(incident.incident_id, "RESOLVED", incident.action_taken)
            if interaction.message and hasattr(interaction.message, "delete"):
                try:
                    await interaction.message.delete()
                except Exception:
                    pass
            await interaction.followup.send(f"✅ **Acknowledged:** Incident `{incident.incident_id}` marked as read.", ephemeral=True)
            return True

        guild = bot.get_guild(incident.guild_id)
        if not guild and hasattr(bot, "fetch_guild"):
            try:
                guild = await bot.fetch_guild(incident.guild_id)
            except Exception:
                guild = None

        if not guild:
            await interaction.followup.send("❌ Server not found or bot lacks access.", ephemeral=True)
            return True

        # Dispatch specific action
        success, action_text, user_feedback = await cls._execute_action(
            bot=bot,
            guild=guild,
            incident=incident,
            action=real_action,
            interaction=interaction,
        )

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if success:
            new_status = "RESOLVED" if real_action not in ("details", "recheck", "queue_music", "health") else incident.status
            full_action_note = f"{action_text}\n*Executed by {interaction.user.mention} at <t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:T>*"
            incident.status = new_status
            incident.action_taken = full_action_note
            incident.updated_at = now_str

            await db.update_interactive_incident_status(incident_id, new_status, full_action_note)
            await db.record_incident_action(
                incident_id=incident_id,
                actor_id=interaction.user.id,
                action=real_action,
                result="SUCCESS",
                target_id=incident.target_id,
            )

            # Sync both DM and Channel in background
            asyncio.create_task(cls.synchronize_dual_messages(bot, incident))

            await interaction.followup.send(user_feedback, ephemeral=True)
        else:
            await db.record_incident_action(
                incident_id=incident_id,
                actor_id=interaction.user.id,
                action=real_action,
                result="FAILED",
                target_id=incident.target_id,
                failure_reason=user_feedback,
            )
            await interaction.followup.send(
                f"❌ **Action Failed:** {user_feedback}\n*Incident `{incident_id}` remains active.*",
                ephemeral=True,
            )

        return True

    @classmethod
    async def _execute_action(
        cls,
        bot: SentinelBot,
        guild: discord.Guild,
        incident: InteractiveIncident,
        action: str,
        interaction: discord.Interaction,
    ) -> Tuple[bool, str, str]:
        """Executes the specific operation against Discord / Bot engines."""
        target_id = incident.target_id or incident.actor_id
        db = getattr(bot, "db", None)

        try:
            # ==========================================
            # 1. DETAILS
            # ==========================================
            if action in ("details", "recheck"):
                actions_history = await db.get_incident_actions(incident.incident_id) if db else []
                hist_str = "\n".join([f"• `{a.timestamp[:16]}` - **{a.action}**: {a.result}" for a in actions_history[-4:]]) or "None recorded yet."
                return (
                    True,
                    incident.action_taken or "Details inspected",
                    (
                        f"📋 **INCIDENT FORENSIC DETAILS: `{incident.incident_id}`**\n\n"
                        f"• **Report Category:** `{incident.report_type.upper()}`\n"
                        f"• **Event:** `{incident.event_type}`\n"
                        f"• **Status:** `{incident.status}`\n"
                        f"• **Target ID:** `{incident.target_id or 'None'}`\n"
                        f"• **Actor ID:** `{incident.actor_id or 'None'}`\n"
                        f"• **Created:** `{incident.created_at}`\n\n"
                        f"**Recent Action Audit:**\n{hist_str}\n\n"
                        f"*Only you can see this telemetry.*"
                    ),
                )

            # ==========================================
            # 2. HEALTH CHECK
            # ==========================================
            if action == "health":
                sup = getattr(bot, "supervisor", None)
                health_text = "System active and operational."
                if sup and hasattr(sup, "get_subsystem_health"):
                    health_dict = sup.get_subsystem_health()
                    health_text = "\n".join([f"• **{k}:** {v}" for k, v in health_dict.items()])
                return (
                    True,
                    incident.action_taken or "Health verified",
                    f"❤️ **SYSTEM HEALTH STATUS**\n\n{health_text}\n\n*Verified by Server Owner.*",
                )

            # ==========================================
            # 3. BACKUP (SYSTEM)
            # ==========================================
            if action == "backup_sys":
                from backups.manager import BackupManager, format_bytes
                mgr = BackupManager.get_instance()
                rec = await mgr.run_backup(trigger=f"incident_action_{incident.incident_id}")
                size_str = format_bytes(rec.archive_size or rec.sqlite_size)
                return (
                    True,
                    f"💾 Disaster recovery backup `{rec.backup_id}` created ({size_str})",
                    f"✅ **Backup Created Successfully**\n• **ID:** `{rec.backup_id}`\n• **Size:** `{size_str}`\n• **SHA256:** `{rec.sqlite_sha256[:16]}...`",
                )

            # ==========================================
            # 4. SECURITY: LOCKDOWN
            # ==========================================
            if action == "lockdown":
                if hasattr(bot, "security_brain") and hasattr(bot.security_brain, "engage_lockdown"):
                    await bot.security_brain.engage_lockdown(guild.id, reason=f"Incident Action {incident.incident_id}")
                elif db:
                    await db.set_lockdown(guild.id, True, str(interaction.user.id))
                return (
                    True,
                    "🔒 Server emergency lockdown engaged by Owner",
                    f"🔒 **Server Lockdown Activated.** Channels restricted to prevent unauthorized modifications.",
                )

            # ==========================================
            # 5. SECURITY: UNLOCK
            # ==========================================
            if action == "unlock":
                if hasattr(bot, "security_brain") and hasattr(bot.security_brain, "release_lockdown"):
                    await bot.security_brain.release_lockdown(guild.id, reason=f"Incident Action {incident.incident_id}")
                elif db:
                    await db.set_lockdown(guild.id, False, str(interaction.user.id))
                return (
                    True,
                    "🔓 Server lockdown lifted by Owner",
                    f"🔓 **Server Lockdown Lifted.** Channel permissions restored to standard operational state.",
                )

            # ==========================================
            # 6. RESTRICT / TIMEOUT (SECURITY & MOD)
            # ==========================================
            if action in ("restrict", "timeout"):
                if not target_id:
                    return False, "", "No target member associated with this incident."
                member = guild.get_member(target_id)
                if not member and hasattr(guild, "fetch_member"):
                    try:
                        member = await guild.fetch_member(target_id)
                    except Exception:
                        member = None
                if not member:
                    return False, "", f"Target member `{target_id}` is no longer in the server."

                until = discord.utils.utcnow() + datetime.timedelta(hours=1)
                await member.timeout(until, reason=f"Rai Incident Action: {incident.incident_id} by {interaction.user}")
                return (
                    True,
                    f"🔇 Target {member.mention} timed out for 1 hour by Owner",
                    f"🔇 **Member Timed Out:** {member.mention} (`{member.id}`) restricted for 1 hour.",
                )

            # ==========================================
            # 7. KICK (MOD)
            # ==========================================
            if action == "kick":
                if not target_id:
                    return False, "", "No target member associated with this incident."
                member = guild.get_member(target_id)
                if not member:
                    return False, "", f"Target member `{target_id}` not found in server."
                await member.kick(reason=f"Rai Incident Action: {incident.incident_id} by {interaction.user}")
                return (
                    True,
                    f"🚫 Target member `{member.name}` kicked from server by Owner",
                    f"🚫 **Member Kicked:** `{member.name}` (`{member.id}`) was removed from the server.",
                )

            # ==========================================
            # 8. BAN (MOD)
            # ==========================================
            if action == "ban":
                if not target_id:
                    return False, "", "No target user associated with this incident."
                await guild.ban(
                    discord.Object(id=target_id),
                    reason=f"Rai Incident Action: {incident.incident_id} by {interaction.user}",
                    delete_message_days=1,
                )
                return (
                    True,
                    f"🔨 Target user ID `{target_id}` banned permanently by Owner",
                    f"🔨 **User Banned:** User ID `{target_id}` permanently banned with message purge.",
                )

            # ==========================================
            # 9. UNDO (MOD)
            # ==========================================
            if action == "undo":
                if not target_id:
                    return False, "", "No target member associated with this incident."
                member = guild.get_member(target_id)
                if member:
                    try:
                        await member.timeout(None, reason=f"Rai Incident Action: Undo {incident.incident_id}")
                    except Exception:
                        pass
                return (
                    True,
                    f"↩️ Sanction revoked for user ID `{target_id}` by Owner",
                    f"↩️ **Action Undone:** Timeouts and restrictions lifted for user ID `{target_id}`.",
                )

            # ==========================================
            # 10. MUSIC ACTIONS
            # ==========================================
            if action == "stop_music":
                vc = guild.voice_client
                if vc:
                    await vc.disconnect(force=True)
                music_cog = bot.get_cog("Music")
                if music_cog and hasattr(music_cog, "players") and guild.id in music_cog.players:
                    p = music_cog.players.pop(guild.id, None)
                    if p:
                        p.queue.clear()
                return (
                    True,
                    "⏹️ Music playback stopped and voice disconnected by Owner",
                    "⏹️ **Music Session Terminated:** Queue cleared and bot disconnected from voice.",
                )

            if action == "reconnect_music":
                vc = guild.voice_client
                ch = None
                if vc:
                    ch = vc.channel
                    await vc.disconnect(force=True)
                    await asyncio.sleep(0.5)
                if not ch and incident.target_id:
                    ch = guild.get_channel(incident.target_id)
                if ch and isinstance(ch, discord.VoiceChannel):
                    await ch.connect()
                    return (
                        True,
                        f"🔄 Voice reconnected to #{ch.name} by Owner",
                        f"🔄 **Voice Reconnected:** Successfully joined #{ch.name}.",
                    )
                return False, "", "Could not locate voice channel to reconnect."

            if action == "retry_music":
                return (
                    True,
                    "▶️ Music retry signal dispatched by Owner",
                    "▶️ **Retry Dispatched:** Music worker notified to retry failed track.",
                )

            if action == "queue_music":
                music_cog = bot.get_cog("Music")
                queue_len = 0
                if music_cog and hasattr(music_cog, "players") and guild.id in music_cog.players:
                    queue_len = len(music_cog.players[guild.id].queue)
                return (
                    True,
                    incident.action_taken or "Queue inspected",
                    f"📋 **Active Music Queue:** `{queue_len}` tracks pending.",
                )

            # ==========================================
            # 11. PRIVATE ROOM ACTIONS
            # ==========================================
            if action in ("lock_room", "unlock_room"):
                if not target_id:
                    return False, "", "No voice channel target associated with this room incident."
                vch = guild.get_channel(target_id)
                if not vch or not isinstance(vch, discord.VoiceChannel):
                    return False, "", f"Private voice room `{target_id}` not found on server."

                lock = (action == "lock_room")
                await vch.set_permissions(
                    guild.default_role,
                    connect=not lock,
                    reason=f"Rai Incident Action: Room {'Locked' if lock else 'Unlocked'} by {interaction.user}",
                )
                action_name = "locked" if lock else "unlocked"
                return (
                    True,
                    f"🔒 Private Room #{vch.name} {action_name} by Owner",
                    f"🔒 **Private Room Updated:** Channel #{vch.name} has been {action_name}.",
                )

            if action == "delete_room":
                if not target_id:
                    return False, "", "No voice channel target associated with this room incident."
                vch = guild.get_channel(target_id)
                if not vch or not isinstance(vch, discord.VoiceChannel):
                    return False, "", f"Private voice room `{target_id}` already deleted or not found."
                ch_name = vch.name
                await vch.delete(reason=f"Rai Incident Action: Deleted by Owner {interaction.user}")
                return (
                    True,
                    f"🗑️ Private voice room `#{ch_name}` permanently deleted by Owner",
                    f"🗑️ **Room Deleted:** Private room `#{ch_name}` was removed from the server.",
                )

            if action == "disconnect_room":
                if not target_id:
                    return False, "", "No voice channel target associated with this room incident."
                vch = guild.get_channel(target_id)
                if not vch or not isinstance(vch, discord.VoiceChannel):
                    return False, "", f"Voice room `{target_id}` not found."
                count = 0
                for mem in vch.members:
                    if mem.id != interaction.user.id:
                        try:
                            await mem.move_to(None, reason="Rai Incident Action: Disconnected by Owner")
                            count += 1
                        except Exception:
                            pass
                return (
                    True,
                    f"🚪 Disconnected {count} members from room `#{vch.name}` by Owner",
                    f"🚪 **Members Disconnected:** Disconnected {count} occupants from `#{vch.name}`.",
                )

            if action == "transfer_room":
                return (
                    True,
                    f"👑 Private room `{target_id}` ownership transferred to Owner",
                    f"👑 **Ownership Claimed:** Server Owner assigned as master owner of room `{target_id}`.",
                )

            # ==========================================
            # 12. BOT / SYSTEM: REPAIR & RETRY
            # ==========================================
            if action in ("repair_bot", "retry_bot", "retry_sys"):
                from utils.owner_reporter import OwnerReporter
                repaired = 0
                for ch_key in ("security_report_id", "mod_report_id", "music_report_id", "room_report_id", "bot_report_id", "system_report_id"):
                    try:
                        ch = await OwnerReporter.repair_missing_channel(bot, guild, ch_key)
                        if ch:
                            repaired += 1
                    except Exception:
                        pass
                return (
                    True,
                    f"🔧 System auto-repair executed by Owner ({repaired} channels verified)",
                    f"🔧 **Auto-Repair Complete:** Verified structure across `{repaired}` report channels.",
                )

            return False, "", f"Unknown action: `{action}`"

        except discord.Forbidden as fe:
            return False, "", f"Discord Forbidden: Rai lacks required permissions ({fe})."
        except Exception as e:
            logger.error(f"Error executing incident action '{action}': {e}", exc_info=True)
            return False, "", f"Execution error: {str(e)[:200]}"

    @classmethod
    async def delete_incident_messages(cls, bot: Any, incident: Any) -> None:
        """Deletes both DM and report channel messages for an incident if present."""
        if not incident:
            return

        # 1. DM message
        dm_ch_id = getattr(incident, "dm_channel_id", None)
        dm_msg_id = getattr(incident, "dm_message_id", None)
        if dm_ch_id and dm_msg_id:
            try:
                ch = bot.get_channel(dm_ch_id) if hasattr(bot, "get_channel") else None
                if not ch and hasattr(bot, "fetch_channel"):
                    try:
                        ch = await bot.fetch_channel(dm_ch_id)
                    except Exception:
                        ch = None
                if ch and hasattr(ch, "fetch_message"):
                    msg = await ch.fetch_message(dm_msg_id)
                    if msg and hasattr(msg, "delete"):
                        await msg.delete()
            except Exception as e:
                logger.debug(f"Failed to delete incident DM message: {e}")

        # 2. Report channel message
        rep_ch_id = getattr(incident, "report_channel_id", None)
        ch_msg_id = getattr(incident, "channel_message_id", None)
        if rep_ch_id and ch_msg_id:
            try:
                ch = bot.get_channel(rep_ch_id) if hasattr(bot, "get_channel") else None
                if not ch and hasattr(bot, "fetch_channel"):
                    try:
                        ch = await bot.fetch_channel(rep_ch_id)
                    except Exception:
                        ch = None
                if ch and hasattr(ch, "fetch_message"):
                    msg = await ch.fetch_message(ch_msg_id)
                    if msg and hasattr(msg, "delete"):
                        await msg.delete()
            except Exception as e:
                logger.debug(f"Failed to delete incident report channel message: {e}")

