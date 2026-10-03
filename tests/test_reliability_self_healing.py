"""
Unit and Integration Tests for Rai Reliability, Command Watchdog,
Action Queue, and Autonomous Self-Healing Engine.
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord import app_commands

from utils.interaction_reliability import (
    generate_error_id,
    safe_defer,
    safe_response,
    safe_error_response,
    safe_interaction,
)
from utils.command_watchdog import CommandWatchdog
from utils.action_queue import GlobalActionQueue
from utils.self_healing import RaiSelfHealingEngine, ErrorClassification
from utils.connection_watchdog import DiscordConnectionWatchdog


class TestInteractionReliability(unittest.IsolatedAsyncioTestCase):
    """Tests for safe interaction responses and timeout prevention."""

    async def test_generate_error_id_format(self):
        eid = generate_error_id()
        self.assertTrue(eid.startswith("RAI-"))
        self.assertEqual(len(eid), 10)

    async def test_safe_defer_unresponded(self):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()

        result = await safe_defer(interaction, ephemeral=True)
        self.assertTrue(result)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)

    async def test_safe_defer_already_responded(self):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = True

        result = await safe_defer(interaction)
        self.assertTrue(result)
        interaction.response.defer.assert_not_called()

    async def test_safe_response_initial(self):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()
        interaction.original_response = AsyncMock()

        await safe_response(interaction, content="Hello", ephemeral=True)
        interaction.response.send_message.assert_awaited_once_with(content="Hello", ephemeral=True)

    async def test_safe_response_deferred(self):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = True
        interaction.edit_original_response = AsyncMock()

        await safe_response(interaction, content="Updated", edit_if_deferred=True)
        interaction.edit_original_response.assert_awaited_once_with(content="Updated")

    async def test_safe_response_handles_expired_interaction(self):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.id = 999
        interaction.command = MagicMock(name="test")
        interaction.command.name = "test"
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = False
        # Simulate Discord 10062 Unknown interaction timeout
        interaction.response.send_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Unknown interaction"))

        # Should NOT raise, must return None safely
        res = await safe_response(interaction, content="Late response")
        self.assertIsNone(res)

    async def test_safe_error_response_masks_exception(self):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.command = MagicMock()
        interaction.command.name = "test_cmd"
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()
        interaction.original_response = AsyncMock()

        err_id = await safe_error_response(interaction, RuntimeError("Sensitive internal stack details"))
        self.assertTrue(err_id.startswith("RAI-"))
        interaction.response.send_message.assert_awaited_once()
        sent_embed = interaction.response.send_message.call_args[1]["embed"]
        # Ensure stack trace is NOT exposed in the embed
        self.assertNotIn("Sensitive internal stack details", sent_embed.description)
        self.assertIn(err_id, sent_embed.description)


class TestCommandWatchdog(unittest.IsolatedAsyncioTestCase):
    """Tests for command execution timing and performance percentiles."""

    async def test_watchdog_timing_and_summary(self):
        bot = MagicMock()
        watchdog = CommandWatchdog(bot)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.id = 1001
        interaction.command = MagicMock()
        interaction.command.name = "ping"
        interaction.user = MagicMock(id=555)
        interaction.guild_id = 999

        watchdog.record_start(interaction)
        await asyncio.sleep(0.05)
        duration = watchdog.record_end(interaction, status="SUCCESS")

        self.assertGreater(duration, 40.0)  # > 40ms
        summary = watchdog.get_performance_summary()
        self.assertEqual(summary["total_commands"], 1)
        self.assertEqual(summary["active_commands"], 0)
        self.assertGreater(summary["p50_ms"], 0.0)


class TestGlobalActionQueue(unittest.IsolatedAsyncioTestCase):
    """Tests for priority queuing, deduplication, and execution."""

    async def test_action_queue_deduplication(self):
        bot = MagicMock()
        bot.db = MagicMock()
        bot.db.is_connected = False
        queue = GlobalActionQueue(bot, max_concurrency=1)

        executed = []

        async def action_fn():
            executed.append("done")

        # First enqueue succeeds
        id1 = queue.enqueue(
            guild_id=1,
            action_type="TIMEOUT",
            coroutine_func=action_fn,
            target_id=123,
            priority=GlobalActionQueue.PRIORITY_MEDIUM,
        )
        self.assertIsNotNone(id1)

        # Immediate second enqueue for identical guild:target:action is deduplicated
        id2 = queue.enqueue(
            guild_id=1,
            action_type="TIMEOUT",
            coroutine_func=action_fn,
            target_id=123,
            priority=GlobalActionQueue.PRIORITY_MEDIUM,
        )
        self.assertIsNone(id2)
        self.assertEqual(queue.get_status()["deduplicated"], 1)


class TestSelfHealingEngine(unittest.IsolatedAsyncioTestCase):
    """Tests for error classification, recovery loop, and safe mode."""

    async def test_error_classification(self):
        bot = MagicMock()
        engine = RaiSelfHealingEngine(bot)

        rate_limit_err = discord.RateLimited(4.5)
        self.assertEqual(engine.classify_error(rate_limit_err), ErrorClassification.RATE_LIMIT)

        forbidden_err = discord.Forbidden(MagicMock(), "Missing permissions")
        self.assertEqual(engine.classify_error(forbidden_err), ErrorClassification.PERMISSION_ERROR)

        lock_err = Exception("sqlite3.OperationalError: database is locked")
        self.assertEqual(engine.classify_error(lock_err), ErrorClassification.DATABASE_ERROR)

    async def test_recovery_flow_and_audit(self):
        bot = MagicMock()
        bot.db = AsyncMock()
        bot.db.is_connected = True
        bot.action_queue = MagicMock()

        engine = RaiSelfHealingEngine(bot)
        fake_err = RuntimeError("Action queue worker stalled")

        success = await engine.handle_component_error("action_queue", fake_err)
        self.assertTrue(success)
        bot.db.log_self_healing_record.assert_awaited_once()

    async def test_safe_mode_trigger_on_repeated_failures(self):
        bot = MagicMock()
        bot.db = AsyncMock()
        bot.db.is_connected = False

        engine = RaiSelfHealingEngine(bot)
        engine._max_recovery_attempts = 3

        fake_err = Exception("Corrupt database index")
        for _ in range(3):
            await engine.handle_component_error("database", fake_err)

        self.assertTrue(engine.is_safe_mode)
        metrics = engine.get_health_metrics()
        self.assertIn("database", metrics["degraded_components"])

    async def test_simulate_failure_safe(self):
        bot = MagicMock()
        bot.db = AsyncMock()
        bot.db.is_connected = False
        bot.action_queue = MagicMock()

        engine = RaiSelfHealingEngine(bot)
        res = await engine.simulate_failure("worker")
        self.assertEqual(res["simulation"], "worker_crash")
        self.assertTrue(res["recovery_success"])


class TestConnectionWatchdog(unittest.IsolatedAsyncioTestCase):
    """Tests for gateway latency tracking and instability detection."""

    async def test_connection_status(self):
        bot = MagicMock()
        bot.is_ready.return_value = True
        bot.latency = 0.045  # 45ms

        cw = DiscordConnectionWatchdog(bot)
        self.assertEqual(cw.current_latency_ms, 45.0)

        status = cw.get_status()
        self.assertTrue(status["connected"])
        self.assertEqual(status["latency_ms"], 45.0)
        self.assertFalse(status["is_unstable"])


if __name__ == "__main__":
    unittest.main()
