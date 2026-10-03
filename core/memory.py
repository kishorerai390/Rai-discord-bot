"""
RAI — SERVER MEMORY & CONVERSATION CONTEXT SERVICE.
Provides:
- Guild-scoped persistent operational memory (server preferences, templates, event schedules).
- Per-user temporary conversation context scoped by (guild_id, user_id, channel_id, session_id).
- Strict cross-guild isolation: memory NEVER leaks between servers.
- Expiration and TTL enforcement for temporary session data.
- Structured audit logging for all memory mutations.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.Memory")


class MemoryService:
    """
    Server-scoped memory and ephemeral conversation context manager.
    Enforces strict guild isolation and lifetime management.
    """

    @classmethod
    async def remember(
        cls,
        bot: SentinelBot,
        guild_id: int,
        key: str,
        value: str,
        category: str = "general",
        created_by: int = 0,
    ) -> None:
        """Stores a persistent memory entry scoped strictly to guild_id."""
        if not guild_id or not key or not value:
            raise ValueError("guild_id, key, and value are required for server memory.")
        
        sanitized_key = key.strip().lower()
        sanitized_val = value.strip()
        await bot.db.set_server_memory(
            guild_id=guild_id,
            key=sanitized_key,
            value=sanitized_val,
            category=category.strip().lower(),
            created_by=created_by,
        )
        logger.info(f"[MEMORY_SET] Guild {guild_id}: '{sanitized_key}' by {created_by}")

    @classmethod
    async def recall(
        cls,
        bot: SentinelBot,
        guild_id: int,
        key: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a persistent memory entry for the given guild."""
        if not guild_id or not key:
            return None
        return await bot.db.get_server_memory(guild_id, key.strip().lower())

    @classmethod
    async def forget(
        cls,
        bot: SentinelBot,
        guild_id: int,
        key: str,
    ) -> bool:
        """Removes a memory entry for the given guild."""
        if not guild_id or not key:
            return False
        deleted = await bot.db.delete_server_memory(guild_id, key.strip().lower())
        if deleted:
            logger.info(f"[MEMORY_DELETE] Guild {guild_id}: '{key}'")
        return deleted

    @classmethod
    async def list_memories(
        cls,
        bot: SentinelBot,
        guild_id: int,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists all remembered keys for the specified guild."""
        if not guild_id:
            return []
        return await bot.db.list_server_memory(guild_id, category=category)

    @classmethod
    async def set_context(
        cls,
        bot: SentinelBot,
        guild_id: int,
        user_id: int,
        channel_id: int,
        session_id: str,
        key: str,
        val: str,
        ttl_seconds: float = 1800.0,
    ) -> None:
        """Saves temporary conversation context with an expiration TTL."""
        await bot.db.set_conversation_context(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=channel_id,
            session_id=session_id,
            key=key.strip().lower(),
            val=val.strip(),
            ttl_seconds=ttl_seconds,
        )

    @classmethod
    async def get_context(
        cls,
        bot: SentinelBot,
        guild_id: int,
        user_id: int,
        channel_id: int,
        key: str,
    ) -> Optional[str]:
        """Retrieves active conversation context if not expired."""
        return await bot.db.get_conversation_context(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=channel_id,
            key=key.strip().lower(),
        )

    @classmethod
    async def sweep_expired_context(cls, bot: SentinelBot) -> int:
        """Removes expired temporary session contexts."""
        return await bot.db.clear_expired_conversation_context()
