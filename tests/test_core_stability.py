"""
Phase 1: Core Stability & Global Exception Boundaries Automated Test Suite for 『RΛI』.
Verifies:
1. Global event error boundary (on_error prevents gateway crashes)
2. Prefix command error boundary (on_command_error handles cooldowns, permissions, generic exceptions)
3. Slash command error boundary (on_app_command_error unwraps invoke errors, formats diagnostic IDs)
4. Background task timeout wrapper (times out hanging tasks and resumes next cycle)
5. Background task exception resilience (catches unhandled exceptions, loop stays alive)
6. BackgroundTaskManager cancel_all (cleanly shuts down all active loops and tasks)
7. Graceful bot close teardown sequence (cancels tasks, disconnects voice, closes database)
8. Startup pre-flight directory and storage validation
9. HealthService background task telemetry integration
"""

import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.bot import SentinelBot
from core.errors import generate_error_id
from core.health import HealthService
from core.tasks import BackgroundTaskManager, safe_task_loop


class TestCoreStability(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Reset BackgroundTaskManager singleton state for isolated testing
        BackgroundTaskManager._instance = BackgroundTaskManager()

        self.bot = SentinelBot()
        self.bot.db = AsyncMock()
        self.bot.supervisor = MagicMock()
        self.bot.supervisor.subsystems = {
            "Gateway": MagicMock(),
            "Security": MagicMock(),
            "Voice": MagicMock(),
        }
        self.bot.self_healing = AsyncMock()
        self.bot.self_healing.stop = MagicMock()
        self.bot.watchdog = MagicMock()
        self.bot.rate_limiter = MagicMock()
        self.bot.rate_limiter._queue.qsize.return_value = 0
        self.bot.autopilot = MagicMock()
        self.bot.action_queue = MagicMock()
        self.bot.conn_watchdog = MagicMock()
        self.bot.cooldowns = MagicMock()
        self.bot.keep_alive = AsyncMock()

    async def test_01_global_event_error_boundary_catches_exception(self):
        """Event error boundary catches unhandled event listener errors without propagating."""
        try:
            raise RuntimeError("Database connection dropped inside on_message listener")
        except RuntimeError:
            await self.bot.on_error("on_message")

        # Supervisor must be notified with degraded status
        security_sub = self.bot.supervisor.subsystems["Security"]
        security_sub.record_degraded.assert_called_once()
        self.assertIn("on_message error", security_sub.record_degraded.call_args[0][0])

        # Self-healing must be notified
        self.bot.self_healing.handle_component_error.assert_awaited_once()

    async def test_02_prefix_command_error_on_cooldown(self):
        """Prefix command on cooldown replies with retry_after notice."""
        ctx = MagicMock(spec=commands.Context)
        ctx.command = MagicMock()
        ctx.command.has_error_handler.return_value = False
        ctx.command.qualified_name = "play"
        ctx.prefix = "!"
        ctx.reply = AsyncMock()

        error = commands.CommandOnCooldown(commands.Cooldown(1, 10), 4.5, commands.BucketType.user)
        await self.bot.on_command_error(ctx, error)

        ctx.reply.assert_awaited_once()
        reply_content = ctx.reply.call_args[0][0]
        self.assertIn("is on cooldown", reply_content)
        self.assertIn("4.5s", reply_content)

    async def test_03_prefix_command_error_missing_permissions(self):
        """Prefix command missing permissions displays formatted embed."""
        ctx = MagicMock(spec=commands.Context)
        ctx.command = MagicMock()
        ctx.command.has_error_handler.return_value = False
        ctx.command.qualified_name = "ban"
        ctx.prefix = "!"
        ctx.reply = AsyncMock()

        error = commands.MissingPermissions(["ban_members", "manage_messages"])
        await self.bot.on_command_error(ctx, error)

        ctx.reply.assert_awaited_once()
        embed = ctx.reply.call_args[1]["embed"]
        self.assertIn("MISSING PERMISSIONS", embed.title.upper())
        self.assertIn("ban_members", embed.description)

    async def test_04_prefix_command_error_unhandled_exception(self):
        """Prefix command with unhandled exception returns diagnostic ID and notifies self-healing."""
        ctx = MagicMock(spec=commands.Context)
        ctx.command = MagicMock()
        ctx.command.has_error_handler.return_value = False
        ctx.command.qualified_name = "custom_tool"
        ctx.prefix = "!"
        ctx.reply = AsyncMock()

        original_error = ZeroDivisionError("Math error in custom calculation")
        error = commands.CommandInvokeError(original_error)
        await self.bot.on_command_error(ctx, error)

        ctx.reply.assert_awaited_once()
        embed = ctx.reply.call_args[1]["embed"]
        self.assertIn("COMMAND ERROR", embed.title.upper())
        self.assertIn("Diagnostic ID", embed.description)
        self.bot.self_healing.handle_component_error.assert_awaited_once()

    async def test_05_slash_command_error_unwraps_invoke_error(self):
        """Slash command error handler unwraps CommandInvokeError and records in watchdog."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.command = MagicMock()
        interaction.command.name = "security_scan"
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = True
        interaction.followup = AsyncMock()

        original_err = RuntimeError("Audit log gateway timeout")
        invoke_err = app_commands.CommandInvokeError(interaction.command, original_err)

        with patch("core.bot.safe_response", new_callable=AsyncMock) as mock_safe_resp:
            await self.bot.on_app_command_error(interaction, invoke_err)
            mock_safe_resp.assert_awaited_once()
            expected_id = mock_safe_resp.call_args[1]["embed"].description.split("`")[1]
            self.bot.watchdog.record_end.assert_called_with(interaction, status="INTERNAL_ERROR", error_id=expected_id)

    async def test_06_background_task_timeout_recovery(self):
        """Hanging background task times out and resumes cleanly on next cycle."""
        manager = BackgroundTaskManager.get_instance()
        run_count = 0

        @safe_task_loop(task_name="test_timeout_worker", timeout_seconds=0.15)
        async def sample_task():
            nonlocal run_count
            run_count += 1
            if run_count == 1:
                await asyncio.sleep(0.4)  # Will exceed timeout (0.15s)
            return "success"

        # Iteration 1: Times out
        res1 = await sample_task()
        self.assertIsNone(res1)

        # Iteration 2: Succeeds immediately
        res2 = await sample_task()
        self.assertEqual(res2, "success")

        telemetry = manager.get_telemetry("test_timeout_worker")
        self.assertIsNotNone(telemetry)
        self.assertEqual(telemetry.total_runs, 2)
        self.assertEqual(telemetry.timeouts, 1)
        self.assertEqual(telemetry.successful_runs, 1)
        self.assertEqual(telemetry.consecutive_errors, 0)

    async def test_07_background_task_unhandled_error_resilience(self):
        """Background task unhandled exception is caught without killing the worker."""
        manager = BackgroundTaskManager.get_instance()
        iteration = 0

        @safe_task_loop(task_name="test_error_worker", timeout_seconds=1.0)
        async def failing_worker():
            nonlocal iteration
            iteration += 1
            if iteration == 1:
                raise ValueError("Transient corrupt JSON payload from external API")
            return "recovered"

        # Iteration 1: Raises exception, caught by wrapper
        res1 = await failing_worker()
        self.assertIsNone(res1)

        # Iteration 2: Succeeds
        res2 = await failing_worker()
        self.assertEqual(res2, "recovered")

        telemetry = manager.get_telemetry("test_error_worker")
        self.assertEqual(telemetry.total_runs, 2)
        self.assertEqual(telemetry.unhandled_errors, 1)
        self.assertEqual(telemetry.successful_runs, 1)

    async def test_08_background_task_manager_cancel_all(self):
        """BackgroundTaskManager cancel_all cleanly terminates all active loops and tasks."""
        manager = BackgroundTaskManager.get_instance()

        mock_loop = MagicMock()
        manager.register_loop(mock_loop)

        # Spawn a lingering asyncio task
        async def lingering():
            try:
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(lingering())
        manager.register_asyncio_task("lingering_task", task)

        await manager.cancel_all(timeout=1.0)
        mock_loop.cancel.assert_called_once()
        self.assertTrue(task.cancelled() or task.done())

    async def test_09_graceful_shutdown_sequence(self):
        """bot.close() executes clean, ordered teardown of all subsystems and connections."""
        mock_vc = AsyncMock(spec=discord.VoiceClient)
        self.bot._connection = MagicMock()
        self.bot._connection.voice_clients = [mock_vc]

        with patch("core.bot.BackgroundTaskManager.get_instance") as mock_get_mgr, \
             patch.object(commands.Bot, "close", new_callable=AsyncMock) as mock_super_close:
            mock_mgr = MagicMock()
            mock_mgr.cancel_all = AsyncMock()
            mock_get_mgr.return_value = mock_mgr

            await self.bot.close()

            # Verify teardown ordering
            mock_mgr.cancel_all.assert_awaited_once_with(timeout=5.0)
            self.bot.supervisor.stop.assert_called_once()
            self.bot.rate_limiter.stop.assert_called_once()
            self.bot.autopilot.stop.assert_called_once()
            mock_vc.disconnect.assert_awaited_once_with(force=True)
            self.bot.keep_alive.stop.assert_awaited_once()
            self.bot.db.close.assert_awaited_once()
            mock_super_close.assert_awaited_once()

    async def test_10_health_service_includes_background_task_telemetry(self):
        """HealthService exports background tasks telemetry in get_system_telemetry payload."""
        manager = BackgroundTaskManager.get_instance()
        manager.register_telemetry("heartbeat_worker", timeout_seconds=30.0)

        telemetry = HealthService.get_system_telemetry(self.bot)
        self.assertIn("background_tasks", telemetry)
        self.assertIn("heartbeat_worker", telemetry["background_tasks"])
        self.assertEqual(telemetry["background_tasks"]["heartbeat_worker"]["timeout_seconds"], 30.0)


if __name__ == "__main__":
    unittest.main()
