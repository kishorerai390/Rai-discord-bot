"""
MusicMaid — Dedicated Bot Role & Permission Management Service.
Automatically provisions and maintains the dedicated 'MusicMaid' bot role
with minimal required voice and text permissions across all connected guilds.
Strictly respects Discord's permission hierarchy and never grants Administrator.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import discord

logger = logging.getLogger("MusicMaid.RoleService")

# Canonical dedicated bot role name
BOT_ROLE_NAME: str = "MusicMaid"

# Role Accent Color (Vibrant Royal Purple matching MusicMaid brand)
BOT_ROLE_COLOR = discord.Colour.from_rgb(147, 51, 234)

# Explicitly Approved Minimum Music Permissions
REQUIRED_PERMISSIONS_DICT: Dict[str, bool] = {
    # Text and Player Permissions
    "view_channel": True,
    "send_messages": True,
    "embed_links": True,
    "read_message_history": True,
    "use_application_commands": True,
    # Voice Permissions
    "connect": True,
    "speak": True,
}


class BotRoleService:
    """Enterprise-grade, idempotent role manager for MusicMaid."""

    @staticmethod
    def get_target_permissions() -> discord.Permissions:
        """
        Construct exact minimum Discord permissions required for music playback and controls.
        Administrator is strictly False.
        """
        perms = discord.Permissions(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            read_message_history=True,
            use_application_commands=True,
            connect=True,
            speak=True,
        )
        perms.administrator = False
        return perms

    @classmethod
    def audit_guild_permissions(cls, guild: discord.Guild) -> Dict[str, Any]:
        """
        Inspect current bot member permissions in a guild and identify any missing capabilities.
        """
        me = guild.me if hasattr(guild, "me") and guild.me else None
        if not me:
            return {"ready": False, "missing": ["bot_member_missing"], "has_manage_roles": False}

        current_perms = me.guild_permissions
        missing = []
        for perm_name, required in REQUIRED_PERMISSIONS_DICT.items():
            if required and not getattr(current_perms, perm_name, False):
                missing.append(perm_name)

        return {
            "ready": len(missing) == 0,
            "missing": missing,
            "has_manage_roles": current_perms.manage_roles,
            "top_role": str(me.top_role.name) if me.top_role else "None",
            "top_role_pos": me.top_role.position if me.top_role else 0,
        }

    @classmethod
    async def setup_guild_role(
        cls,
        guild: discord.Guild,
        db: Optional[Any] = None,
    ) -> Tuple[bool, Optional[discord.Role], str]:
        """
        Idempotent automatic setup for a single guild:
        1. Finds or reuses the dedicated 'MusicMaid' role.
        2. Repairs only missing, explicitly approved permissions.
        3. Creates the role once if missing and permissions allow.
        4. Assigns the role to MusicMaid's own guild member if hierarchy permits.
        5. Saves role ID to database.
        """
        if not guild:
            return False, None, "Invalid guild object"

        me = guild.me if hasattr(guild, "me") and guild.me else None
        if not me:
            return False, None, f"Bot member handle unavailable in guild {guild.id}"

        target_perms = cls.get_target_permissions()
        existing_role: Optional[discord.Role] = None

        # 1. Attempt lookup by stored database role ID
        saved_role_id = None
        if db and hasattr(db, "get_bot_role_id"):
            try:
                saved_role_id = await db.get_bot_role_id(guild.id)
                if saved_role_id:
                    existing_role = guild.get_role(int(saved_role_id))
            except Exception as db_err:
                logger.debug(f"[RoleSetup] Stored role ID lookup notice in guild {guild.id}: {db_err}")

        # 2. If not found by ID, look up by canonical role name
        if not existing_role:
            for role in guild.roles:
                if role.name.strip().lower() == BOT_ROLE_NAME.lower():
                    existing_role = role
                    break

        # Check if bot has manage_roles
        can_manage_roles = bool(me.guild_permissions.manage_roles)

        # =====================================================================
        # CASE A: ROLE ALREADY EXISTS (Reuse & Repair)
        # =====================================================================
        if existing_role:
            logger.info(
                f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Reusing existing '{BOT_ROLE_NAME}' role (ID: {existing_role.id})."
            )

            # Persist to database if not already stored
            if db and hasattr(db, "set_bot_role_id") and saved_role_id != existing_role.id:
                try:
                    await db.set_bot_role_id(guild.id, existing_role.id)
                except Exception as db_save_err:
                    logger.debug(f"[RoleSetup] Error persisting role ID {existing_role.id}: {db_save_err}")

            # Check if role is missing approved permissions
            role_perms = existing_role.permissions
            missing_perms = []
            for perm_name, required in REQUIRED_PERMISSIONS_DICT.items():
                if required and not getattr(role_perms, perm_name, False):
                    missing_perms.append(perm_name)

            if missing_perms:
                # Can we repair it? Requires manage_roles and bot.top_role > existing_role
                me_pos = getattr(me.top_role, "position", 0) if me.top_role else 0
                target_pos = getattr(existing_role, "position", 0)
                if can_manage_roles and me_pos > target_pos:
                    try:
                        updated_perms = discord.Permissions(role_perms.value)
                        for p in missing_perms:
                            setattr(updated_perms, p, True)
                        updated_perms.administrator = False  # Strict guarantee
                        await existing_role.edit(
                            permissions=updated_perms,
                            reason=f"MusicMaid permission repair for missing permissions: {', '.join(missing_perms)}",
                        )
                        logger.info(
                            f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Successfully repaired permissions for role '{existing_role.name}'."
                        )
                    except discord.Forbidden:
                        logger.warning(
                            f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Discord forbidden while repairing permissions for '{existing_role.name}'."
                        )
                    except Exception as edit_err:
                        logger.warning(
                            f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Could not edit role permissions: {edit_err}"
                        )
                else:
                    logger.info(
                        f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Existing role '{existing_role.name}' is missing permissions ({', '.join(missing_perms)}), but bot lacks hierarchy/Manage Roles to edit it."
                    )

            # Ensure role is assigned to the bot itself
            assign_success = await cls._ensure_member_role(guild, me, existing_role, can_manage_roles)
            return True, existing_role, f"Reused existing role (Assigned: {assign_success})"

        # =====================================================================
        # CASE B: ROLE DOES NOT EXIST (Create Once)
        # =====================================================================
        if not can_manage_roles:
            diagnostic = (
                f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Missing 'Manage Roles' permission. "
                f"Cannot automatically create dedicated '{BOT_ROLE_NAME}' role. "
                f"MusicMaid will continue running with its existing guild permissions. "
                f"Manual fix: In Server Settings > Roles, grant 'Manage Roles' to MusicMaid or create a role named '{BOT_ROLE_NAME}'."
            )
            logger.warning(diagnostic)
            return False, None, diagnostic

        # Create role with exact permissions
        try:
            created_role = await guild.create_role(
                name=BOT_ROLE_NAME,
                permissions=target_perms,
                colour=BOT_ROLE_COLOR,
                hoist=False,
                mentionable=False,
                reason="MusicMaid automated bot role setup with approved music playback permissions",
            )
            logger.info(
                f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Created dedicated '{BOT_ROLE_NAME}' role (ID: {created_role.id})."
            )

            # Save in database
            if db and hasattr(db, "set_bot_role_id"):
                try:
                    await db.set_bot_role_id(guild.id, created_role.id)
                except Exception as db_save_err:
                    logger.debug(f"[RoleSetup] Error saving created role ID: {db_save_err}")

            # Assign to the bot
            assign_success = await cls._ensure_member_role(guild, me, created_role, can_manage_roles)
            return True, created_role, f"Created new dedicated role (Assigned: {assign_success})"

        except discord.Forbidden:
            diagnostic = (
                f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Forbidden to create role. "
                f"Verify bot has 'Manage Roles' in this server."
            )
            logger.warning(diagnostic)
            return False, None, diagnostic
        except discord.HTTPException as http_err:
            diagnostic = f"[RoleSetup] Guild '{guild.name}' ({guild.id}): HTTP error creating role: {http_err}"
            logger.error(diagnostic)
            return False, None, diagnostic
        except Exception as e:
            diagnostic = f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Unexpected exception during role setup: {e}"
            logger.error(diagnostic)
            return False, None, diagnostic

    @classmethod
    async def _ensure_member_role(
        cls,
        guild: discord.Guild,
        me: discord.Member,
        role: discord.Role,
        can_manage_roles: bool,
    ) -> bool:
        """
        Assigns the dedicated role strictly to MusicMaid's own guild member if not already assigned.
        Never assigns to ordinary members.
        """
        if role in me.roles:
            return True

        if not can_manage_roles:
            logger.info(
                f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Bot lacks 'Manage Roles' to assign '{role.name}' to itself."
            )
            return False

        me_pos = getattr(me.top_role, "position", 0) if me.top_role else 0
        role_pos = getattr(role, "position", 0)
        if me_pos <= role_pos:
            logger.warning(
                f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Role hierarchy prevents assigning '{role.name}' "
                f"(Role pos {role_pos} >= Bot top role '{getattr(me.top_role, 'name', 'None')}' pos {me_pos}). "
                f"Manual fix: Move MusicMaid's bot integration role above '{role.name}' in Server Settings > Roles."
            )
            return False

        try:
            await me.add_roles(role, reason="MusicMaid dedicated bot role assignment")
            logger.info(f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Successfully assigned '{role.name}' to MusicMaid.")
            return True
        except discord.Forbidden:
            logger.warning(
                f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Forbidden to assign '{role.name}' to itself."
            )
            return False
        except Exception as assign_err:
            logger.warning(
                f"[RoleSetup] Guild '{guild.name}' ({guild.id}): Failed assigning role: {assign_err}"
            )
            return False

    @classmethod
    async def setup_all_guilds(
        cls,
        bot: discord.Client,
        db: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Inspect and configure dedicated roles across all connected guilds sequentially,
        with small delay to prevent Discord REST rate limits.
        """
        guilds: List[discord.Guild] = list(getattr(bot, "guilds", []))
        total = len(guilds)
        logger.info(f"[RoleSetup] Initiating automated role inspection across {total} connected guilds...")

        results = {
            "total_guilds": total,
            "created": 0,
            "reused": 0,
            "failed": 0,
            "details": [],
        }

        for guild in guilds:
            try:
                success, role, message = await cls.setup_guild_role(guild, db)
                status = "success" if success else "skipped_or_failed"
                if success:
                    if "Created" in message:
                        results["created"] += 1
                    else:
                        results["reused"] += 1
                else:
                    results["failed"] += 1

                results["details"].append({
                    "guild_id": guild.id,
                    "guild_name": guild.name,
                    "status": status,
                    "role_id": role.id if role else None,
                    "message": message,
                })

                # Yield control briefly to prevent Discord gateway / REST rate limits
                await asyncio.sleep(0.1)

            except Exception as guild_err:
                logger.error(f"[RoleSetup] Error inspecting guild {guild.id}: {guild_err}")
                results["failed"] += 1

        logger.info(
            f"[RoleSetup] Completed role inspection: {results['created']} created, "
            f"{results['reused']} reused, {results['failed']} failed/skipped out of {total} guilds."
        )
        return results
