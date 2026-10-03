"""
Core Permissions & Access Control Module for Rai.
Provides permission validation, role hierarchy checks, and command access gates.
"""

from __future__ import annotations

from config.permissions import (
    PermissionLevel,
    is_founder_or_owner,
    get_member_permission_level,
    has_permission,
    is_admin_or_owner,
    is_guild_owner,
    is_dj_or_staff,
    can_moderate,
    check_bot_hierarchy,
    FOUNDER_ROLE_ID,
    BOT_USER_ID,
)

__all__ = [
    "PermissionLevel",
    "is_founder_or_owner",
    "get_member_permission_level",
    "has_permission",
    "is_admin_or_owner",
    "is_guild_owner",
    "is_dj_or_staff",
    "can_moderate",
    "check_bot_hierarchy",
    "FOUNDER_ROLE_ID",
    "BOT_USER_ID",
]
