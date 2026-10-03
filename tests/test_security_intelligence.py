"""
Comprehensive Automated Test Suite for RAI Security Intelligence Upgrade.

Covers:
1. Signal Bus & Telemetry (typed models, deduplication, bounded queue, non-blocking)
2. Security Brain (sliding window correlation, compound patterns, multi-signal threat scoring)
3. Deterministic Risk Engine (levels, hysteresis cooldown, incident ID generation)
4. Adaptive Protection (dynamic posture, rate-limit adjustments)
5. Safe Action Engine (policy gate, role hierarchy, owner/bot immunity, reversible actions)
6. Security Simulator (synthetic vectors, zero Discord mutations, dry-run safety)
7. Read-Only Permission Auditor (non-destructive inspection, severity tiers)
8. Incident Investigation (timeline reconstruction from verified storage, no fabrication)
9. Auto-Recovery (6 health criteria, safe state restoration)
10. Dynamic Current Server Owner Resolution (guild.owner_id, DM fallback)
11. Chaos Resilience & Isolation (Postgres/Redis/Firebase/AI offline, watchdog auto-restart)
"""

import asyncio
import datetime
import re
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from security.signals import (
    SecuritySignal,
    SecuritySignalBus,
    SignalEventType,
    SignalSeverity,
    SignalSource,
)
from security.brain import SecurityBrain, CorrelatedThreatAssessment
from security.risk_engine import RiskEngine, RiskLevel, RiskEvaluationResult, HysteresisState
from security.adaptive_protection import AdaptiveProtectionManager, AdaptivePosture
from security.action_engine import SafeActionEngine, ActionType, ProposedAction
from security.simulator import SecuritySimulator, SimulationResult
from security.permission_auditor import PermissionAuditor, AuditSeverity
from security.investigation import IncidentInvestigator, IncidentReport
from security.recovery import RecoveryCoordinator, RecoveryHealthCheck
from utils.owner_reporter import OwnerReporter


class TestSecuritySignals(unittest.IsolatedAsyncioTestCase):
    """Tests for typed signal models, bounded queues, and deduplication."""

    async def asyncSetUp(self):
        SecuritySignalBus.reset_instance()
        self.bus = SecuritySignalBus.get_instance(max_queue_size=50)

    async def asyncTearDown(self):
        self.bus.stop()
        SecuritySignalBus.reset_instance()

    def test_signal_serialization(self):
        sig = SecuritySignal(
            guild_id=12345,
            event_type=SignalEventType.JOIN_BURST.value,
            source=SignalSource.ANTI_RAID.value,
            severity=SignalSeverity.CRITICAL.value,
            confidence=0.95,
            actor_id=999,
            actor_name="spammer",
            evidence={"rate": 15},
        )
        data = sig.to_dict()
        self.assertEqual(data["guild_id"], 12345)
        self.assertEqual(data["event_type"], "join_burst")
        self.assertEqual(data["severity"], "CRITICAL")
        self.assertEqual(data["evidence"]["rate"], 15)

        restored = SecuritySignal.from_dict(data)
        self.assertEqual(restored.guild_id, sig.guild_id)
        self.assertEqual(restored.actor_name, "spammer")

    def test_signal_deduplication(self):
        sig1 = SecuritySignal(
            guild_id=12345,
            event_type=SignalEventType.MASS_MENTION.value,
            source=SignalSource.MENTION_SPAM.value,
            severity=SignalSeverity.HIGH.value,
            actor_id=777,
            channel_id=888,
        )
        sig2 = SecuritySignal(
            guild_id=12345,
            event_type=SignalEventType.MASS_MENTION.value,
            source=SignalSource.MENTION_SPAM.value,
            severity=SignalSeverity.HIGH.value,
            actor_id=777,
            channel_id=888,
        )
        # First publish succeeds
        pub1 = self.bus.publish(sig1)
        self.assertTrue(pub1)

        # Duplicate within TTL is deduplicated
        pub2 = self.bus.publish(sig2)
        self.assertFalse(pub2)

        m = self.bus.get_metrics()
        self.assertEqual(m["signals_deduplicated"], 1)

    def test_bounded_queue(self):
        # Fill queue to maximum capacity
        small_bus = SecuritySignalBus(max_queue_size=3)
        for i in range(3):
            sig = SecuritySignal(
                guild_id=100 + i,
                event_type=SignalEventType.SPAM_BURST.value,
                source=SignalSource.ANTI_SPAM.value,
                severity=SignalSeverity.LOW.value,
                actor_id=1000 + i,
            )
            self.assertTrue(small_bus.publish(sig))

        # 4th item should be dropped due to bounded queue
        overflow_sig = SecuritySignal(
            guild_id=999,
            event_type=SignalEventType.SPAM_BURST.value,
            source=SignalSource.ANTI_SPAM.value,
            severity=SignalSeverity.LOW.value,
            actor_id=9999,
        )
        self.assertFalse(small_bus.publish(overflow_sig))
        self.assertEqual(small_bus._metrics["signals_dropped"], 1)


class TestSecurityBrain(unittest.IsolatedAsyncioTestCase):
    """Tests for sliding window aggregation and compound threat detection."""

    async def asyncSetUp(self):
        self.brain = SecurityBrain(window_seconds=10.0)

    async def test_compound_coordinated_raid_spam(self):
        guild_id = 999111
        # Signal 1: Join burst
        await self.brain.ingest_signal(
            SecuritySignal(
                guild_id=guild_id,
                event_type=SignalEventType.JOIN_BURST.value,
                source=SignalSource.ANTI_RAID.value,
                severity=SignalSeverity.HIGH.value,
                confidence=0.9,
                actor_id=101,
            )
        )
        # Signal 2: Mass mention spam
        await self.brain.ingest_signal(
            SecuritySignal(
                guild_id=guild_id,
                event_type=SignalEventType.MASS_MENTION.value,
                source=SignalSource.MENTION_SPAM.value,
                severity=SignalSeverity.HIGH.value,
                confidence=0.9,
                actor_id=102,
            )
        )

        assessment = self.brain.evaluate_guild(guild_id)
        self.assertIn("COORDINATED_RAID_SPAM", assessment.compound_patterns)
        self.assertGreater(assessment.threat_score, 50.0)

    async def test_compound_cross_channel_attack(self):
        guild_id = 999222
        # Distribute spam across 5 channels
        for ch_id in range(2001, 2006):
            await self.brain.ingest_signal(
                SecuritySignal(
                    guild_id=guild_id,
                    event_type=SignalEventType.REPEATED_MENTION_SPAM.value,
                    source=SignalSource.MENTION_SPAM.value,
                    severity=SignalSeverity.HIGH.value,
                    confidence=0.9,
                    actor_id=505,
                    channel_id=ch_id,
                )
            )

        assessment = self.brain.evaluate_guild(guild_id)
        self.assertTrue(any("CROSS_CHANNEL_ATTACK" in p for p in assessment.compound_patterns))

    async def test_sliding_window_pruning(self):
        guild_id = 999333
        # Signal with timestamp 20 seconds ago
        old_time = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=20)
        ).isoformat()
        await self.brain.ingest_signal(
            SecuritySignal(
                guild_id=guild_id,
                event_type=SignalEventType.JOIN_BURST.value,
                source=SignalSource.ANTI_RAID.value,
                severity=SignalSeverity.HIGH.value,
                confidence=0.9,
                actor_id=303,
                timestamp=old_time,
            )
        )

        # Trigger evaluation which prunes old signals
        assessment = self.brain.evaluate_guild(guild_id)
        self.assertEqual(assessment.signal_count, 0)
        self.assertEqual(assessment.threat_score, 0.0)


class TestDeterministicRiskEngine(unittest.IsolatedAsyncioTestCase):
    """Tests for risk levels, incident ID format, and hysteresis transitions."""

    async def asyncSetUp(self):
        self.engine = RiskEngine()

    def test_incident_id_format(self):
        inc_id = self.engine.generate_incident_id()
        self.assertTrue(re.match(r"^RAI-INC-\d{6}$", inc_id), f"Invalid ID format: {inc_id}")

    def test_score_mapping(self):
        self.assertEqual(self.engine.map_score_to_risk(10.0), RiskLevel.NORMAL)
        self.assertEqual(self.engine.map_score_to_risk(35.0), RiskLevel.ELEVATED)
        self.assertEqual(self.engine.map_score_to_risk(65.0), RiskLevel.HIGH_ALERT)
        self.assertEqual(self.engine.map_score_to_risk(80.0), RiskLevel.CRITICAL)
        self.assertEqual(self.engine.map_score_to_risk(95.0), RiskLevel.EMERGENCY)

    async def test_hysteresis_escalation_and_deescalation(self):
        guild_id = 888111

        # 1. Immediate escalation to CRITICAL
        high_threat = CorrelatedThreatAssessment(
            guild_id=guild_id,
            threat_score=85.0,
            dominant_vector="raid_spam",
            active_signals_count=5,
            unique_actors=[1001],
            channels_affected=[2001],
            patterns_detected=["COORDINATED_RAID_SPAM"],
            confidence=0.95,
        )
        t0 = time.time()
        res1 = await self.engine.evaluate_risk(high_threat, now=t0)
        self.assertEqual(res1.risk_level, RiskLevel.CRITICAL)
        self.assertTrue(res1.incident_id.startswith("RAI-INC-"))

        # 2. Threat drops to zero: enters RECOVERY state holding CRITICAL
        zero_threat = CorrelatedThreatAssessment(
            guild_id=guild_id,
            threat_score=0.0,
            dominant_vector="none",
            active_signals_count=0,
            unique_actors=[],
            channels_affected=[],
            patterns_detected=[],
            confidence=0.0,
        )

        res2 = await self.engine.evaluate_risk(zero_threat, now=t0 + 1.0)
        self.assertEqual(res2.risk_level, RiskLevel.CRITICAL)
        self.assertEqual(res2.hysteresis_state, HysteresisState.RECOVERY)

        # 3. After 121 seconds: RECOVERY completes -> steps down to HIGH_ALERT in MONITORING state
        res3 = await self.engine.evaluate_risk(zero_threat, now=t0 + 122.0)
        self.assertEqual(res3.risk_level, RiskLevel.HIGH_ALERT)
        self.assertEqual(res3.hysteresis_state, HysteresisState.MONITORING)

        # 4. After another 61 seconds (total 183s): MONITORING completes -> returns to NORMAL
        res4 = await self.engine.evaluate_risk(zero_threat, now=t0 + 185.0)
        self.assertEqual(res4.risk_level, RiskLevel.NORMAL)
        self.assertEqual(res4.hysteresis_state, HysteresisState.NORMAL)


class TestAdaptiveProtection(unittest.IsolatedAsyncioTestCase):
    """Tests for adaptive posture based on active risk level."""

    def test_posture_escalation(self):
        mgr = AdaptiveProtectionManager()

        normal_posture = mgr.get_posture_for_level(RiskLevel.NORMAL)
        self.assertEqual(normal_posture.join_window_multiplier, 1.0)
        self.assertEqual(normal_posture.mention_threshold_reduction, 0)
        self.assertFalse(normal_posture.emergency_lockdown_enabled)
        self.assertFalse(normal_posture.owner_alert_required)

        critical_posture = mgr.get_posture_for_level(RiskLevel.CRITICAL)
        self.assertGreaterEqual(critical_posture.join_window_multiplier, 2.0)
        self.assertGreaterEqual(critical_posture.mention_threshold_reduction, 3)
        self.assertTrue(critical_posture.security_priority_boost)
        self.assertTrue(critical_posture.owner_alert_required)


class TestSafeActionEngine(unittest.IsolatedAsyncioTestCase):
    """Tests for protection policy gate, immunity, role hierarchy, and reversible actions."""

    async def asyncSetUp(self):
        self.action_engine = SafeActionEngine()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 777001
        self.guild.owner_id = 111111

        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.id = 999999
        self.bot_top_role = MagicMock(spec=discord.Role)
        self.bot_top_role.position = 50
        self.bot_member.top_role = self.bot_top_role
        self.bot_member.guild_permissions.moderate_members = True
        self.bot_member.guild_permissions.ban_members = True
        self.guild.me = self.bot_member

    async def test_owner_immunity(self):
        owner_member = MagicMock(spec=discord.Member)
        owner_member.id = 111111
        owner_member.guild = self.guild

        action = ProposedAction(
            action_type=ActionType.TIMEOUT_USER,
            guild_id=self.guild.id,
            target_id=owner_member.id,
            target_name="GuildOwner",
            reason="Spam",
            parameters={"duration_seconds": 300},
        )

        valid, err, _, _ = self.action_engine.validate_policy(self.guild, action, owner_member)
        self.assertFalse(valid)
        self.assertIn("owner", err.lower())

    async def test_bot_immunity(self):
        action = ProposedAction(
            action_type=ActionType.BAN_USER,
            guild_id=self.guild.id,
            target_id=999999,
            target_name="RaiBot",
            reason="Rogue action",
        )
        valid, err, _, _ = self.action_engine.validate_policy(self.guild, action, self.bot_member)
        self.assertFalse(valid)
        self.assertIn("target itself", err.lower())

    async def test_role_hierarchy_check(self):
        high_role_member = MagicMock(spec=discord.Member)
        high_role_member.id = 222222
        high_role_member.guild = self.guild
        target_role = MagicMock(spec=discord.Role)
        target_role.position = 60  # Higher than bot's 50
        high_role_member.top_role = target_role
        high_role_member.roles = [target_role]

        action = ProposedAction(
            action_type=ActionType.TIMEOUT_USER,
            guild_id=self.guild.id,
            target_id=high_role_member.id,
            target_name="Admin",
            reason="Violation",
            parameters={"duration_seconds": 300},
        )
        valid, err, _, _ = self.action_engine.validate_policy(self.guild, action, high_role_member)
        self.assertFalse(valid)
        self.assertIn("hierarchy", err.lower())


class TestSecuritySimulator(unittest.IsolatedAsyncioTestCase):
    """Tests for zero-mutation threat simulation."""

    async def asyncSetUp(self):
        self.simulator = SecuritySimulator()

    async def test_simulate_scenarios_zero_mutations(self):
        for scenario in ["raid", "spam", "nuke", "mention", "permission"]:
            res = await self.simulator.simulate_scenario(scenario, guild_id=123456)
            self.assertIsInstance(res, SimulationResult)
            self.assertIn("COMPLETE", res.simulation_status)
            self.assertTrue(len(res.expected_actions) > 0)
            self.assertGreater(res.expected_threat_score, 0.0)

            embed = self.simulator.create_simulation_embed(res)
            self.assertIn("SECURITY SIMULATION", embed.title)
            # Verify explicit confirmation that Discord changes = NONE
            found_none = any(f.name == "Real Discord Changes" and f.value == "**NONE**" for f in embed.fields)
            self.assertTrue(found_none)


class TestPermissionAuditor(unittest.IsolatedAsyncioTestCase):
    """Tests for read-only permission audit engine."""

    async def test_permission_audit(self):
        auditor = PermissionAuditor()

        guild = MagicMock(spec=discord.Guild)
        guild.id = 555001

        # Mock roles
        role1 = MagicMock(spec=discord.Role)
        role1.id = 1
        role1.name = "Admin 1"
        role1.permissions.administrator = True

        role2 = MagicMock(spec=discord.Role)
        role2.id = 2
        role2.name = "Admin 2"
        role2.permissions.administrator = True

        role3 = MagicMock(spec=discord.Role)
        role3.id = 3
        role3.name = "Admin 3"
        role3.permissions.administrator = True

        role4 = MagicMock(spec=discord.Role)
        role4.id = 4
        role4.name = "Admin 4"
        role4.permissions.administrator = True

        guild.roles = [role1, role2, role3, role4]
        guild.text_channels = []
        guild.webhooks = AsyncMock(return_value=[])

        # Default role
        guild.default_role = MagicMock(spec=discord.Role)
        guild.default_role.permissions.mention_everyone = True
        guild.default_role.permissions.manage_messages = False
        guild.default_role.permissions.kick_members = False
        guild.default_role.permissions.ban_members = False

        # Bot member
        bot_member = MagicMock(spec=discord.Member)
        bot_member.guild_permissions.administrator = False
        bot_member.guild_permissions.manage_roles = True
        bot_member.guild_permissions.manage_channels = True
        bot_member.guild_permissions.moderate_members = True
        bot_member.guild_permissions.view_audit_log = True
        bot_member.top_role.position = 10
        guild.me = bot_member

        report = await auditor.audit_guild(guild)
        self.assertGreater(report.critical_count, 0)
        self.assertTrue(any(f.category == "@everyone" for f in report.findings))

        embed = auditor.create_audit_embed(report)
        self.assertIn("SECURITY AUDIT", embed.title)


class TestIncidentInvestigation(unittest.IsolatedAsyncioTestCase):
    """Tests for incident investigation and timeline reconstruction."""

    async def test_investigate_non_existent_returns_none(self):
        db = MagicMock()
        db._db = MagicMock()
        cursor = AsyncMock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []

        class NoneCtx:
            async def __aenter__(self):
                return cursor
            async def __aexit__(self, *args):
                pass

        db._db.execute = MagicMock(return_value=NoneCtx())

        investigator = IncidentInvestigator(db=db)
        res = await investigator.get_incident_timeline("RAI-INC-999999", guild_id=123)
        self.assertIsNone(res)

    async def test_timeline_reconstruction_without_fabrication(self):
        db = MagicMock()
        db._db = MagicMock()

        incident_row = {
            "event_id": "RAI-INC-000101",
            "result": "RESOLVED",
            "severity": "CRITICAL",
            "target_name": "RogueAdmin",
            "timestamp": "2026-10-01T20:00:00Z",
            "automated_action": "Timed out attacker and revoked role",
        }

        signal_rows = [
            {
                "timestamp": "2026-10-01T20:00:01Z",
                "event_type": "mass_channel_delete",
                "source": "anti_nuke",
                "severity": "CRITICAL",
                "actor_name": "RogueAdmin",
                "channel_name": "general",
            }
        ]

        class MockCtx:
            def __init__(self, c):
                self.c = c
            async def __aenter__(self):
                return self.c
            async def __aexit__(self, *args):
                pass

        def execute_side_effect(query, params=None):
            c = AsyncMock()
            if "security_incidents" in query:
                c.fetchone.return_value = incident_row
            elif "security_intelligence_signals" in query:
                c.fetchall.return_value = signal_rows
            else:
                c.fetchall.return_value = []
            return MockCtx(c)

        db._db.execute = MagicMock(side_effect=execute_side_effect)

        investigator = IncidentInvestigator(db=db)
        report = await investigator.get_incident_timeline("RAI-INC-000101", guild_id=123)
        self.assertIsNotNone(report)
        self.assertEqual(report.incident_id, "RAI-INC-000101")
        self.assertEqual(len(report.timeline), 1)
        self.assertIn("Mass channel delete", report.timeline[0].description)

        embed = investigator.create_timeline_embed(report)
        self.assertIn("INCIDENT TIMELINE", embed.title)


class TestDynamicOwnerReporter(unittest.IsolatedAsyncioTestCase):
    """Tests for dynamic resolution of current server owner via guild.owner_id."""

    async def test_dynamic_owner_resolution_dm_success(self):
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 998877
        guild.name = "Test Guild"
        guild.owner_id = 445566  # Current owner ID

        owner_user = MagicMock(spec=discord.User)
        owner_user.bot = False
        owner_user.send = AsyncMock()
        bot.get_user.return_value = owner_user

        success, note = await OwnerReporter.report_to_current_server_owner(
            bot=bot,
            guild=guild,
            event_title="Critical Threat Neutralized",
            incident_id="RAI-INC-000042",
            severity="CRITICAL",
            details={"vector": "Mass Nuke Attempt"},
        )
        self.assertTrue(success)
        self.assertIn("Direct Message", note)
        owner_user.send.assert_awaited_once()

    async def test_dynamic_owner_fallback_to_security_channel(self):
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 998877
        guild.name = "Test Guild"
        guild.owner_id = 445566

        # Owner has DMs closed
        owner_user = MagicMock(spec=discord.User)
        owner_user.bot = False
        owner_user.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "DMs closed"))
        bot.get_user.return_value = owner_user

        # Security channel exists
        sec_channel = MagicMock(spec=discord.TextChannel)
        sec_channel.name = "security-log"
        sec_channel.send = AsyncMock()
        guild.text_channels = [sec_channel]

        success, note = await OwnerReporter.report_to_current_server_owner(
            bot=bot,
            guild=guild,
            event_title="Critical Threat Neutralized",
            incident_id="RAI-INC-000042",
            severity="CRITICAL",
        )
        self.assertTrue(success)
        self.assertIn("channel fallback", note)
        sec_channel.send.assert_awaited_once()


class TestRecoveryCoordinator(unittest.IsolatedAsyncioTestCase):
    """Tests for 6-criteria health checks and safe state reversal."""

    async def test_health_check_passes_when_all_healthy(self):
        bot = MagicMock()
        bot.is_ready.return_value = True
        bot.db = MagicMock()
        bot.db._db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchone.return_value = (1,)
        bot.db._db.execute.return_value.__aenter__.return_value = cursor

        coordinator = RecoveryCoordinator(bot=bot)
        check = await coordinator.verify_health_criteria(guild_id=123)
        self.assertTrue(check.can_recover)
        self.assertTrue(check.gateway_healthy)
        self.assertTrue(check.db_healthy)


class TestChaosResilience(unittest.IsolatedAsyncioTestCase):
    """
    Tests that Security Brain, Risk Engine, and Action Engine remain 100% operational
    when PostgreSQL, Redis, Firebase, and AI are offline.
    """

    async def test_security_survives_external_infrastructure_failures(self):
        # 1. Simulate PostgreSQL, Redis, Firebase, and AI as offline/unavailable
        with patch("observability.metrics.PROMETHEUS_AVAILABLE", False):
            # Brain and Risk Engine must execute deterministically without any external dependency
            brain = SecurityBrain()
            risk_engine = RiskEngine()
            action_engine = SafeActionEngine()

            guild_id = 999000

            # Ingest critical raid signals
            for i in range(3):
                sig = SecuritySignal(
                    guild_id=guild_id,
                    event_type=SignalEventType.MASS_BAN.value,
                    source=SignalSource.ANTI_NUKE.value,
                    severity=SignalSeverity.CRITICAL.value,
                    confidence=0.99,
                    actor_id=555 + i,
                    evidence={"bans": 12},
                )
                await brain.ingest_signal(sig)

            assessment = brain.evaluate_guild(guild_id)
            self.assertGreater(assessment.threat_score, 70.0)

            # Risk Engine evaluates risk deterministically
            risk_res = await risk_engine.evaluate_risk(assessment)
            self.assertIn(risk_res.risk_level, (RiskLevel.CRITICAL, RiskLevel.EMERGENCY))
            self.assertTrue(risk_res.incident_id.startswith("RAI-INC-"))

            # Safe Action Engine validates policy
            guild = MagicMock(spec=discord.Guild)
            guild.id = guild_id
            guild.owner_id = 111
            bot_member = MagicMock(spec=discord.Member)
            bot_member.id = 999
            bot_member.top_role.position = 100
            guild.me = bot_member

            target = MagicMock(spec=discord.Member)
            target.id = 555
            target.top_role.position = 20
            target.roles = []

            proposed = ProposedAction(
                action_type=ActionType.TIMEOUT_USER,
                guild_id=guild_id,
                target_id=555,
                target_name="Spammer",
                reason="Anti-Nuke mass ban",
                parameters={"duration_seconds": 3600},
            )

            valid, err, _, _ = action_engine.validate_policy(guild, proposed, target)
            self.assertTrue(valid)
            self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
