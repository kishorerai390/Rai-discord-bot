"""
Command Watchdog for Rai Bot.
Monitors execution duration, detects stuck commands, tracks command metrics,
measures ACK and processing latencies, and alerts on slow or failing interactions.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("RaiWatchdog")


@dataclass
class ActiveCommandRecord:
    interaction_id: int
    command_name: str
    user_id: int
    guild_id: Optional[int]
    received_at: float
    acknowledged_at: Optional[float] = None


@dataclass
class CompletedCommandRecord:
    interaction_id: int
    command_name: str
    user_id: int
    guild_id: Optional[int]
    ack_latency_ms: float
    processing_latency_ms: float
    duration_ms: float
    status: str  # NORMAL, SLOW, VERY_SLOW, CRITICAL_SLOW, FAILED
    error_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class CommandWatchdog:
    """Real-time command execution watchdog and performance tracker."""

    def __init__(self, bot: SentinelBot, ring_buffer_size: int = 500):
        self.bot = bot
        self._active_commands: Dict[int, ActiveCommandRecord] = {}
        self._recent_history: deque[CompletedCommandRecord] = deque(maxlen=ring_buffer_size)
        self._slow_threshold_ms: float = 1000.0  # 1s
        self._very_slow_threshold_ms: float = 3000.0  # 3s
        self._critical_threshold_ms: float = 10000.0  # 10s
        self._ack_warning_threshold_ms: float = 1500.0  # 1.5s
        self._supervisor_task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Starts the watchdog background supervisor for stuck commands."""
        if not self._supervisor_task or self._supervisor_task.done():
            self._supervisor_task = asyncio.create_task(self._stuck_command_supervisor())
            logger.info("Command Watchdog supervisor started.")

    def stop(self) -> None:
        """Stops the watchdog supervisor."""
        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()

    def record_start(self, interaction: discord.Interaction) -> None:
        """Records the beginning of an interaction command execution."""
        cmd_name = interaction.command.name if interaction.command else "interaction"
        self._active_commands[interaction.id] = ActiveCommandRecord(
            interaction_id=interaction.id,
            command_name=cmd_name,
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            received_at=time.perf_counter(),
        )

    def record_ack(self, interaction: discord.Interaction) -> float:
        """Records the instant an interaction was acknowledged/deferred."""
        record = self._active_commands.get(interaction.id)
        now = time.perf_counter()
        if not record:
            return 0.0

        record.acknowledged_at = now
        ack_latency_ms = (now - record.received_at) * 1000.0
        if ack_latency_ms >= self._ack_warning_threshold_ms:
            logger.warning(
                f"[Watchdog ALERT] INTERACTION ACK DELAY\n"
                f"Command: /{record.command_name}\n"
                f"Guild: {record.guild_id}\n"
                f"ACK delay: {ack_latency_ms:.1f}ms\n"
                f"Possible cause: Gateway latency / Event Loop / Database"
            )
        return ack_latency_ms

    def record_end(
        self,
        interaction: discord.Interaction,
        status: str = "SUCCESS",
        error_id: Optional[str] = None,
    ) -> float:
        """Records completion of an interaction command and classifies latency."""
        now = time.perf_counter()
        record = self._active_commands.pop(interaction.id, None)
        cmd_name = interaction.command.name if interaction.command else "interaction"

        if not record:
            duration_ms = 0.0
            ack_latency_ms = 0.0
            processing_latency_ms = 0.0
        else:
            duration_ms = (now - record.received_at) * 1000.0
            ack_time = record.acknowledged_at or record.received_at
            ack_latency_ms = (ack_time - record.received_at) * 1000.0
            processing_latency_ms = (now - ack_time) * 1000.0

        if status == "SUCCESS":
            if duration_ms >= self._critical_threshold_ms:
                status = "CRITICAL_SLOW"
            elif duration_ms >= self._very_slow_threshold_ms:
                status = "VERY_SLOW"
            elif duration_ms >= self._slow_threshold_ms:
                status = "SLOW"
            else:
                status = "NORMAL"

        completed = CompletedCommandRecord(
            interaction_id=interaction.id,
            command_name=cmd_name,
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            ack_latency_ms=round(ack_latency_ms, 2),
            processing_latency_ms=round(processing_latency_ms, 2),
            duration_ms=round(duration_ms, 2),
            status=status,
            error_id=error_id,
        )
        self._recent_history.append(completed)

        if duration_ms >= 1500.0 or status in ("VERY_SLOW", "CRITICAL_SLOW", "FAILED"):
            logger.info(
                f"\n--- RAI COMMAND WATCHDOG ---\n"
                f"Command: /{cmd_name}\n"
                f"ACK Latency: {ack_latency_ms:.1f}ms\n"
                f"Processing Latency: {processing_latency_ms:.1f}ms\n"
                f"Total Latency: {duration_ms:.1f}ms\n"
                f"Status: {status}\n"
                f"----------------------------"
            )

        return duration_ms

    async def _stuck_command_supervisor(self) -> None:
        """Background loop that detects stuck commands exceeding 15 seconds."""
        while True:
            try:
                await asyncio.sleep(5)
                now = time.perf_counter()
                stuck: List[ActiveCommandRecord] = []
                for rec in list(self._active_commands.values()):
                    if (now - rec.received_at) > 15.0:
                        stuck.append(rec)

                for rec in stuck:
                    elapsed = round(now - rec.received_at, 1)
                    logger.error(
                        f"[Watchdog ALERT] Command /{rec.command_name} (ID: {rec.interaction_id}) "
                        f"has been executing for {elapsed}s without responding! User: {rec.user_id}"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in CommandWatchdog supervisor loop: {e}")

    def get_performance_summary(self) -> Dict[str, Any]:
        """Calculates in-memory latency percentiles, error rates, and throughput."""
        if not self._recent_history:
            return {
                "total_commands": 0,
                "active_commands": len(self._active_commands),
                "avg_duration_ms": 0.0,
                "avg_ack_ms": 0.0,
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "slow_count": 0,
                "failed_count": 0,
            }

        durations = sorted([r.duration_ms for r in self._recent_history])
        ack_latencies = [r.ack_latency_ms for r in self._recent_history]
        total = len(durations)
        avg = sum(durations) / total
        avg_ack = sum(ack_latencies) / total
        p50 = durations[int(total * 0.50)]
        p95 = durations[min(int(total * 0.95), total - 1)]

        slow_count = sum(1 for r in self._recent_history if r.status in ("SLOW", "VERY_SLOW", "CRITICAL_SLOW"))
        failed_count = sum(1 for r in self._recent_history if r.status == "FAILED")

        return {
            "total_commands": total,
            "active_commands": len(self._active_commands),
            "avg_duration_ms": round(avg, 2),
            "avg_ack_ms": round(avg_ack, 2),
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "slow_count": slow_count,
            "failed_count": failed_count,
        }
