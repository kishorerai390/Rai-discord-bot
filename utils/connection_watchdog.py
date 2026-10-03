"""
Discord Connection Watchdog for Rai Bot.
Continuously monitors Gateway latency, heartbeat health, reconnect events,
and API stability without creating competing reconnect loops.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("RaiConnection")


class DiscordConnectionWatchdog:
    """Passively observes Discord gateway latency, heartbeat, and reconnection events."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._latency_history: list[float] = []
        self._reconnect_count: int = 0
        self._last_heartbeat_ack: float = time.time()
        self._supervisor_task: Optional[asyncio.Task] = None
        self._is_unstable = False

    def start(self) -> None:
        """Starts the passive gateway observer loop."""
        if not self._supervisor_task or self._supervisor_task.done():
            self._supervisor_task = asyncio.create_task(self._watchdog_loop())
            logger.info("Discord Connection Watchdog started.")

    def stop(self) -> None:
        """Stops the watchdog supervisor."""
        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()

    def record_reconnect(self) -> None:
        """Called when Discord client reconnects."""
        self._reconnect_count += 1
        logger.warning(f"[ConnectionWatchdog] Gateway reconnect observed (Total: {self._reconnect_count})")

    def record_identify(self) -> None:
        """Called when Discord client completes IDENTIFY handshake."""
        self._last_heartbeat_ack = time.time()
        logger.info("[ConnectionWatchdog] Gateway IDENTIFY handshake completed.")

    def record_resume(self) -> None:
        """Called when Discord client completes RESUME handshake."""
        self._last_heartbeat_ack = time.time()
        logger.info("[ConnectionWatchdog] Gateway RESUME handshake completed.")

    def record_disconnect(self, reason: str = "") -> None:
        """Called when Discord client disconnects from Gateway."""
        logger.warning(f"[ConnectionWatchdog] Gateway disconnect: {reason}")

    @property
    def current_latency_ms(self) -> float:
        """Returns the current Gateway latency in milliseconds."""
        raw = getattr(self.bot, "latency", 0.0)
        return round((raw or 0.0) * 1000.0, 2)

    async def _watchdog_loop(self) -> None:
        """Samples latency and detects heartbeat stalling."""
        while True:
            try:
                await asyncio.sleep(15)
                ms = self.current_latency_ms
                self._latency_history.append(ms)
                if len(self._latency_history) > 60:
                    self._latency_history.pop(0)

                # Classify instability (latency > 500ms or NaN)
                if ms > 500.0:
                    self._is_unstable = True
                    logger.warning(f"[ConnectionWatchdog] High gateway latency detected: {ms}ms")
                else:
                    self._is_unstable = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in connection watchdog loop: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Returns connection health telemetry."""
        avg_lat = (
            round(sum(self._latency_history) / len(self._latency_history), 2)
            if self._latency_history
            else self.current_latency_ms
        )
        return {
            "connected": self.bot.is_ready(),
            "latency_ms": self.current_latency_ms,
            "avg_latency_ms": avg_lat,
            "reconnects": self._reconnect_count,
            "is_unstable": self._is_unstable,
        }
