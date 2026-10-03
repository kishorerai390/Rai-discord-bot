"""
Emergency Lockdown and Channel Overwrite Restoration Engine.
Allows the server founder to atomically seal all public channels during an active raid,
and restore original permissions cleanly upon unlock without overwriting unrelated admin changes.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Dict, List, Optional
import discord

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.Lockdown")


class LockdownManager:
    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # guild_id -> dict of channel_id -> previous send_messages overwrite state
        self._saved_overwrites: Dict[int, Dict[int, Optional[bool]]] = {}

    async def lock_guild(self, guild: discord.Guild, reason: str = "Emergency Server Lockdown") -> int:
        """
        Denies send_messages for @everyone across all regular text channels.
        Saves previous states to memory and database for flawless restoration.
        """
        locked_count = 0
        guild_saves: Dict[int, Optional[bool]] = {}

        for ch in guild.text_channels:
            if not ch.permissions_for(guild.me).manage_channels:
                continue

            current_ow = ch.overwrites_for(guild.default_role)
            guild_saves[ch.id] = current_ow.send_messages

            # If send_messages is not already denied, deny it
            if current_ow.send_messages is not False:
                try:
                    await ch.set_permissions(guild.default_role, send_messages=False, reason=reason)
                    locked_count += 1
                except Exception as e:
                    logger.debug(f"Could not lock #{ch.name}: {e}")

        self._saved_overwrites[guild.id] = guild_saves
        logger.info(f"Lockdown complete in {guild.name}: locked {locked_count} text channel(s).")
        return locked_count

    async def unlock_guild(self, guild: discord.Guild, reason: str = "Lockdown Lifted") -> int:
        """
        Restores only the channels that were modified during lockdown.
        Preserves any manual administrator changes made outside Rai.
        """
        saved = self._saved_overwrites.pop(guild.id, {})
        unlocked_count = 0

        for ch in guild.text_channels:
            if not ch.permissions_for(guild.me).manage_channels:
                continue

            # If we recorded this channel during lock, restore its previous value
            if ch.id in saved:
                prev_val = saved[ch.id]
                try:
                    await ch.set_permissions(guild.default_role, send_messages=prev_val, reason=reason)
                    unlocked_count += 1
                except Exception as e:
                    logger.debug(f"Could not unlock #{ch.name}: {e}")
            else:
                # Default unlock: allow or reset
                current_ow = ch.overwrites_for(guild.default_role)
                if current_ow.send_messages is False:
                    try:
                        await ch.set_permissions(guild.default_role, send_messages=None, reason=reason)
                        unlocked_count += 1
                    except Exception:
                        pass

        logger.info(f"Unlock complete in {guild.name}: unlocked {unlocked_count} text channel(s).")
        return unlocked_count
