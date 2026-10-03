"""
Central Command Execution Boundary and Error Isolation Layer for RAI.
Ensures every command executes inside an isolated error boundary with:
- Standardized error taxonomy (11 types)
- Unique request and diagnostic IDs
- Execution telemetry (start_time, duration, outcome)
- Safe user-facing feedback without leaking internal stack traces
- Zero cascading failures into Gateway, Music, Dynamic VC, Security, or Workers
"""

from __future__ import annotations

import asyncio
import enum
import logging
import random
import string
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, Optional, TypeVar, Union

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import error_embed

logger = logging.getLogger("Rai.CommandBoundary")

T = TypeVar("T")


def generate_command_request_id() -> str:
    """Generates unique request ID e.g. RAI-CMD-A9B8C7"""
    chars = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"RAI-CMD-{chars}"


class CommandErrorCode(str, enum.Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    DISCORD_API_ERROR = "DISCORD_API_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"


@dataclass
class CommandExecutionContext:
    request_id: str
    diagnostic_id: str
    guild_id: Optional[int]
    user_id: int
    command_name: str
    module_name: str
    start_time: float = field(default_factory=time.time)
    duration: float = 0.0
    result: str = "PENDING"
    error_code: Optional[CommandErrorCode] = None
    error_message: Optional[str] = None
    user_facing_message: Optional[str] = None

    def complete(self, result: str = "SUCCESS") -> None:
        self.duration = round(time.time() - self.start_time, 4)
        self.result = result

    def fail(self, error_code: CommandErrorCode, user_facing_message: str, internal_message: Optional[str] = None) -> None:
        self.duration = round(time.time() - self.start_time, 4)
        self.result = "FAILED"
        self.error_code = error_code
        self.user_facing_message = user_facing_message
        self.error_message = internal_message or user_facing_message


class CommandExecutionBoundary:
    """
    Central execution boundary for slash commands, context commands, and prefix commands.
    Catches, classifies, records, and safely handles any failure without affecting other subsystems.
    """

    _recent_contexts: Dict[str, CommandExecutionContext] = {}
    _max_recent_history: int = 100

    @classmethod
    def classify_exception(cls, exc: Exception) -> tuple[CommandErrorCode, str]:
        """Classify any exception into standard 11 error codes and safe user message."""
        original = getattr(exc, "original", exc)

        # 1. Rate Limit
        if isinstance(original, (commands.CommandOnCooldown, app_commands.CommandOnCooldown)):
            retry_after = getattr(original, "retry_after", 1.0)
            return (
                CommandErrorCode.RATE_LIMIT_ERROR,
                f"This action is cooling down. Please wait {round(retry_after, 1)}s before trying again.",
            )

        # 2. Permissions
        if isinstance(
            original,
            (
                commands.MissingPermissions,
                app_commands.MissingPermissions,
                commands.BotMissingPermissions,
                app_commands.BotMissingPermissions,
                commands.CheckFailure,
                app_commands.CheckFailure,
            ),
        ):
            if isinstance(original, (commands.MissingPermissions, app_commands.MissingPermissions)):
                perms = ", ".join(f"`{p}`" for p in getattr(original, "missing_permissions", []))
                return (
                    CommandErrorCode.PERMISSION_ERROR,
                    f"You lack the required permissions to perform this command:\n{perms}",
                )
            if isinstance(original, (commands.BotMissingPermissions, app_commands.BotMissingPermissions)):
                perms = ", ".join(f"`{p}`" for p in getattr(original, "missing_permissions", []))
                return (
                    CommandErrorCode.PERMISSION_ERROR,
                    f"『RΛI』 requires the following permissions to complete this operation:\n{perms}",
                )
            return (
                CommandErrorCode.PERMISSION_ERROR,
                "Permission denied. You do not meet the role or administrative policy criteria.",
            )

        # 3. Validation / Arguments
        if isinstance(original, (commands.BadArgument, commands.MissingRequiredArgument)):
            return (
                CommandErrorCode.VALIDATION_ERROR,
                f"Invalid or missing command arguments: {original}",
            )

        # 4. Timeout
        if isinstance(original, (asyncio.TimeoutError, TimeoutError)):
            return (
                CommandErrorCode.TIMEOUT_ERROR,
                "The requested operation timed out while waiting for a response. Please try again.",
            )

        # 5. Discord API / Forbidden / NotFound
        if isinstance(original, discord.NotFound):
            return (
                CommandErrorCode.NOT_FOUND,
                "The requested Discord resource (channel, role, message, or user) was not found or has been deleted.",
            )
        if isinstance(original, discord.Forbidden):
            return (
                CommandErrorCode.PERMISSION_ERROR,
                "Discord API rejected this operation (HTTP 403 Forbidden). Rai lacks role hierarchy or channel permissions.",
            )
        if isinstance(original, discord.HTTPException):
            if original.status == 429:
                return (
                    CommandErrorCode.RATE_LIMIT_ERROR,
                    "Discord API rate limit hit. The operation was aborted to protect bot responsiveness.",
                )
            return (
                CommandErrorCode.DISCORD_API_ERROR,
                f"Discord API communication error (HTTP {original.status}). Please try again shortly.",
            )

        # 6. Database
        exc_str = str(original).lower()
        if "sqlite" in exc_str or "database" in exc_str or "locked" in exc_str or "db" in exc_str:
            return (
                CommandErrorCode.DATABASE_ERROR,
                "A storage coordination delay occurred. Local state remains preserved.",
            )

        # 7. Providers (Audio, REST APIs, etc.)
        if "youtube" in exc_str or "yt-dlp" in exc_str or "ffmpeg" in exc_str or "stream" in exc_str:
            return (
                CommandErrorCode.PROVIDER_ERROR,
                "External media provider was unable to fulfill the request.",
            )

        # 8. Configuration
        if "config" in exc_str or "missing setting" in exc_str:
            return (
                CommandErrorCode.CONFIGURATION_ERROR,
                "Server configuration for this module is incomplete or invalid.",
            )

        # 9. Conflict
        if "conflict" in exc_str or "already active" in exc_str or "duplicate" in exc_str:
            return (
                CommandErrorCode.CONFLICT,
                "The requested action conflicts with an active session or lock.",
            )

        # Default: Internal Error
        return (
            CommandErrorCode.INTERNAL_ERROR,
            "An unexpected operational condition occurred. Subsystems remain isolated and stable.",
        )

    @classmethod
    def create_context(
        cls,
        command_name: str,
        module_name: str,
        user_id: int,
        guild_id: Optional[int] = None,
    ) -> CommandExecutionContext:
        req_id = generate_command_request_id()
        ctx = CommandExecutionContext(
            request_id=req_id,
            diagnostic_id=req_id,
            guild_id=guild_id,
            user_id=user_id,
            command_name=command_name,
            module_name=module_name,
        )
        cls._recent_contexts[req_id] = ctx
        if len(cls._recent_contexts) > cls._max_recent_history:
            oldest = next(iter(cls._recent_contexts))
            cls._recent_contexts.pop(oldest, None)
        return ctx

    @classmethod
    async def execute_isolated(
        cls,
        command_name: str,
        module_name: str,
        interaction_or_ctx: Union[discord.Interaction, commands.Context],
        coro: Coroutine[Any, Any, T],
    ) -> Optional[T]:
        """
        Executes a command coroutine within an isolated boundary.
        If an exception is raised, it is caught, classified, and communicated
        to the user via an ephemeral response with a Diagnostic ID.
        """
        user_id = (
            interaction_or_ctx.user.id
            if isinstance(interaction_or_ctx, discord.Interaction)
            else interaction_or_ctx.author.id
        )
        guild_id = (
            interaction_or_ctx.guild_id
            if isinstance(interaction_or_ctx, discord.Interaction)
            else (interaction_or_ctx.guild.id if interaction_or_ctx.guild else None)
        )

        ctx = cls.create_context(command_name, module_name, user_id, guild_id)

        try:
            res = await coro
            ctx.complete("SUCCESS")
            logger.info(
                f"[BOUNDARY] {ctx.request_id} | {command_name} ({module_name}) -> SUCCESS in {ctx.duration*1000:.1f}ms"
            )
            return res
        except Exception as exc:
            err_code, safe_msg = cls.classify_exception(exc)
            ctx.fail(err_code, safe_msg, internal_message=str(exc))
            logger.error(
                f"[BOUNDARY] {ctx.request_id} | {command_name} ({module_name}) -> {err_code.value} in {ctx.duration*1000:.1f}ms: {exc}",
                exc_info=True,
            )

            # Build user safe response embed
            embed = error_embed(
                f"Command Note: {command_name}",
                f"{safe_msg}\n\n"
                f"**Diagnostic Reference:** `{ctx.diagnostic_id}`\n"
                f"**Classification:** `{err_code.value}`\n"
                f"*Core systems and server security remain active.*",
            )

            try:
                if isinstance(interaction_or_ctx, discord.Interaction):
                    if interaction_or_ctx.response.is_done():
                        await interaction_or_ctx.followup.send(embed=embed, ephemeral=True)
                    else:
                        await interaction_or_ctx.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction_or_ctx.reply(embed=embed, delete_after=15.0)
            except Exception as notify_err:
                logger.debug(f"[BOUNDARY] Failed to send error embed to user: {notify_err}")

            return None
