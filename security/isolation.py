"""
Security Subsystem Isolation and Protection Engine.
Guarantees that Security has top priority and is strictly isolated from
audio, music, gaming, or general bot activity.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional, TypeVar
import discord

from core.errors import isolated_boundary
from core.rate_limiter import ResourcePriority

logger = logging.getLogger("Rai.SecurityIsolation")

T = TypeVar("T")


class SecurityIsolationManager:
    """
    Ensures security tasks are never starved, delayed, or crashed by music or other modules.
    """

    @staticmethod
    def run_isolated_task(
        name: str,
        coroutine: Coroutine[Any, Any, Any],
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> asyncio.Task:
        """Spawns an independent asyncio Task guarded by an isolated error boundary."""
        target_loop = loop or asyncio.get_event_loop()

        async def _guarded_runner():
            try:
                await coroutine
            except Exception as e:
                logger.critical(f"🚨 [Security Isolation] Handled isolated exception in '{name}': {e}", exc_info=True)

        return target_loop.create_task(_guarded_runner(), name=f"security_isolated_{name}")

    @staticmethod
    def get_security_priority() -> ResourcePriority:
        """Returns the high priority tier assigned to security interventions."""
        return ResourcePriority.HIGH
