"""
Production Resilience and Chaos Testing Suite for Rai.
Tests Section 2 & 22 critical reliability requirements:
- Music failure cannot crash Security
- Circuit Breaker trips and isolates external API failures
- Priority queue ensures Security preempts Music under high load
- Database unavailability fallback and recovery
- Supervisor health grid reporting
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
import discord

from core.circuit_breaker import CircuitBreaker, CircuitBreakerRegistry, CircuitState
from core.errors import CircuitBreakerOpenError, MusicPlaybackError, isolated_boundary
from core.rate_limiter import GlobalRateLimiter, ResourcePriority
from core.supervisor import SystemSupervisor, SubsystemHealth
from music.isolation import MusicIsolationManager
from music.queue import BoundedMusicQueue, Track
from security.isolation import SecurityIsolationManager
from security.antiraid import AntiRaidEngine
from security.antinuke import AntiNukeEngine
from security.lockdown import LockdownManager


class TestProductionResilience(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.latency = 0.025
        self.bot.is_ready.return_value = True
        self.bot.is_closed.return_value = False
        self.bot.voice_clients = []
        self.bot.db = AsyncMock()
        self.bot.db.get_or_create_guild_config = AsyncMock(return_value=MagicMock())

        self.supervisor = SystemSupervisor(self.bot)
        self.bot.supervisor = self.supervisor
        self.rate_limiter = GlobalRateLimiter(max_concurrency=2)
        self.bot.rate_limiter = self.rate_limiter

        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 1457382179981099090
        self.guild.name = "Test Guild"

    async def asyncTearDown(self):
        self.supervisor.stop()
        self.rate_limiter.stop()
        CircuitBreakerRegistry.reset_all()

    async def test_music_failure_does_not_crash_security(self):
        """
        CRITICAL TEST (Section 2 & 22):
        Music 💥
        Security 🟢
        Database 🟢
        Gateway 🟢
        """
        security_executed = False

        # 1. Simulate a catastrophic music crash
        @MusicIsolationManager.guard("stream_transcode_crash", fallback_return=None)
        async def crashing_music_task():
            raise RuntimeError("FFmpeg crashed with SIGSEGV / Lavalink disconnected!")

        music_result = await crashing_music_task()
        self.assertIsNone(music_result, "Music failure must be safely intercepted by error boundary")

        # 2. Simulate concurrent high-priority security execution
        async def security_task():
            nonlocal security_executed
            security_executed = True

        task = SecurityIsolationManager.run_isolated_task(
            "anti_raid_mitigation",
            security_task(),
        )
        await task

        self.assertTrue(security_executed, "Security task must execute flawlessly even after music crash")

        # 3. Verify supervisor reflects Music failure while Security is 🟢
        await self.supervisor._check_all_subsystems()
        self.assertEqual(
            self.supervisor.subsystems["Security"].status,
            SubsystemHealth.ONLINE,
            "Security status MUST remain 🟢 despite music crash",
        )

    async def test_circuit_breaker_trips_and_recovers(self):
        """
        Tests Section 16:
        Repeated failures trip the circuit breaker OPEN, failing fast without blocking.
        """
        breaker = CircuitBreaker("test_service", failure_threshold=3, recovery_timeout=0.2)

        async def failing_service():
            raise ConnectionError("External service timeout")

        # 1. First 2 failures (CLOSED)
        with self.assertRaises(ConnectionError):
            await breaker.call(failing_service)
        with self.assertRaises(ConnectionError):
            await breaker.call(failing_service)
        self.assertEqual(breaker.state, CircuitState.CLOSED)

        # 2. 3rd failure TRIPS to OPEN
        with self.assertRaises(ConnectionError):
            await breaker.call(failing_service)
        self.assertEqual(breaker.state, CircuitState.OPEN)

        # 3. Next call must immediately raise CircuitBreakerOpenError without calling service
        with self.assertRaises(CircuitBreakerOpenError):
            await breaker.call(failing_service)

        # 4. Wait for recovery timeout to transition to HALF_OPEN
        await asyncio.sleep(0.25)
        self.assertTrue(breaker.is_available)

        # 5. Successful call resets to CLOSED
        async def working_service():
            return "OK"

        res = await breaker.call(working_service)
        await breaker.record_success()
        self.assertEqual(res, "OK")
        self.assertEqual(breaker.state, CircuitState.CLOSED)

    async def test_priority_queue_security_preempts_music(self):
        """
        Tests Section 15:
        Security tasks MUST jump ahead of queued music actions.
        """
        self.rate_limiter.start()
        execution_order = []

        async def music_work():
            execution_order.append("MUSIC")

        async def security_work():
            execution_order.append("SECURITY")

        # Enqueue 3 music actions first (lower priority = 4)
        for i in range(3):
            await self.rate_limiter.enqueue_action(
                item_id=f"music_{i}",
                guild_id=self.guild.id,
                priority=ResourcePriority.MUSIC,
                work_fn=music_work,
            )

        # Enqueue 1 security action (critical priority = 0)
        await self.rate_limiter.enqueue_action(
            item_id="security_emergency",
            guild_id=self.guild.id,
            priority=ResourcePriority.CRITICAL,
            work_fn=security_work,
        )

        # Wait for queue to drain
        await asyncio.sleep(0.1)

        self.assertIn("SECURITY", execution_order)
        # Verify that SECURITY was processed promptly ahead of low priority items
        self.assertEqual(execution_order[0], "SECURITY")

    async def test_bounded_music_queue_limits(self):
        """
        Tests Section 18:
        Queue does not grow unbounded (max capacity protection).
        """
        queue = BoundedMusicQueue(max_size=5)
        member = MagicMock(spec=discord.Member)
        member.id = 12345
        member.display_name = "DJ Member"

        tracks = [
            Track(f"Track {i}", f"url_{i}", f"stream_{i}", 180, member)
            for i in range(10)
        ]

        # Add 5 items
        for t in tracks[:5]:
            added = await queue.add(t)
            self.assertTrue(added)

        self.assertEqual(len(queue), 5)

        # Adding 6th item must be rejected to prevent memory explosion
        added_overflow = await queue.add(tracks[5])
        self.assertFalse(added_overflow)
        self.assertEqual(len(queue), 5)

    async def test_supervisor_health_report(self):
        """
        Tests Section 3:
        Supervisor generates clean human-readable status table.
        """
        report = self.supervisor.get_health_report()
        self.assertIn("RAI SYSTEM SUPERVISOR HEALTH", report)
        self.assertIn("Gateway", report)
        self.assertIn("Security", report)
        self.assertIn("Music", report)
        self.assertIn("🟢", report)

    async def test_lockdown_and_safe_unlock(self):
        """
        Tests Section 8:
        Lockdown atomically restricts @everyone and safely restores state.
        """
        lockdown_mgr = LockdownManager(self.bot)

        # Mock channels
        ch1 = MagicMock(spec=discord.TextChannel)
        ch1.id = 101
        ch1.name = "general"
        ow1 = MagicMock()
        ow1.send_messages = None
        ch1.overwrites_for.return_value = ow1
        ch1.permissions_for.return_value.manage_channels = True
        ch1.set_permissions = AsyncMock()

        self.guild.text_channels = [ch1]

        # 1. Lock guild
        locked = await lockdown_mgr.lock_guild(self.guild)
        self.assertEqual(locked, 1)
        ch1.set_permissions.assert_awaited_once_with(self.guild.default_role, send_messages=False, reason="Emergency Server Lockdown")

        # 2. Unlock guild
        unlocked = await lockdown_mgr.unlock_guild(self.guild)
        self.assertEqual(unlocked, 1)


if __name__ == "__main__":
    unittest.main()
