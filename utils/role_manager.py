"""
Central Role Manager for the Rai Discord Bot.
Handles idempotent role hierarchy creation, safe assignment, hierarchy validation,
self-healing, database synchronization, and audit logging.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple
import discord

if TYPE_CHECKING:
    from main import SentinelBot
    from database.models import GuildRole

logger = logging.getLogger("RaiRoleManager")

# System role definitions across STAFF, BOT, COMMUNITY, and SECURITY categories
ROLE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # STAFF
    "server_owner": {
        "name": "👑 Server Owner",
        "type": "STAFF",
        "color": 0xF1C40F,
        "hoist": True,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": False,
        "match_keywords": ["server owner", "owner", "founder"],
    },
    "head_admin": {
        "name": "🛡️ Head Administrator",
        "type": "STAFF",
        "color": 0xE74C3C,
        "hoist": True,
        "mentionable": True,
        "permissions": discord.Permissions(
            ban_members=True,
            kick_members=True,
            manage_roles=True,
            manage_channels=True,
            manage_guild=True,
            view_audit_log=True,
        ),
        "can_auto_assign": False,
        "match_keywords": ["head admin", "head administrator", "chief admin"],
    },
    "admin": {
        "name": "⚡ Administrator",
        "type": "STAFF",
        "color": 0xE67E22,
        "hoist": True,
        "mentionable": True,
        "permissions": discord.Permissions(
            ban_members=True,
            kick_members=True,
            manage_roles=True,
            manage_channels=True,
            view_audit_log=True,
        ),
        "can_auto_assign": False,
        "match_keywords": ["administrator", "admin"],
    },
    "moderator": {
        "name": "🔧 Moderator",
        "type": "STAFF",
        "color": 0x3498DB,
        "hoist": True,
        "mentionable": True,
        "permissions": discord.Permissions(
            kick_members=True,
            moderate_members=True,
            manage_messages=True,
            mute_members=True,
            deafen_members=True,
        ),
        "can_auto_assign": False,
        "match_keywords": ["moderator", "mod"],
    },
    "junior_mod": {
        "name": "🔨 Junior Moderator",
        "type": "STAFF",
        "color": 0x2ECC71,
        "hoist": True,
        "mentionable": True,
        "permissions": discord.Permissions(
            moderate_members=True,
            manage_messages=True,
        ),
        "can_auto_assign": False,
        "match_keywords": ["junior mod", "jr mod", "trial mod"],
    },
    "security_team": {
        "name": "🚨 Security Team",
        "type": "STAFF",
        "color": 0x9B59B6,
        "hoist": True,
        "mentionable": True,
        "permissions": discord.Permissions(
            moderate_members=True,
            view_audit_log=True,
        ),
        "can_auto_assign": False,
        "match_keywords": ["security team", "security", "guard"],
    },
    "support_team": {
        "name": "🎫 Support Team",
        "type": "STAFF",
        "color": 0x1ABC9C,
        "hoist": True,
        "mentionable": True,
        "permissions": discord.Permissions(
            manage_messages=True,
        ),
        "can_auto_assign": False,
        "match_keywords": ["support team", "support", "ticket support"],
    },
    "trial_staff": {
        "name": "🕵️ Trial Staff",
        "type": "STAFF",
        "color": 0x95A5A6,
        "hoist": True,
        "mentionable": False,
        "permissions": discord.Permissions(
            moderate_members=True,
        ),
        "can_auto_assign": False,
        "match_keywords": ["trial staff", "trainee"],
    },

    # BOT
    "bot": {
        "name": "🤖 Rai Bot",
        "type": "BOT",
        "color": 0x5865F2,
        "hoist": True,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": False,
        "match_keywords": ["rai bot", "bots", "bot"],
    },

    # COMMUNITY
    "vip": {
        "name": "💎 VIP",
        "type": "COMMUNITY",
        "color": 0x9B59B6,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": False,
        "match_keywords": ["vip", "elite"],
    },
    "booster": {
        "name": "🌟 Booster",
        "type": "COMMUNITY",
        "color": 0xF47FFF,
        "hoist": True,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": True,
        "match_keywords": ["booster", "nitro booster", "server booster"],
    },
    "creator": {
        "name": "🎨 Creator",
        "type": "COMMUNITY",
        "color": 0xE91E63,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": False,
        "match_keywords": ["creator", "artist", "designer"],
    },
    "gamer": {
        "name": "🎮 Gamer",
        "type": "COMMUNITY",
        "color": 0x00D166,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": False,
        "is_self_assignable": True,
        "match_keywords": ["gamer", "gaming", "player"],
    },
    "music_lover": {
        "name": "🎵 Music Lover",
        "type": "COMMUNITY",
        "color": 0x1DB954,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": False,
        "is_self_assignable": True,
        "match_keywords": ["music lover", "music", "audiophile", "listener"],
    },
    "editor": {
        "name": "🎬 Editor",
        "type": "COMMUNITY",
        "color": 0x9B59B6,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": False,
        "is_self_assignable": True,
        "match_keywords": ["editor", "video editor", "vfx", "montage", "creator"],
    },
    "verified": {
        "name": "✅ Verified",
        "type": "COMMUNITY",
        "color": 0x2ECC71,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions(
            send_messages=True,
            read_messages=True,
            view_channel=True,
            add_reactions=True,
        ),
        "can_auto_assign": True,
        "match_keywords": ["verified", "verify"],
    },
    "member": {
        "name": "👤 Member",
        "type": "COMMUNITY",
        "color": 0x95A5A6,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions(
            send_messages=True,
            read_messages=True,
            view_channel=True,
        ),
        "can_auto_assign": True,
        "match_keywords": ["member", "members"],
    },
    "new_member": {
        "name": "🆕 New Member",
        "type": "COMMUNITY",
        "color": 0x34495E,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions(
            read_messages=True,
            view_channel=True,
        ),
        "can_auto_assign": True,
        "match_keywords": ["new member", "newbie", "unverified"],
    },

    # SECURITY / TEMPORARY
    "verification_required": {
        "name": "🔐 Verification Required",
        "type": "SECURITY",
        "color": 0xE67E22,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": True,
        "match_keywords": ["verification required", "pending verification"],
    },
    "under_observation": {
        "name": "🟡 Under Observation",
        "type": "SECURITY",
        "color": 0xF1C40F,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": True,
        "match_keywords": ["under observation", "observation", "watchlist"],
    },
    "restricted": {
        "name": "🟠 Restricted",
        "type": "SECURITY",
        "color": 0xE67E22,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions(
            send_messages=True,
            embed_links=False,
            attach_files=False,
            mention_everyone=False,
        ),
        "can_auto_assign": True,
        "match_keywords": ["restricted", "quarantine", "limited"],
    },
    "security_threat": {
        "name": "🔴 Security Threat",
        "type": "SECURITY",
        "color": 0x992D22,
        "hoist": True,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": True,
        "match_keywords": ["security threat", "threat", "danger"],
    },
    "timeout": {
        "name": "⏳ Timeout",
        "type": "SECURITY",
        "color": 0x7F8C8D,
        "hoist": False,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": True,
        "match_keywords": ["timeout", "muted", "silenced"],
    },
    "raid_protection": {
        "name": "🛑 Raid Protection",
        "type": "SECURITY",
        "color": 0xE74C3C,
        "hoist": True,
        "mentionable": False,
        "permissions": discord.Permissions.none(),
        "can_auto_assign": True,
        "match_keywords": ["raid protection", "anti-raid", "lockdown"],
    },
}


class RoleManager:
    """Centralized manager for guild roles, hierarchy safety, assignments, and healing."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # In-memory mapping cache: guild_id -> {role_key -> discord_role_id}
        self._cache: Dict[int, Dict[str, int]] = {}
        self._lock = asyncio.Lock()

    # ==========================================
    # CACHE MANAGEMENT
    # ==========================================

    def invalidate_guild_cache(self, guild_id: int) -> None:
        """Clear cached role mappings for a guild."""
        self._cache.pop(guild_id, None)

    def invalidate_role_cache(self, guild_id: int, role_id: int) -> None:
        """Remove a specific role from the cache."""
        if guild_id in self._cache:
            keys_to_remove = [k for k, v in self._cache[guild_id].items() if v == role_id]
            for k in keys_to_remove:
                self._cache[guild_id].pop(k, None)

    async def get_role(self, guild: discord.Guild, role_key: str) -> Optional[discord.Role]:
        """
        Safely fetch a configured Discord role by its role_key.
        Validates whether the role still actually exists in Discord before returning.
        """
        async with self._lock:
            guild_cache = self._cache.setdefault(guild.id, {})
            role_id = guild_cache.get(role_key)

        if role_id:
            role = guild.get_role(role_id)
            if role:
                return role
            # Stale cache detected
            guild_cache.pop(role_key, None)

        # Lookup in Database
        record = await self.bot.db.get_guild_role(guild.id, role_key)
        if not record or not record.enabled:
            return None

        role = guild.get_role(record.discord_role_id)
        if not role:
            # Stale DB record detected - role was deleted from guild
            logger.warning(
                f"Role {role_key} (ID {record.discord_role_id}) no longer exists in guild {guild.name} ({guild.id})."
            )
            return None

        # Update cache
        async with self._lock:
            self._cache.setdefault(guild.id, {})[role_key] = role.id

        return role

    # ==========================================
    # HIERARCHY & PERMISSION SAFETY
    # ==========================================

    @staticmethod
    def validate_hierarchy(guild: discord.Guild, target_role: discord.Role) -> Tuple[bool, str]:
        """
        Validates if Rai has sufficient permissions and role hierarchy to manage target_role.
        """
        if not guild.me.guild_permissions.manage_roles:
            return False, "Bot lacks the `Manage Roles` guild permission."
        if target_role.is_default():
            return False, "Cannot modify or assign the default @everyone role."
        if target_role.managed:
            return False, f"Role {target_role.name} is managed by Discord/integrations and cannot be modified."
        if target_role >= guild.me.top_role:
            return False, (
                f"Role {target_role.name} (pos {target_role.position}) is higher than or equal to "
                f"Rai's top role ({guild.me.top_role.name}, pos {guild.me.top_role.position})."
            )
        return True, "OK"

    @classmethod
    def validate_member_manageable(
        cls, guild: discord.Guild, member: discord.Member, target_role: Optional[discord.Role] = None
    ) -> Tuple[bool, str]:
        """
        Validates if Rai can safely perform role changes on the target member.
        """
        if member.id == guild.owner_id:
            return False, "Cannot modify server owner's roles."
        if member == guild.me:
            return False, "Cannot modify Rai's own primary roles."
        if member.top_role >= guild.me.top_role and member != guild.me:
            return False, (
                f"Member {member.display_name} has top role {member.top_role.name} (pos {member.top_role.position}) "
                f"which is higher than or equal to Rai's top role ({guild.me.top_role.name}, pos {guild.me.top_role.position})."
            )
        if target_role:
            role_ok, reason = cls.validate_hierarchy(guild, target_role)
            if not role_ok:
                return False, reason
        return True, "OK"

    @classmethod
    def validate_executor_permissions(
        cls,
        executor: discord.Member,
        target_member: Optional[discord.Member] = None,
        target_role: Optional[discord.Role] = None,
    ) -> Tuple[bool, str]:
        """
        Ensures a staff member invoking commands is authorized and respects Discord hierarchy.
        """
        guild = executor.guild
        if executor.id == guild.owner_id:
            return True, "OK"

        if not executor.guild_permissions.manage_roles:
            return False, "You require the `Manage Roles` permission to perform this action."

        if target_role and target_role >= executor.top_role:
            return False, f"You cannot manage role {target_role.name} because it is higher than or equal to your highest role."

        if target_member:
            if target_member.id == guild.owner_id:
                return False, "You cannot modify roles for the server owner."
            if target_member.top_role >= executor.top_role and target_member.id != executor.id:
                return False, f"You cannot modify {target_member.display_name} because their role is equal or higher than yours."

        return True, "OK"

    # ==========================================
    # AUTOMATIC SETUP (IDEMPOTENT)
    # ==========================================

    async def setup_guild_roles(
        self, guild: discord.Guild, executor: Optional[str] = "SYSTEM"
    ) -> Dict[str, Any]:
        """
        Inspects existing guild roles, reuses compatible roles, creates only missing roles safely,
        records mappings into database, and logs changes.
        Idempotent: Running multiple times will never create duplicate roles.
        """
        report: Dict[str, Any] = {
            "reused": [],
            "created": [],
            "skipped": [],
            "errors": [],
        }

        if not guild.me.guild_permissions.manage_roles:
            msg = "Bot lacks `Manage Roles` permission. Cannot set up or configure server roles."
            logger.error(f"Setup aborted in {guild.name}: {msg}")
            report["errors"].append(msg)
            return report

        existing_db_roles = {r.role_key: r for r in await self.bot.db.get_all_guild_roles(guild.id)}
        current_guild_roles = list(guild.roles)

        for role_key, defn in ROLE_DEFINITIONS.items():
            # 1. Check if already configured in DB and exists on Discord
            if role_key in existing_db_roles:
                rec = existing_db_roles[role_key]
                role = guild.get_role(rec.discord_role_id)
                if role:
                    report["reused"].append(f"{defn['name']} (Existing ID: {role.id})")
                    continue

            # 2. Search for existing compatible role in Discord guild
            matched_role: Optional[discord.Role] = None
            keywords = defn.get("match_keywords", [])
            for r in current_guild_roles:
                if r.is_default() or r.managed:
                    continue
                r_name_clean = r.name.lower().strip()
                if any(kw in r_name_clean for kw in keywords):
                    # Check if another key is already using this role
                    already_used = any(
                        rec.discord_role_id == r.id for rec in existing_db_roles.values()
                    )
                    if not already_used:
                        matched_role = r
                        break

            if matched_role:
                # Link existing compatible role
                await self.bot.db.save_guild_role(
                    guild_id=guild.id,
                    role_key=role_key,
                    discord_role_id=matched_role.id,
                    role_name=matched_role.name,
                    role_type=defn["type"],
                    managed_by_rai=True,
                    enabled=True,
                    position=matched_role.position,
                )
                report["reused"].append(f"{defn['name']} (Matched: {matched_role.name})")
                await self.bot.db.log_role_audit(
                    guild_id=guild.id,
                    user_id=None,
                    role_id=matched_role.id,
                    role_key=role_key,
                    action="ROLE_SYNCED",
                    reason=f"Matched existing compatible role '{matched_role.name}'",
                    trigger="ROLE_SETUP",
                    executor=executor,
                    success=True,
                )
                continue

            # 3. Create missing role if safe
            # Never automatically create staff roles with Administrator/elevated perms unless safe
            if defn["type"] == "STAFF" and defn.get("permissions", discord.Permissions.none()).administrator:
                report["skipped"].append(f"{defn['name']} (Dangerous perms skipped)")
                continue

            try:
                # Create role safely below bot's top role
                new_role = await guild.create_role(
                    name=defn["name"],
                    permissions=defn.get("permissions", discord.Permissions.none()),
                    colour=discord.Colour(defn.get("color", 0x95A5A6)),
                    hoist=defn.get("hoist", False),
                    mentionable=defn.get("mentionable", False),
                    reason="Rai Automatic Role System Setup",
                )
                await self.bot.db.save_guild_role(
                    guild_id=guild.id,
                    role_key=role_key,
                    discord_role_id=new_role.id,
                    role_name=new_role.name,
                    role_type=defn["type"],
                    managed_by_rai=True,
                    enabled=True,
                    position=new_role.position,
                )
                report["created"].append(f"{new_role.name} (Created)")
                await self.bot.db.log_role_audit(
                    guild_id=guild.id,
                    user_id=None,
                    role_id=new_role.id,
                    role_key=role_key,
                    action="ROLE_CREATED",
                    reason="Created missing system role during automatic setup",
                    trigger="ROLE_SETUP",
                    executor=executor,
                    success=True,
                )
            except discord.Forbidden:
                err = f"Permission denied creating {defn['name']}."
                report["errors"].append(err)
                logger.error(err)
            except Exception as e:
                err = f"Failed to create {defn['name']}: {e}"
                report["errors"].append(err)
                logger.error(err, exc_info=True)

        self.invalidate_guild_cache(guild.id)
        return report

    # ==========================================
    # ROLE ASSIGNMENT & REMOVAL
    # ==========================================

    async def assign_role(
        self,
        guild: discord.Guild,
        member: discord.Member,
        role_key: str,
        reason: str,
        trigger: str = "AUTO",
        executor: str = "SYSTEM",
        priority: int = 2,
    ) -> Tuple[bool, str]:
        """
        Safely assign a managed role to a member.
        Validates hierarchy, bot permissions, and dispatches via GlobalActionQueue.
        """
        role = await self.get_role(guild, role_key)
        if not role:
            return False, f"Role `{role_key}` is not configured or no longer exists."

        if role in member.roles:
            return True, f"Member already has role {role.name}."

        manageable, check_reason = self.validate_member_manageable(guild, member, role)
        if not manageable:
            await self.bot.db.log_role_audit(
                guild_id=guild.id,
                user_id=member.id,
                role_id=role.id,
                role_key=role_key,
                action="ROLE_ACTION_FAILED",
                reason=f"Hierarchy check failed: {check_reason}",
                trigger=trigger,
                executor=executor,
                success=False,
                error=check_reason,
            )
            return False, check_reason

        async def _do_assign():
            await member.add_roles(role, reason=f"[{trigger}] {reason}")
            await self.bot.db.log_role_audit(
                guild_id=guild.id,
                user_id=member.id,
                role_id=role.id,
                role_key=role_key,
                action="AUTO_ASSIGN" if trigger == "AUTO" else "STAFF_ASSIGN",
                reason=reason,
                trigger=trigger,
                executor=executor,
                success=True,
            )

        # Dispatch via GlobalActionQueue for rate-limiting & deduplication
        if hasattr(self.bot, "action_queue") and self.bot.action_queue:
            dedup = f"{guild.id}:{member.id}:ASSIGN_{role_key}"
            action_id = self.bot.action_queue.enqueue(
                guild_id=guild.id,
                action_type=f"ASSIGN_ROLE_{role_key.upper()}",
                coroutine_func=_do_assign,
                target_id=member.id,
                priority=priority,
                custom_dedup_key=dedup,
            )
            return True, f"Queued role assignment (Action: {action_id or 'Deduplicated'})."
        else:
            try:
                await _do_assign()
                return True, f"Successfully assigned {role.name}."
            except Exception as e:
                return False, f"Failed to assign role: {e}"

    async def remove_role(
        self,
        guild: discord.Guild,
        member: discord.Member,
        role_key: str,
        reason: str,
        trigger: str = "AUTO",
        executor: str = "SYSTEM",
        priority: int = 2,
    ) -> Tuple[bool, str]:
        """
        Safely remove a managed role from a member.
        Validates hierarchy, bot permissions, and dispatches via GlobalActionQueue.
        """
        role = await self.get_role(guild, role_key)
        if not role:
            return False, f"Role `{role_key}` is not configured or no longer exists."

        if role not in member.roles:
            return True, f"Member does not possess role {role.name}."

        manageable, check_reason = self.validate_member_manageable(guild, member, role)
        if not manageable:
            await self.bot.db.log_role_audit(
                guild_id=guild.id,
                user_id=member.id,
                role_id=role.id,
                role_key=role_key,
                action="ROLE_ACTION_FAILED",
                reason=f"Hierarchy check failed: {check_reason}",
                trigger=trigger,
                executor=executor,
                success=False,
                error=check_reason,
            )
            return False, check_reason

        async def _do_remove():
            await member.remove_roles(role, reason=f"[{trigger}] {reason}")
            await self.bot.db.log_role_audit(
                guild_id=guild.id,
                user_id=member.id,
                role_id=role.id,
                role_key=role_key,
                action="AUTO_REMOVE" if trigger == "AUTO" else "STAFF_REMOVE",
                reason=reason,
                trigger=trigger,
                executor=executor,
                success=True,
            )

        # Dispatch via GlobalActionQueue
        if hasattr(self.bot, "action_queue") and self.bot.action_queue:
            dedup = f"{guild.id}:{member.id}:REMOVE_{role_key}"
            action_id = self.bot.action_queue.enqueue(
                guild_id=guild.id,
                action_type=f"REMOVE_ROLE_{role_key.upper()}",
                coroutine_func=_do_remove,
                target_id=member.id,
                priority=priority,
                custom_dedup_key=dedup,
            )
            return True, f"Queued role removal (Action: {action_id or 'Deduplicated'})."
        else:
            try:
                await _do_remove()
                return True, f"Successfully removed {role.name}."
            except Exception as e:
                return False, f"Failed to remove role: {e}"

    # ==========================================
    # MEMBER LIFECYCLE HOOKS
    # ==========================================

    async def on_member_join(self, member: discord.Member) -> None:
        """
        Executed when a member joins:
        1. Assigns 'new_member' role.
        2. Assigns 'verification_required' if verification is enabled.
        """
        guild = member.guild
        if member.bot:
            # Bot joined: assign bot role
            await self.assign_role(
                guild, member, "bot", reason="New bot joined server", trigger="AUTO", executor="SYSTEM"
            )
            return

        # 1. Assign New Member
        await self.assign_role(
            guild, member, "new_member", reason="New member joined", trigger="AUTO", executor="SYSTEM"
        )

        # 2. Check Verification Config
        verif_cfg = await self.bot.db.get_verification_config(guild.id)
        if verif_cfg and verif_cfg.enabled:
            await self.assign_role(
                guild,
                member,
                "verification_required",
                reason="Verification enabled for new arrivals",
                trigger="AUTO",
                executor="SYSTEM",
            )

    async def on_verification_completed(self, member: discord.Member) -> None:
        """
        Executed upon successful verification:
        1. Removes 'new_member' and 'verification_required'.
        2. Adds 'verified' and 'member' roles.
        """
        guild = member.guild
        # Remove onboarding roles
        await self.remove_role(
            guild, member, "new_member", reason="Verification completed", trigger="VERIFICATION", executor="SYSTEM"
        )
        await self.remove_role(
            guild, member, "verification_required", reason="Verification completed", trigger="VERIFICATION", executor="SYSTEM"
        )

        # Grant member & verified roles
        await self.assign_role(
            guild, member, "verified", reason="Passed verification", trigger="VERIFICATION", executor="SYSTEM"
        )
        await self.assign_role(
            guild, member, "member", reason="Full server member access", trigger="VERIFICATION", executor="SYSTEM"
        )

    # ==========================================
    # SECURITY BRAIN & ANTI-RAID INTEGRATION
    # ==========================================

    async def set_under_observation(
        self, guild: discord.Guild, member: discord.Member, reason: str, trigger: str = "SECURITY_BRAIN"
    ) -> Tuple[bool, str]:
        """Assigns 'under_observation' role to suspicious accounts."""
        return await self.assign_role(
            guild, member, "under_observation", reason=reason, trigger=trigger, executor="SECURITY_BRAIN", priority=1
        )

    async def clear_under_observation(
        self, guild: discord.Guild, member: discord.Member, reason: str = "Observation period resolved"
    ) -> Tuple[bool, str]:
        """Removes 'under_observation' role."""
        return await self.remove_role(
            guild, member, "under_observation", reason=reason, trigger="AUTO_CLEANUP", executor="SYSTEM", priority=2
        )

    async def set_restricted(
        self, guild: discord.Guild, member: discord.Member, reason: str, trigger: str = "SECURITY_BRAIN"
    ) -> Tuple[bool, str]:
        """Assigns 'restricted' role during active security enforcement."""
        return await self.assign_role(
            guild, member, "restricted", reason=reason, trigger=trigger, executor="SECURITY_BRAIN", priority=1
        )

    async def clear_restricted(
        self, guild: discord.Guild, member: discord.Member, reason: str = "Restriction lifted"
    ) -> Tuple[bool, str]:
        """Removes 'restricted' role."""
        return await self.remove_role(
            guild, member, "restricted", reason=reason, trigger="AUTO_CLEANUP", executor="SYSTEM", priority=2
        )

    async def set_security_threat(
        self, guild: discord.Guild, member: discord.Member, reason: str, trigger: str = "SECURITY_BRAIN"
    ) -> Tuple[bool, str]:
        """Assigns 'security_threat' role to confirmed dangerous accounts."""
        return await self.assign_role(
            guild, member, "security_threat", reason=reason, trigger=trigger, executor="SECURITY_BRAIN", priority=0
        )

    async def clear_security_threat(
        self, guild: discord.Guild, member: discord.Member, reason: str = "Threat cleared"
    ) -> Tuple[bool, str]:
        """Removes 'security_threat' role."""
        return await self.remove_role(
            guild, member, "security_threat", reason=reason, trigger="STAFF_ACTION", executor="SYSTEM", priority=1
        )

    async def activate_raid_protection(self, guild: discord.Guild, reason: str) -> int:
        """
        Assigns 'raid_protection' role to recent arrivals during an active elevated raid.
        Returns count of members quarantined.
        """
        role = await self.get_role(guild, "raid_protection")
        if not role:
            return 0

        now = datetime.datetime.now(datetime.timezone.utc)
        count = 0
        for m in guild.members:
            if m.bot or m.id == guild.owner_id:
                continue
            # Target members joined within last 2 hours
            if m.joined_at and (now - m.joined_at).total_seconds() < 7200:
                ok, _ = await self.assign_role(
                    guild, m, "raid_protection", reason=reason, trigger="ANTI_RAID", executor="SECURITY_BRAIN", priority=0
                )
                if ok:
                    count += 1
        return count

    async def deactivate_raid_protection(self, guild: discord.Guild, reason: str = "Raid resolved") -> int:
        """
        Removes 'raid_protection' role from all members after incident resolution.
        Returns count of members restored.
        """
        role = await self.get_role(guild, "raid_protection")
        if not role:
            return 0

        count = 0
        for m in guild.members:
            if role in m.roles:
                ok, _ = await self.remove_role(
                    guild, m, "raid_protection", reason=reason, trigger="ANTI_RAID_RECOVERY", executor="SYSTEM", priority=1
                )
                if ok:
                    count += 1
        return count

    # ==========================================
    # SELF-HEALING & REPAIR
    # ==========================================

    async def repair_guild_roles(self, guild: discord.Guild) -> Dict[str, Any]:
        """
        Inspects stored role mappings against live Discord roles.
        If a managed role was accidentally deleted:
        1. Detects it.
        2. Recreates it if safe (never recreates dangerous staff roles automatically).
        3. Updates stored Discord role ID.
        4. Logs recovery.
        """
        report: Dict[str, Any] = {
            "repaired": [],
            "recreated": [],
            "skipped_staff": [],
            "errors": [],
        }

        stored_roles = await self.bot.db.get_all_guild_roles(guild.id)
        for rec in stored_roles:
            discord_role = guild.get_role(rec.discord_role_id)
            if discord_role is not None:
                continue  # Role is intact

            # Role was deleted in Discord!
            defn = ROLE_DEFINITIONS.get(rec.role_key)
            if not defn:
                continue

            # Safety check: Never automatically recreate staff roles with elevated permissions
            if defn["type"] == "STAFF":
                report["skipped_staff"].append(
                    f"{defn['name']} (Staff role deleted - manual re-assignment required for safety)"
                )
                await self.bot.db.log_role_audit(
                    guild_id=guild.id,
                    user_id=None,
                    role_id=rec.discord_role_id,
                    role_key=rec.role_key,
                    action="ROLE_ACTION_FAILED",
                    reason="Deleted staff role recreation skipped to prevent privilege escalation",
                    trigger="SELF_HEALING",
                    executor="SYSTEM",
                    success=False,
                )
                continue

            # Recreate non-staff role safely
            try:
                new_role = await guild.create_role(
                    name=defn["name"],
                    permissions=defn.get("permissions", discord.Permissions.none()),
                    colour=discord.Colour(defn.get("color", 0x95A5A6)),
                    hoist=defn.get("hoist", False),
                    mentionable=defn.get("mentionable", False),
                    reason="Rai Self-Healing: Recreated missing managed role",
                )
                await self.bot.db.save_guild_role(
                    guild_id=guild.id,
                    role_key=rec.role_key,
                    discord_role_id=new_role.id,
                    role_name=new_role.name,
                    role_type=defn["type"],
                    managed_by_rai=True,
                    enabled=True,
                    position=new_role.position,
                )
                report["recreated"].append(f"{new_role.name} (Restored ID: {new_role.id})")
                await self.bot.db.log_role_audit(
                    guild_id=guild.id,
                    user_id=None,
                    role_id=new_role.id,
                    role_key=rec.role_key,
                    action="ROLE_REPAIRED",
                    reason=f"Restored deleted role {rec.role_key}",
                    trigger="SELF_HEALING",
                    executor="SYSTEM",
                    success=True,
                )
            except Exception as e:
                err = f"Failed to restore {rec.role_key}: {e}"
                report["errors"].append(err)
                logger.error(err, exc_info=True)

        self.invalidate_guild_cache(guild.id)
        return report

    # ==========================================
    # BACKGROUND SYNCHRONIZATION
    # ==========================================

    async def sync_guild_roles(self, guild: discord.Guild) -> Dict[str, Any]:
        """
        Synchronizes temporary and automated roles:
        1. Synchronizes Discord native timeouts with 'timeout' role.
        2. Synchronizes server booster status with 'booster' role.
        """
        report: Dict[str, Any] = {
            "timeouts_synced": 0,
            "boosters_synced": 0,
            "errors": [],
        }

        timeout_role = await self.get_role(guild, "timeout")
        booster_role = await self.get_role(guild, "booster")
        now = datetime.datetime.now(datetime.timezone.utc)

        for member in guild.members:
            if member.id == guild.owner_id or member.bot:
                continue

            # 1. Sync Timeout Role
            if timeout_role:
                is_timed_out = member.timed_out_until is not None and member.timed_out_until > now
                has_role = timeout_role in member.roles

                if is_timed_out and not has_role:
                    ok, _ = await self.assign_role(
                        guild, member, "timeout", reason="Synchronize active Discord timeout", trigger="SYNC"
                    )
                    if ok:
                        report["timeouts_synced"] += 1
                elif not is_timed_out and has_role:
                    ok, _ = await self.remove_role(
                        guild, member, "timeout", reason="Timeout expired or removed", trigger="SYNC"
                    )
                    if ok:
                        report["timeouts_synced"] += 1

            # 2. Sync Booster Role
            if booster_role:
                is_boosting = member.premium_since is not None
                has_role = booster_role in member.roles

                if is_boosting and not has_role:
                    ok, _ = await self.assign_role(
                        guild, member, "booster", reason="Synchronize Nitro booster status", trigger="SYNC"
                    )
                    if ok:
                        report["boosters_synced"] += 1
                elif not is_boosting and has_role:
                    ok, _ = await self.remove_role(
                        guild, member, "booster", reason="Nitro boost ended", trigger="SYNC"
                    )
                    if ok:
                        report["boosters_synced"] += 1

        return report


class OnboardingRoleView(discord.ui.View):
    """Button-based interest role selector for onboarding without separate text channels."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Gamer", style=discord.ButtonStyle.secondary, emoji="🎮", custom_id="rai_role:toggle:gamer")
    async def gamer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._toggle_role(interaction, "gamer")

    @discord.ui.button(label="Music Lover", style=discord.ButtonStyle.secondary, emoji="🎵", custom_id="rai_role:toggle:music_lover")
    async def music_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._toggle_role(interaction, "music_lover")

    @discord.ui.button(label="Editor", style=discord.ButtonStyle.secondary, emoji="🎬", custom_id="rai_role:toggle:editor")
    async def editor_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._toggle_role(interaction, "editor")

    async def _toggle_role(self, interaction: discord.Interaction, role_key: str):
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ This interaction must be used in a server.", ephemeral=True)
            return

        role_info = ROLE_DEFINITIONS.get(role_key)
        if not role_info or not role_info.get("is_self_assignable"):
            await interaction.response.send_message("❌ This role cannot be self-assigned.", ephemeral=True)
            return

        # Locate role in guild by name or keyword
        target_role = None
        role_name_clean = role_info["name"].replace("🎮 ", "").replace("🎵 ", "").replace("🎬 ", "").lower()
        for r in guild.roles:
            if role_name_clean in r.name.lower() or any(k in r.name.lower() for k in role_info.get("match_keywords", [])):
                target_role = r
                break

        if not target_role:
            # Create the role safely if bot has permissions
            if guild.me.guild_permissions.manage_roles:
                try:
                    target_role = await guild.create_role(
                        name=role_info["name"],
                        color=discord.Color(role_info["color"]),
                        reason="Raivora Onboarding: Interest Role provisioned",
                    )
                except Exception as e:
                    await interaction.response.send_message(f"❌ Could not create role: {e}", ephemeral=True)
                    return
            else:
                await interaction.response.send_message("❌ The bot is missing `Manage Roles` permission.", ephemeral=True)
                return

        # Check hierarchy
        if target_role >= guild.me.top_role:
            await interaction.response.send_message("❌ This role is higher than the bot's highest role.", ephemeral=True)
            return

        # Toggle role
        if target_role in member.roles:
            try:
                await member.remove_roles(target_role, reason="Raivora Onboarding: Self-removed interest role")
                await interaction.response.send_message(
                    f"⚪ Removed **{target_role.name}** from your profile.", ephemeral=True
                )
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to remove role: {e}", ephemeral=True)
        else:
            try:
                await member.add_roles(target_role, reason="Raivora Onboarding: Self-assigned interest role")
                await interaction.response.send_message(
                    f"✅ Added **{target_role.name}** to your profile!", ephemeral=True
                )
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to add role: {e}", ephemeral=True)

