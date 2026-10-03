"""
Interaction Reliability Manager and Safe Response System for Rai Bot.
Prevents "The Rai didn't respond in time" and "Application did not respond" timeouts
by enforcing immediate gateway-level acknowledgement, duplicate prevention,
fault-tolerant responses, error masking with diagnostic Error IDs, and lifecycle tracking.
"""

from __future__ import annotations

import asyncio
import logging
import random
import string
import time
import traceback
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional, Set, Union
import discord
from discord import app_commands

from utils.embeds import error_embed

logger = logging.getLogger("RaiInteraction")

# Whitelist of commands that should default to public (non-ephemeral) display
# By default all user-specific slash commands display ephemerally ("Only you can see this")
PUBLIC_COMMANDS: Set[str] = set()


def generate_error_id() -> str:
    """Generates a random unique diagnostic Error ID like RAI-A8F2K9."""
    chars = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"RAI-{chars}"


class DuplicateInteractionGuard:
    """Short-lived deduplication cache preventing duplicate processing of Discord interactions."""

    def __init__(self, ttl_seconds: float = 60.0):
        self._seen: Dict[int, float] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    def is_duplicate(self, interaction_id: int) -> bool:
        """Returns True if the interaction ID was already seen within the TTL window."""
        now = time.time()
        self._cleanup(now)
        if interaction_id in self._seen:
            return True
        self._seen[interaction_id] = now
        return False

    def _cleanup(self, now: float) -> None:
        cutoff = now - self._ttl
        expired = [iid for iid, ts in self._seen.items() if ts < cutoff]
        for iid in expired:
            self._seen.pop(iid, None)


class InteractionResponseManager:
    """Centralized manager for safe Discord interaction responses and lifecycle routing."""

    _patches_installed = False
    _orig_send_message = None
    _orig_defer = None

    @classmethod
    def install_patches(cls) -> None:
        """
        Transparently wraps discord.InteractionResponse.send_message and defer
        so that every slash command callback automatically edits or follows up
        the deferred interaction without raising InteractionResponded.
        """
        if cls._patches_installed:
            return

        cls._orig_send_message = discord.InteractionResponse.send_message
        cls._orig_defer = discord.InteractionResponse.defer
        cls._orig_webhook_send = discord.Webhook.send

        async def _patched_send_message(self, *args, **kwargs):
            if self.is_done():
                interaction: discord.Interaction = self._parent
                # Strip ephemeral & silent which edit_original_response does not take
                edit_kwargs = {
                    k: v
                    for k, v in kwargs.items()
                    if k not in ("ephemeral", "silent", "delete_after")
                }
                try:
                    return await interaction.edit_original_response(*args, **edit_kwargs)
                except discord.NotFound:
                    # Original message expired or was deleted, fall back to followup
                    try:
                        return await interaction.followup.send(*args, **kwargs)
                    except Exception as e:
                        logger.debug(f"Followup fallback failed for {interaction.id}: {e}")
                        return None
                except Exception as e:
                    # In case of other Discord errors (like message not found), fallback to followup
                    try:
                        return await interaction.followup.send(*args, **kwargs)
                    except Exception:
                        logger.debug(f"edit_original_response fallback failed: {e}")
                        return None

            return await cls._orig_send_message(self, *args, **kwargs)

        async def _patched_defer(self, *args, **kwargs):
            if self.is_done():
                return
            try:
                return await cls._orig_defer(self, *args, **kwargs)
            except (discord.NotFound, discord.InteractionResponded):
                return

        async def _patched_webhook_send(self, *args, **kwargs):
            # For application command interaction followup webhooks, default to ephemeral
            if getattr(self, "type", None) == discord.WebhookType.application:
                if "ephemeral" not in kwargs:
                    kwargs["ephemeral"] = True
            return await cls._orig_webhook_send(self, *args, **kwargs)

        discord.InteractionResponse.send_message = _patched_send_message
        discord.InteractionResponse.defer = _patched_defer
        discord.Webhook.send = _patched_webhook_send
        cls._patches_installed = True
        logger.info("InteractionResponseManager global gateway patches installed.")

    @staticmethod
    async def defer_reply(
        interaction: discord.Interaction,
        ephemeral: bool = True,
        thinking: bool = True,
    ) -> bool:
        """Immediately acknowledges the interaction with deferReply()."""
        return await safe_defer(interaction, ephemeral=ephemeral, thinking=thinking)

    @staticmethod
    async def defer_update(interaction: discord.Interaction) -> bool:
        """Acknowledges button or component interaction with deferUpdate()."""
        if interaction.response.is_done():
            return True
        try:
            await interaction.response.defer(thinking=False)
            return True
        except (discord.NotFound, discord.InteractionResponded):
            return False
        except Exception as e:
            logger.debug(f"defer_update warning for {interaction.id}: {e}")
            return False

    @staticmethod
    async def reply(
        interaction: discord.Interaction,
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        embeds: Optional[list[discord.Embed]] = None,
        view: Optional[discord.ui.View] = None,
        ephemeral: bool = True,
    ) -> Optional[Union[discord.Message, discord.WebhookMessage]]:
        """Safely replies or edits response."""
        return await safe_response(
            interaction,
            content=content,
            embed=embed,
            embeds=embeds,
            view=view,
            ephemeral=ephemeral,
            edit_if_deferred=True,
        )

    @staticmethod
    async def edit_reply(
        interaction: discord.Interaction,
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        embeds: Optional[list[discord.Embed]] = None,
        view: Optional[discord.ui.View] = None,
    ) -> Optional[Union[discord.Message, discord.WebhookMessage]]:
        """Edits an existing deferred response."""
        return await safe_response(
            interaction,
            content=content,
            embed=embed,
            embeds=embeds,
            view=view,
            edit_if_deferred=True,
        )

    @staticmethod
    async def follow_up(
        interaction: discord.Interaction,
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        embeds: Optional[list[discord.Embed]] = None,
        view: Optional[discord.ui.View] = None,
        ephemeral: bool = True,
    ) -> Optional[Union[discord.Message, discord.WebhookMessage]]:
        """Sends a follow-up message after initial reply."""
        return await safe_response(
            interaction,
            content=content,
            embed=embed,
            embeds=embeds,
            view=view,
            ephemeral=ephemeral,
            edit_if_deferred=False,
        )


async def safe_defer(
    interaction: discord.Interaction,
    ephemeral: bool = True,
    thinking: bool = True,
) -> bool:
    """
    Immediately acknowledges the interaction within Discord's 3-second window.
    Returns True if deferral succeeded, or False if already responded or expired.
    """
    if interaction.response.is_done():
        return True

    try:
        await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
        return True
    except (discord.NotFound, discord.InteractionResponded):
        return False
    except Exception as e:
        logger.debug(f"Non-critical safe_defer warning for {interaction.id}: {e}")
        return False


async def safe_response(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    embeds: Optional[list[discord.Embed]] = None,
    view: Optional[discord.ui.View] = None,
    ephemeral: bool = True,
    edit_if_deferred: bool = True,
) -> Optional[Union[discord.Message, discord.WebhookMessage]]:
    """
    Safely responds to an interaction regardless of whether it was deferred,
    already responded to, or requires follow-up. Prevents duplicate initial responses
    and handles expired interactions gracefully.
    """
    kwargs: Dict[str, Any] = {}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if embeds is not None:
        kwargs["embeds"] = embeds
    if view is not None:
        kwargs["view"] = view

    try:
        if interaction.response.is_done():
            # If already acknowledged/deferred
            if edit_if_deferred:
                try:
                    return await interaction.edit_original_response(**kwargs)
                except discord.NotFound:
                    return await interaction.followup.send(ephemeral=ephemeral, **kwargs)
                except Exception:
                    return await interaction.followup.send(ephemeral=ephemeral, **kwargs)
            else:
                return await interaction.followup.send(ephemeral=ephemeral, **kwargs)
        else:
            # Not yet acknowledged
            kwargs["ephemeral"] = ephemeral
            await interaction.response.send_message(**kwargs)
            return await interaction.original_response()

    except discord.NotFound:
        logger.warning(
            f"Interaction {interaction.id} expired before response could be sent. "
            f"Command: {interaction.command.name if interaction.command else 'unknown'}"
        )
        return None
    except discord.InteractionResponded:
        try:
            return await interaction.followup.send(ephemeral=ephemeral, **kwargs)
        except Exception as e:
            logger.error(f"Failed fallback followup after InteractionResponded: {e}")
            return None
    except discord.Forbidden as e:
        logger.warning(f"Forbidden error sending interaction response: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in safe_response: {e}", exc_info=True)
        return None


async def safe_error_response(
    interaction: discord.Interaction,
    error: Union[Exception, str],
    custom_message: Optional[str] = None,
    ephemeral: bool = True,
) -> str:
    """
    Sends a sanitized error embed containing a unique Error ID to the user.
    Logs the full internal traceback with the matching Error ID for administrator diagnosis.
    Never exposes stack traces or sensitive credentials.
    """
    error_id = generate_error_id()
    cmd_name = interaction.command.name if interaction.command else "interaction"

    # Log internal diagnostics with the Error ID
    if isinstance(error, Exception):
        tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        logger.error(f"[{error_id}] Command /{cmd_name} failed: {error}\n{tb_str}")
    else:
        logger.error(f"[{error_id}] Command /{cmd_name} reported error: {error}")

    user_text = (
        custom_message
        or "An unexpected error occurred while executing this command.\n"
        "The error has been logged automatically for security staff."
    )
    embed = error_embed(
        "Request Failed",
        f"{user_text}\n\n**Error ID:** `{error_id}`",
    )

    await safe_response(interaction, embed=embed, ephemeral=ephemeral)
    return error_id


@asynccontextmanager
async def safe_interaction(
    interaction: discord.Interaction,
    ephemeral: bool = False,
    auto_defer: bool = True,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Context manager that guarantees immediate interaction deferral,
    tracks command execution duration, and catches unhandled exceptions
    to prevent "Application did not respond".
    """
    start_time = time.perf_counter()
    ctx_data: Dict[str, Any] = {
        "start_time": start_time,
        "error_id": None,
        "status": "SUCCESS",
    }

    if auto_defer:
        await safe_defer(interaction, ephemeral=ephemeral)

    try:
        yield ctx_data
    except Exception as exc:
        ctx_data["status"] = "FAILED"
        err_id = await safe_error_response(interaction, exc, ephemeral=ephemeral)
        ctx_data["error_id"] = err_id
        if hasattr(interaction.client, "db") and interaction.client.db.is_connected:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            asyncio.create_task(
                interaction.client.db.log_command_metric(
                    command_name=interaction.command.name if interaction.command else "unknown",
                    user_id=interaction.user.id,
                    guild_id=interaction.guild_id,
                    duration_ms=duration_ms,
                    status="FAILED",
                    error_id=err_id,
                )
            )
        raise exc
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        status = ctx_data["status"]
        if status == "SUCCESS":
            if duration_ms > 3000.0:
                status = "VERY_SLOW"
            elif duration_ms > 1000.0:
                status = "SLOW"

        if hasattr(interaction.client, "db") and interaction.client.db.is_connected:
            asyncio.create_task(
                interaction.client.db.log_command_metric(
                    command_name=interaction.command.name if interaction.command else "unknown",
                    user_id=interaction.user.id,
                    guild_id=interaction.guild_id,
                    duration_ms=duration_ms,
                    status=status,
                    error_id=ctx_data.get("error_id"),
                )
            )
