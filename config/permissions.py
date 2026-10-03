"""
Rai Permission Hierarchy and Access Control System.
Enforces multi-tiered authorization:
- OWNER (Root master, founder)
- ADMIN (Server administrators, managed features)
- SECURITY_MANAGER (Security/anti-raid controllers)
- MODERATOR (Disciplinary actions: warn, timeout, kick, ban)
- DJ (Music playback controls only, strictly isolated from security)
- MEMBER (General public server member)
"""

from __future__ import annotations

import enum
import unicodedata
from typing import Optional, Tuple
import discord
from discord import app_commands

FOUNDER_ROLE_ID = 1545494610489643038
BOT_USER_ID = 1554732669072445532


class PermissionLevel(enum.IntEnum):
    """Hierarchical permission tiers. Higher integer = higher privilege."""
    MEMBER = 0
    DJ = 10
    MODERATOR = 20
    SECURITY_MANAGER = 30
    ADMIN = 40
    OWNER = 50


def is_founder_or_owner(member: discord.Member) -> bool:
    """Check if a member is the server owner, the bot itself, or holds the Founder role."""
    if not member or not getattr(member, "guild", None):
        return False
    # 1. Server owner
    if member.id == member.guild.owner_id:
        return True
    # 2. The bot itself (The Raivora)
    guild = member.guild
    if (getattr(guild, "me", None) and member.id == guild.me.id) or member.id == BOT_USER_ID:
        return True
    # 3. Founder role holder
    roles = getattr(member, "roles", [])
    for r in roles:
        if getattr(r, "id", None) == FOUNDER_ROLE_ID:
            return True
        r_name = getattr(r, "name", "")
        # Normalize fancy unicode/font glyphs (e.g. 𝐅𝐎𝐔𝐍𝐃𝐄𝐑 -> FOUNDER)
        norm_name = unicodedata.normalize("NFKD", r_name).lower()
        if "founder" in norm_name:
            return True
    return False


def get_member_permission_level(member: discord.Member, dj_role_id: Optional[int] = None) -> PermissionLevel:
    """Calculates the member's current permission level."""
    if not member or not getattr(member, "guild", None):
        return PermissionLevel.MEMBER

    if is_founder_or_owner(member):
        return PermissionLevel.OWNER

    if getattr(member, "guild_permissions", None) and member.guild_permissions.administrator:
        return PermissionLevel.ADMIN

    # Check for security manager or moderator roles
    role_names = [unicodedata.normalize("NFKD", r.name).lower() for r in getattr(member, "roles", [])]
    for name in role_names:
        if "security" in name or "sentinel" in name or "shield" in name:
            return PermissionLevel.SECURITY_MANAGER
        if "mod" in name or "staff" in name or "enforcer" in name:
            return PermissionLevel.MODERATOR

    if getattr(member, "guild_permissions", None):
        if member.guild_permissions.ban_members or member.guild_permissions.kick_members or member.guild_permissions.moderate_members:
            return PermissionLevel.MODERATOR

    # Check DJ role (Music isolated permission)
    if dj_role_id:
        if any(r.id == dj_role_id for r in getattr(member, "roles", [])):
            return PermissionLevel.DJ
    for name in role_names:
        if "dj" in name or "music" in name:
            return PermissionLevel.DJ

    return PermissionLevel.MEMBER


def has_permission(required: PermissionLevel, dj_role_id: Optional[int] = None):
    """Slash command decorator requiring at least the specified permission level."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        level = get_member_permission_level(interaction.user, dj_role_id=dj_role_id)
        return level >= required
    return app_commands.check(predicate)


def is_admin_or_owner():
    """
    Slash command decorator strictly restricting major bot controls exclusively to the Server Owner / Founder.
    Only the server owner or a member holding the Founder role is authorized.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        return is_founder_or_owner(interaction.user)
    return app_commands.check(predicate)


def is_guild_owner():
    """Slash command decorator requiring Server Ownership or Founder role."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        return is_founder_or_owner(interaction.user)
    return app_commands.check(predicate)


def is_dj_or_staff(dj_role_id: Optional[int] = None):
    """Slash command decorator for music commands: DJ, Staff, or Owner."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        level = get_member_permission_level(interaction.user, dj_role_id=dj_role_id)
        return level >= PermissionLevel.DJ
    return app_commands.check(predicate)


def can_moderate(
    moderator: discord.Member,
    target: discord.Member,
    bot_member: discord.Member,
) -> Tuple[bool, str]:
    """
    Validates whether the moderator and bot can perform a moderation action on the target.
    Returns (can_moderate: bool, rejection_reason: str).
    """
    guild = moderator.guild

    # 1. Target is the guild owner
    if target.id == guild.owner_id:
        return False, "Cannot moderate the server owner."

    # 2. Target is the bot itself
    if target.id == bot_member.id:
        return False, "The bot cannot moderate itself."

    # 3. Target is the moderator
    if target.id == moderator.id:
        return False, "You cannot moderate yourself."

    # 4. Check if moderator is server owner
    is_mod_owner = (moderator.id == guild.owner_id)

    # 5. Role hierarchy: Moderator vs Target
    if not is_mod_owner and target.top_role >= moderator.top_role:
        return False, f"Cannot moderate {target.mention}: their highest role ({target.top_role.name}) is equal to or higher than yours ({moderator.top_role.name})."

    # 6. Role hierarchy: Bot vs Target
    if target.top_role >= bot_member.top_role:
        return False, f"The bot cannot moderate {target.mention}: their highest role ({target.top_role.name}) is equal to or higher than the bot's highest role ({bot_member.top_role.name})."

    return True, ""


def check_bot_hierarchy(target: discord.Member, bot_member: discord.Member) -> Tuple[bool, str]:
    """Check if bot has hierarchy over target for automated actions."""
    if target.id == target.guild.owner_id:
        return False, "Target is the server owner."
    if target.id == bot_member.id:
        return False, "Target is the bot."
    if target.top_role >= bot_member.top_role:
        return False, f"Target's highest role ({target.top_role.name}) is equal or higher than the bot's role ({bot_member.top_role.name})."
    return True, ""
