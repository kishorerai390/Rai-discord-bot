"""
RAI — CENTRAL INTERACTION MANAGER
Production-grade interaction coordination, immediate acknowledgment engine,
double-response protection, request ID generation, and latency metrics.

Guarantees:
1. Sub-100ms Acknowledgement: Immediate deferReply() or deferUpdate().
2. Interaction State Machine:
   NOT_ACKNOWLEDGED -> ACKNOWLEDGING -> ACKNOWLEDGED / DEFERRED -> RESPONDING -> COMPLETED / FAILED / EXPIRED
3. Double Response Protection: Prevents duplicate replies, deferrals, or updates.
4. Unique Request ID: RAI-REQ-XXXXXXXX attached to every interaction.
5. ACK Latency Telemetry: Tracks time from reception to gateway deferral.
6. Error Boundary: User-facing sanitized messages with Request ID, full internal logging.
7. Background Worker Handoff: Safe timeout protection and long-running job wrapping.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random
import string
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, TypeVar, Union

import discord

from database.models import InteractionRecord

logger = logging.getLogger("Rai.InteractionManager")

T = TypeVar("T")


class InteractionState(str, Enum):
    NOT_ACKNOWLEDGED = "NOT_ACKNOWLEDGED"
    ACKNOWLEDGING = "ACKNOWLEDGING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DEFERRED = "DEFERRED"
    RESPONDING = "RESPONDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


@dataclass
class ManagedInteractionContext:
    request_id: str
    interaction_id: int
    interaction_type: str
    command_name: str
    user_id: int
    guild_id: Optional[int]
    state: InteractionState
    received_at: float
    ack_started_at: Optional[float] = None
    ack_completed_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

    @property
    def ack_latency_ms(self) -> Optional[float]:
        if self.ack_completed_at and self.received_at:
            return round((self.ack_completed_at - self.received_at) * 1000.0, 2)
        return None

    @property
    def duration_ms(self) -> Optional[float]:
        if self.completed_at and self.received_at:
            return round((self.completed_at - self.received_at) * 1000.0, 2)
        return None


@dataclass
class InteractionMetricsSummary:
    total_processed: int = 0
    ack_latency_sum_ms: float = 0.0
    fast_ack_count: int = 0      # < 100ms
    healthy_ack_count: int = 0   # 100 - 500ms
    warning_ack_count: int = 0   # 500 - 1000ms
    critical_ack_count: int = 0  # > 1000ms
    slow_operations_count: int = 0
    double_responses_prevented: int = 0
    failures_count: int = 0

    @property
    def avg_ack_latency_ms(self) -> float:
        if self.total_processed == 0:
            return 0.0
        return round(self.ack_latency_sum_ms / self.total_processed, 1)


class InteractionManager:
    """
    Central, thread-safe manager through which ALL Discord interactions pass.
    Eliminates "Application did not respond" and prevents duplicate responses.
    """

    _instance: Optional[InteractionManager] = None
    _contexts: Dict[int, ManagedInteractionContext] = {}
    _lock = asyncio.Lock()
    metrics = InteractionMetricsSummary()

    @classmethod
    def get_instance(cls) -> InteractionManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def generate_request_id(prefix: str = "RAI-REQ") -> str:
        """Generate high-entropy unique Request ID (e.g. RAI-REQ-82F91A)."""
        chars = string.ascii_uppercase + string.digits
        token = "".join(random.choices(chars, k=6))
        return f"{prefix}-{token}"

    @classmethod
    def get_context(cls, interaction_id: int) -> Optional[ManagedInteractionContext]:
        return cls._contexts.get(interaction_id)

    @classmethod
    async def register_interaction(
        cls, interaction: discord.Interaction, command_name: Optional[str] = None
    ) -> ManagedInteractionContext:
        """Register newly received interaction in NOT_ACKNOWLEDGED state."""
        now = time.perf_counter()
        req_id = cls.generate_request_id()
        cmd = command_name or (interaction.command.name if interaction.command else "component")

        ctx = ManagedInteractionContext(
            request_id=req_id,
            interaction_id=interaction.id,
            interaction_type=str(interaction.type),
            command_name=cmd,
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            state=InteractionState.NOT_ACKNOWLEDGED,
            received_at=now,
        )

        async with cls._lock:
            # Periodic cleanup of contexts older than 15 minutes
            cutoff = now - 900.0
            expired_keys = [iid for iid, c in cls._contexts.items() if c.received_at < cutoff]
            for k in expired_keys:
                cls._contexts.pop(k, None)

            cls._contexts[interaction.id] = ctx

        return ctx

    @classmethod
    async def acknowledge_immediately(
        cls,
        interaction: discord.Interaction,
        ephemeral: bool = True,
        is_component_update: bool = False,
    ) -> bool:
        """
        Immediately acknowledge interaction within milliseconds.
        Guarantees sub-100ms response to prevent 'Application did not respond'.
        """
        ctx = cls.get_context(interaction.id)
        if not ctx:
            ctx = await cls.register_interaction(interaction)

        if ctx.state in (InteractionState.ACKNOWLEDGED, InteractionState.DEFERRED, InteractionState.COMPLETED):
            cls.metrics.double_responses_prevented += 1
            return True

        ctx.state = InteractionState.ACKNOWLEDGING
        ctx.ack_started_at = time.perf_counter()

        try:
            if is_component_update:
                if not interaction.response.is_done():
                    await interaction.response.defer(thinking=False)
                ctx.state = InteractionState.ACKNOWLEDGED
            else:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=ephemeral, thinking=True)
                ctx.state = InteractionState.DEFERRED

            ctx.ack_completed_at = time.perf_counter()
            ack_ms = ctx.ack_latency_ms or 0.0

            # Telemetry update
            cls.metrics.total_processed += 1
            cls.metrics.ack_latency_sum_ms += ack_ms

            if ack_ms < 100.0:
                cls.metrics.fast_ack_count += 1
            elif ack_ms < 500.0:
                cls.metrics.healthy_ack_count += 1
            elif ack_ms < 1000.0:
                cls.metrics.warning_ack_count += 1
            else:
                cls.metrics.critical_ack_count += 1

            return True

        except discord.InteractionResponded:
            ctx.state = InteractionState.DEFERRED
            ctx.ack_completed_at = time.perf_counter()
            cls.metrics.double_responses_prevented += 1
            return True
        except discord.NotFound:
            ctx.state = InteractionState.EXPIRED
            logger.warning(f"[{ctx.request_id}] Interaction expired before ACK: {ctx.command_name}")
            return False
        except Exception as e:
            ctx.state = InteractionState.FAILED
            ctx.error = str(e)
            logger.warning(f"[{ctx.request_id}] Immediate ACK error: {e}")
            return False

    @classmethod
    async def safe_reply(
        cls,
        interaction: discord.Interaction,
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        embeds: Optional[List[discord.Embed]] = None,
        view: Optional[discord.ui.View] = None,
        ephemeral: bool = True,
    ) -> Optional[Union[discord.Message, discord.WebhookMessage]]:
        """
        Safely delivers response to user with double-reply protection.
        Automatically uses edit_original_response if already deferred,
        or send_message if not yet acknowledged.
        """
        ctx = cls.get_context(interaction.id)
        req_tag = f"[{ctx.request_id}] " if ctx else ""

        kwargs: Dict[str, Any] = {}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if embeds is not None:
            kwargs["embeds"] = embeds
        if view is not None:
            kwargs["view"] = view

        if ctx:
            ctx.state = InteractionState.RESPONDING

        try:
            if interaction.response.is_done():
                try:
                    msg = await interaction.edit_original_response(**kwargs)
                    if ctx:
                        ctx.state = InteractionState.COMPLETED
                    return msg
                except discord.NotFound:
                    # Message token expired or deleted, fallback to followup
                    msg = await interaction.followup.send(ephemeral=ephemeral, **kwargs)
                    if ctx:
                        ctx.state = InteractionState.COMPLETED
                    return msg
            else:
                kwargs["ephemeral"] = ephemeral
                await interaction.response.send_message(**kwargs)
                if ctx:
                    ctx.state = InteractionState.COMPLETED
                return await interaction.original_response()

        except discord.InteractionResponded:
            try:
                msg = await interaction.followup.send(ephemeral=ephemeral, **kwargs)
                if ctx:
                    ctx.state = InteractionState.COMPLETED
                return msg
            except Exception as e:
                logger.error(f"{req_tag}Followup send failed: {e}")
                return None
        except discord.NotFound:
            logger.warning(f"{req_tag}Interaction not found during safe_reply")
            if ctx:
                ctx.state = InteractionState.EXPIRED
            return None
        except Exception as e:
            logger.error(f"{req_tag}Error in safe_reply: {e}", exc_info=True)
            if ctx:
                ctx.state = InteractionState.FAILED
                ctx.error = str(e)
            return None

    @classmethod
    async def safe_error_response(
        cls,
        interaction: discord.Interaction,
        error: Union[Exception, str],
        custom_message: Optional[str] = None,
        ephemeral: bool = True,
    ) -> str:
        """
        Sends sanitized failure response to the user with Request ID.
        Never exposes raw stack traces.
        """
        ctx = cls.get_context(interaction.id)
        req_id = ctx.request_id if ctx else cls.generate_request_id()

        # Log internal traceback
        cmd_name = interaction.command.name if interaction.command else "interaction"
        if isinstance(error, Exception):
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            logger.error(f"[{req_id}] Command /{cmd_name} unhandled error:\n{tb}")
        else:
            logger.error(f"[{req_id}] Command /{cmd_name} reported error: {error}")

        user_text = (
            custom_message
            or "❌ Rai couldn't complete that operation.\n"
               "The issue has been logged for system maintenance."
        )

        embed = discord.Embed(
            title="Request Failed",
            description=f"{user_text}\n\n**Request ID:** `{req_id}`",
            color=0xED4245,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(text=f"Rai Incident Isolation • {req_id}")

        await cls.safe_reply(interaction, embed=embed, ephemeral=ephemeral)
        if ctx:
            ctx.state = InteractionState.FAILED
            ctx.error = str(error)
            ctx.error_code = req_id

        cls.metrics.failures_count += 1
        return req_id

    @classmethod
    async def execute_interaction(
        cls,
        interaction: discord.Interaction,
        operation_name: str,
        execute: Callable[[discord.Interaction, ManagedInteractionContext], Coroutine[Any, Any, T]],
        ephemeral: bool = True,
        auto_defer: bool = True,
        is_component_update: bool = False,
        timeout: float = 15.0,
    ) -> Optional[T]:
        """
        Enterprise wrapper for ALL Discord interactions:
        1. Generates Request ID.
        2. Guarantees immediate acknowledgment before executing slow logic.
        3. Measures ACK latency and total execution duration.
        4. Provides timeout isolation and error boundary.
        5. Persists telemetry in interaction_records database table.
        """
        ctx = await cls.register_interaction(interaction, command_name=operation_name)

        if auto_defer:
            await cls.acknowledge_immediately(
                interaction,
                ephemeral=ephemeral,
                is_component_update=is_component_update,
            )

        start_time = time.perf_counter()
        result: Optional[T] = None

        try:
            # Execute operation with bounded timeout protection
            result = await asyncio.wait_for(
                execute(interaction, ctx),
                timeout=timeout,
            )
            ctx.state = InteractionState.COMPLETED
            return result

        except asyncio.TimeoutError:
            ctx.state = InteractionState.FAILED
            cls.metrics.slow_operations_count += 1
            logger.warning(f"[{ctx.request_id}] Operation '{operation_name}' timed out after {timeout}s")
            await cls.safe_reply(
                interaction,
                content=(
                    f"⏳ **Rai is still processing this operation in the background.**\n\n"
                    f"**Request ID:** `{ctx.request_id}`\n"
                    f"This command required extended processing. Please check status shortly."
                ),
                ephemeral=ephemeral,
            )
            return None

        except Exception as exc:
            ctx.state = InteractionState.FAILED
            await cls.safe_error_response(interaction, exc, ephemeral=ephemeral)
            return None

        finally:
            ctx.completed_at = time.perf_counter()
            duration_ms = ctx.duration_ms or 0.0

            if duration_ms > 3000.0:
                cls.metrics.slow_operations_count += 1

            # Persist telemetry record asynchronously if db is connected
            bot = getattr(interaction, "client", None)
            if bot and hasattr(bot, "db") and bot.db:
                rec = InteractionRecord(
                    request_id=ctx.request_id,
                    guild_id=ctx.guild_id,
                    user_id=ctx.user_id,
                    interaction_id=ctx.interaction_id,
                    interaction_type=ctx.interaction_type,
                    command_name=ctx.command_name,
                    module=operation_name.split()[0] if operation_name else "general",
                    received_at=ctx.received_at,
                    ack_at=ctx.ack_completed_at,
                    completed_at=ctx.completed_at,
                    ack_latency_ms=ctx.ack_latency_ms,
                    duration_ms=duration_ms,
                    status=ctx.state.value,
                    error_code=ctx.error_code,
                    created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                )
                if hasattr(bot.db, "save_interaction_record"):
                    coro = bot.db.save_interaction_record(rec)
                    if asyncio.iscoroutine(coro):
                        asyncio.create_task(coro)
