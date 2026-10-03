"""
Permission and Role Hierarchy Utilities.
Ensures fail-safe verification and prevents illegal moderation actions.
"""

from __future__ import annotations

from typing import Optional, Tuple
import discord
from discord import app_commands


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

    # 4. Check if moderator is server owner (owner bypasses hierarchy checks against other members)
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


import unicodedata

FOUNDER_ROLE_ID = 1545494610489643038
BOT_USER_ID = 1554732669072445532


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


def is_admin_or_owner():
    """
    Slash command decorator strictly restricting major bot controls exclusively to the Server Owner / Founder.
    Only the server owner or a member holding the Founder role is authorized.
    Locks out anyone else even if they possess Discord's Administrator permission.
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
