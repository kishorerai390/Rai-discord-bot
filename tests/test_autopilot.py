"""
Unit tests for Rai Autopilot Engine, adaptive baselines,
threat simulations, and action audit logs.
"""

from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
import discord

from database.database import Database
from database.models import AutopilotConfig, SecurityBaseline
from utils.autopilot import AutopilotEngine, AutopilotEvent


class TestAutopilotEngine(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db_path = Path(f"data/test_autopilot_{uuid.uuid4().hex[:8]}.db")
        self.db = Database(self.db_path)
        await self.db.connect()

        self.mock_bot = MagicMock()
        self.mock_bot.db = self.db
        self.mock_bot.guilds = []
        self.mock_bot.user = MagicMock()
        self.mock_bot.user.id = 999999999
        self.mock_bot.security_brain = None

        self.engine = AutopilotEngine(self.mock_bot)

    async def asyncTearDown(self):
        self.engine.stop()
        await self.db.close()
        for ext in ["", "-wal", "-shm"]:
            p = Path(f"{self.db_path}{ext}")
            if p.exists():
                try:
                    os.remove(p)
                except Exception:
                    pass

    async def test_autopilot_config_lifecycle(self):
        guild_id = 888111222
        cfg = await self.db.get_or_create_autopilot_config(guild_id)
        self.assertEqual(cfg.guild_id, guild_id)
        self.assertTrue(cfg.enabled)
        self.assertFalse(cfg.dry_run)
        self.assertEqual(cfg.max_safety_level, "HIGH")

        # Update dry_run and safety level
        ok = await self.db.update_autopilot_config(
            guild_id, dry_run=True, max_safety_level="CRITICAL", raid_protection=False
        )
        self.assertTrue(ok)

        updated = await self.db.get_or_create_autopilot_config(guild_id)
        self.assertTrue(updated.dry_run)
        self.assertEqual(updated.max_safety_level, "CRITICAL")
        self.assertFalse(updated.raid_protection)

    async def test_autopilot_action_logging(self):
        guild_id = 888111222
        action_id = await self.db.log_autopilot_action(
            guild_id=guild_id,
            module="ANTI_SPAM",
            trigger="MESSAGE_BURST",
            reason="15 messages in 3 seconds",
            risk_level="MEDIUM",
            action="TIMEOUT",
            result="SUCCESS",
            target_id=12345678,
            target_type="user",
            details="User placed in 10-minute timeout",
        )
        self.assertTrue(action_id.startswith("AP-"))

        actions = await self.db.get_recent_autopilot_actions(guild_id, limit=5)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_id, action_id)
        self.assertEqual(actions[0].module, "ANTI_SPAM")
        self.assertEqual(actions[0].risk_level, "MEDIUM")
        self.assertEqual(actions[0].result, "SUCCESS")

    async def test_security_baseline_lifecycle(self):
        guild_id = 888111222
        baseline = await self.db.get_or_create_security_baseline(guild_id)
        self.assertEqual(baseline.guild_id, guild_id)
        self.assertAlmostEqual(baseline.avg_joins_per_hour, 2.0)

        # Update with new sample
        ok = await self.db.update_security_baseline(
            guild_id=guild_id,
            joins_per_hour=10.0,
            messages_per_min=50.0,
        )
        self.assertTrue(ok)

        updated = await self.db.get_or_create_security_baseline(guild_id)
        self.assertGreater(updated.avg_joins_per_hour, 2.0)
        self.assertGreater(updated.avg_messages_per_min, 10.0)
        self.assertEqual(updated.sample_count, 2)

    async def test_subsystem_health_tracking(self):
        await self.db.update_subsystem_health("SecurityBrain", "HEALTHY", "Optimal throughput")
        await self.db.update_subsystem_health("VoiceGuard", "DEGRADED", "Interface mode fallback")

        health = await self.db.get_all_subsystem_health()
        names = {h.subsystem: h.status for h in health}
        self.assertEqual(names.get("SecurityBrain"), "HEALTHY")
        self.assertEqual(names.get("VoiceGuard"), "DEGRADED")

    async def test_hierarchy_boundary_safety(self):
        guild = MagicMock()
        guild.owner_id = 111111111
        guild.me = MagicMock()
        guild.me.top_role = MagicMock()
        guild.me.top_role.__ge__ = lambda s, o: True
        guild.me.top_role.__lt__ = lambda s, o: False

        # Owner cannot be targeted
        owner = MagicMock()
        owner.id = 111111111
        self.assertFalse(self.engine._can_target_member(guild, owner))

        # Bot itself cannot be targeted
        bot_member = MagicMock()
        bot_member.id = self.mock_bot.user.id
        self.assertFalse(self.engine._can_target_member(guild, bot_member))

        # Member with higher role cannot be targeted
        higher_member = MagicMock()
        higher_member.id = 222222222
        higher_member.top_role = MagicMock()
        higher_member.top_role.__ge__ = lambda s, o: True
        self.assertFalse(self.engine._can_target_member(guild, higher_member))

    async def test_threat_simulations(self):
        guild = MagicMock()
        guild.id = 888111222
        guild.name = "Test Simulation Server"
        guild.system_channel = None
        guild.get_channel = MagicMock(return_value=None)
        guild.me = MagicMock()
        guild.me.id = 123456789
        guild.me.top_role = MagicMock()

        for threat in ["raid", "spam", "nuke", "webhook"]:
            res = await self.engine.simulate_threat(guild, threat)
            self.assertEqual(res["status"], "SIMULATION_SUCCESS")
            self.assertEqual(res["threat_type"], threat)
            self.assertIn("proposed_action", res)
            self.assertIn(res["risk_level"], ["LOW", "MEDIUM", "HIGH", "CRITICAL"])


if __name__ == "__main__":
    unittest.main()
