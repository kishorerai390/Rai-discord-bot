"""
Centralized Rate Limiting and Cooldown Management.
Supports runtime monotonic timers, sliding window security event counters,
burst + sustained limits, independent violation tracking, and persistent SQLite storage.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from database.database import Database

logger = logging.getLogger(__name__)


class CooldownScope(Enum):
    USER_CMD = "user_cmd"
    USER_GUILD_CMD = "user_guild_cmd"
    GUILD_ACTION = "guild_action"
    GLOBAL = "global"


@dataclass
class RuntimeCooldownEntry:
    key: str
    expires_at: float  # monotonic time
    created_at: float  # monotonic time
    attempts: int = 1


@dataclass
class SlidingWindowBucket:
    """Sliding time window tracker for security actions using monotonic timestamps."""
    timestamps: List[float] = field(default_factory=list)

    def prune(self, now: float, window: float) -> None:
        cutoff = now - window
        self.timestamps = [t for t in self.timestamps if t > cutoff]

    def add_and_check(self, now: float, limit: int, window: float) -> Tuple[bool, int]:
        """
        Prunes old entries, adds current timestamp, and returns:
        (is_exceeded, current_count_within_window)
        """
        self.prune(now, window)
        self.timestamps.append(now)
        count = len(self.timestamps)
        return count > limit, count


class CooldownManager:
    """
    Centralized cooldown manager providing:
    - In-memory monotonic command cooldowns
    - Sliding window security detection (burst + sustained)
    - Persistent SQLite cooldowns for critical safeguard actions
    - Concurrency-safe atomic reserve/check operations
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db
        # In-memory runtime cooldowns: key -> RuntimeCooldownEntry
        self._runtime_cooldowns: Dict[str, RuntimeCooldownEntry] = {}
        # Sliding windows for security rate limits: "guild:executor:action" -> SlidingWindowBucket
        self._security_sliding_windows: Dict[str, SlidingWindowBucket] = {}
        # Concurrency locks
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    def set_db(self, db: Database) -> None:
        self.db = db

    def start_cleanup_loop(self, interval_seconds: int = 60) -> None:
        """Start the background task to periodically prune expired cooldowns."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup(interval_seconds))

    def stop_cleanup_loop(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

    async def _periodic_cleanup(self, interval: int) -> None:
        while True:
            try:
                await asyncio.sleep(interval)
                await self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cooldown cleanup loop: {e}")

    # ==========================================
    # RUNTIME COMMAND COOLDOWNS
    # ==========================================

    def _build_key(
        self,
        scope: CooldownScope,
        command_or_action: str,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ) -> str:
        if scope == CooldownScope.USER_CMD:
            return f"u:{user_id}:{command_or_action}"
        elif scope == CooldownScope.USER_GUILD_CMD:
            return f"ug:{guild_id}:{user_id}:{command_or_action}"
        elif scope == CooldownScope.GUILD_ACTION:
            return f"ga:{guild_id}:{command_or_action}"
        elif scope == CooldownScope.GLOBAL:
            return f"global:{command_or_action}"
        return f"{scope.value}:{guild_id}:{user_id}:{command_or_action}"

    async def check_and_reserve(
        self,
        scope: CooldownScope,
        command: str,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
        cooldown_seconds: float = 3.0,
    ) -> Tuple[bool, float]:
        """
        Atomic CHECK -> RESERVE.
        Returns:
            (is_rate_limited: bool, retry_after_seconds: float)
        If not rate limited, reserves the cooldown and returns (False, 0.0).
        """
        async with self._lock:
            now = time.monotonic()
            key = self._build_key(scope, command, user_id, guild_id)

            entry = self._runtime_cooldowns.get(key)
            if entry is not None:
                if now < entry.expires_at:
                    entry.attempts += 1
                    retry_after = max(0.1, entry.expires_at - now)
                    return True, round(retry_after, 1)
                else:
                    # Expired, clean up
                    del self._runtime_cooldowns[key]

            # Reserve slot
            self._runtime_cooldowns[key] = RuntimeCooldownEntry(
                key=key,
                expires_at=now + cooldown_seconds,
                created_at=now,
                attempts=1,
            )
            return False, 0.0

    async def cancel_cooldown(
        self,
        scope: CooldownScope,
        command: str,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ) -> None:
        """
        Release reserved cooldown when a command fails validation before executing.
        """
        async with self._lock:
            key = self._build_key(scope, command, user_id, guild_id)
            self._runtime_cooldowns.pop(key, None)

    async def reset_user_cooldowns(self, user_id: int, guild_id: Optional[int] = None) -> int:
        """Admin reset for all in-memory cooldowns matching a user."""
        async with self._lock:
            removed = 0
            u_str = str(user_id)
            keys_to_remove = []
            for k in self._runtime_cooldowns.keys():
                if f":{u_str}:" in k or k.startswith(f"u:{u_str}:"):
                    if guild_id is None or f":{guild_id}:" in k:
                        keys_to_remove.append(k)

            for k in keys_to_remove:
                del self._runtime_cooldowns[k]
                removed += 1
            return removed

    async def reset_all_cooldowns(self, guild_id: Optional[int] = None) -> int:
        """Admin reset of all runtime cooldowns in a guild."""
        async with self._lock:
            if guild_id is None:
                count = len(self._runtime_cooldowns)
                self._runtime_cooldowns.clear()
                return count
            else:
                g_str = f":{guild_id}:"
                keys_to_remove = [k for k in self._runtime_cooldowns if g_str in k]
                for k in keys_to_remove:
                    del self._runtime_cooldowns[k]
                return len(keys_to_remove)

    # ==========================================
    # SLIDING WINDOW & BURST/SUSTAINED PROTECTION
    # ==========================================

    async def record_security_action(
        self,
        guild_id: int,
        executor_id: int,
        action: str,
        limit: int,
        window_seconds: int,
        sustained_limit: Optional[int] = None,
        sustained_window_seconds: Optional[int] = None,
    ) -> Tuple[bool, int, str]:
        """
        Sliding-window evaluation with optional burst + sustained limits.
        Returns:
            (is_violation: bool, count_in_window: int, rule_triggered: str)
        """
        async with self._lock:
            now = time.monotonic()
            bucket_key = f"{guild_id}:{executor_id}:{action}"
            bucket = self._security_sliding_windows.setdefault(bucket_key, SlidingWindowBucket())

            # Check primary (burst) window
            burst_exceeded, burst_count = bucket.add_and_check(now, limit, float(window_seconds))
            if burst_exceeded:
                return True, burst_count, f"Burst limit exceeded ({burst_count}/{limit} in {window_seconds}s)"

            # Check sustained window if configured
            if sustained_limit and sustained_window_seconds:
                bucket.prune(now, float(sustained_window_seconds))
                sustained_count = len(bucket.timestamps)
                if sustained_count > sustained_limit:
                    return (
                        True,
                        sustained_count,
                        f"Sustained limit exceeded ({sustained_count}/{sustained_limit} in {sustained_window_seconds}s)",
                    )

            return False, burst_count, "OK"

    # ==========================================
    # PERSISTENT COOLDOWNS
    # ==========================================

    async def check_persistent_cooldown(
        self, guild_id: int, user_id: Optional[int], action: str
    ) -> Tuple[bool, Optional[str]]:
        if not self.db:
            return False, None
        expires_at_iso = await self.db.get_persistent_cooldown(guild_id, user_id, action)
        if not expires_at_iso:
            return False, None

        now = datetime.datetime.now(datetime.timezone.utc)
        expires_dt = datetime.datetime.fromisoformat(expires_at_iso)
        if now < expires_dt:
            return True, expires_at_iso
        else:
            await self.db.delete_persistent_cooldown(guild_id, user_id, action)
            return False, None

    async def set_persistent_cooldown(
        self, guild_id: int, user_id: Optional[int], action: str, duration_seconds: int
    ) -> str:
        if not self.db:
            return ""
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_dt = now + datetime.timedelta(seconds=duration_seconds)
        expires_iso = expires_dt.isoformat()
        await self.db.set_persistent_cooldown(guild_id, user_id, action, expires_iso)
        return expires_iso

    # ==========================================
    # CLEANUP
    # ==========================================

    async def cleanup_expired(self) -> Dict[str, int]:
        """Prunes expired in-memory cooldowns and calls SQLite cleanup."""
        now = time.monotonic()
        cleaned_runtime = 0
        async with self._lock:
            keys_to_del = [k for k, v in self._runtime_cooldowns.items() if now >= v.expires_at]
            for k in keys_to_del:
                del self._runtime_cooldowns[k]
                cleaned_runtime += 1

            # Prune sliding windows empty for more than 120 seconds
            stale_windows = []
            for k, b in self._security_sliding_windows.items():
                b.prune(now, 120.0)
                if not b.timestamps:
                    stale_windows.append(k)
            for k in stale_windows:
                del self._security_sliding_windows[k]

        db_cleaned = {"cooldowns": 0, "violations": 0}
        if self.db and self.db.is_connected:
            try:
                db_cleaned = await self.db.cleanup_expired_data()
            except Exception as e:
                logger.error(f"Error cleaning up DB cooldowns: {e}")

        return {
            "runtime_cooldowns": cleaned_runtime,
            "db_cooldowns": db_cleaned.get("cooldowns", 0),
            "db_violations": db_cleaned.get("violations", 0),
        }
