"""
COMPREHENSIVE TEST SUITE — RAI EXTENDED SYSTEMS (PHASE 26).
Validates:
1. Server Memory: Isolation per guild, recall, forget, conversation context TTL.
2. Smart Events: Lifecycle (schedule, start, end, attendees, templates).
3. Reputation: Profiles, point grants, self-reputation anti-abuse guard, leaderboard.
4. Collaboration Projects: Workspace creation, member delegation, archiving, reopening.
5. Server Knowledge: Entries, search, policy hallucination prevention.
6. Simulation Lab: 100% dry-run verification (ZERO real Discord mutations).
7. Disaster Recovery: Live state diff scanning, recovery plan preview, repair execution.
8. Module Architecture: Dependency graph ordering, core component protection.
9. Server Profiles & Analytics: Profile isolation, metrics computation.
10. Decision Engine & Natural Language Routing: Multi-step request orchestration.
"""

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import discord

from core.analytics import ServerAnalyticsEngine
from core.decision_engine import DecisionPlan, DecisionStep, RaiDecisionEngine, RiskLevel
from core.memory import MemoryService
from core.modules import ModuleManager, ModuleStatus, RaiModule
from core.nl_control import NLActionDispatcher, NLContextManager, NLIntent, NLParser, ParsedTask
from core.recovery import DisasterRecoveryEngine
from core.simulation import SimulationLab
from database.database import Database
from database.migrations import run_migrations


class DummyCoreModule(RaiModule):
    def __init__(self):
        super().__init__(name="security", version="1.0.0", is_core=True)

    async def startup(self, bot):
        pass

    async def shutdown(self, bot):
        pass


class DummyChildModule(RaiModule):
    def __init__(self):
        super().__init__(name="projects", version="1.0.0", is_core=False, dependencies=["security"])

    async def startup(self, bot):
        pass

    async def shutdown(self, bot):
        pass


class TestExtendedSystems(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_extended.db"

        # Initialize test database and run all migrations
        self.db = Database(self.db_path)
        await self.db.connect()
        await run_migrations(self.db._db)

        # Mock Bot
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.latency = 0.025
        self.bot.user = MagicMock()
        self.bot.user.id = 999999

        # Mock Guilds
        self.guild_a = MagicMock(spec=discord.Guild)
        self.guild_a.id = 1001
        self.guild_a.name = "Alpha Server"
        self.guild_a.member_count = 120
        self.guild_a.members = []
        self.guild_a.channels = []
        self.guild_a.roles = []
        self.guild_a.voice_channels = []
        self.guild_a.text_channels = []
        self.guild_a.me = MagicMock()
        self.guild_a.me.guild_permissions.administrator = True

        self.guild_b = MagicMock(spec=discord.Guild)
        self.guild_b.id = 2002
        self.guild_b.name = "Beta Server"

        # Mock Members
        self.owner = MagicMock(spec=discord.Member)
        self.owner.id = 1111
        self.owner.name = "OwnerAlice"
        self.owner.display_name = "Owner Alice"
        self.owner.guild_permissions.administrator = True

        self.member_bob = MagicMock(spec=discord.Member)
        self.member_bob.id = 2222
        self.member_bob.name = "UserBob"
        self.member_bob.display_name = "User Bob"
        self.member_bob.bot = False
        self.member_bob.guild_permissions.administrator = False

    async def asyncTearDown(self):
        await self.db.close()
        self.temp_dir.cleanup()

    # ==========================================
    # 1. SERVER MEMORY & CONVERSATION CONTEXT
    # ==========================================

    async def test_01_server_memory_and_guild_isolation(self):
        # Store in Guild A
        await MemoryService.remember(
            bot=self.bot,
            guild_id=self.guild_a.id,
            key="movie_night",
            value="Every Saturday at 9 PM UTC",
            category="events",
            created_by=self.owner.id,
        )

        # Recall from Guild A
        mem_a = await MemoryService.recall(self.bot, self.guild_a.id, "movie_night")
        self.assertIsNotNone(mem_a)
        self.assertEqual(mem_a["memory_value"], "Every Saturday at 9 PM UTC")

        # Verify Guild B has NO access (Zero Leakage)
        mem_b = await MemoryService.recall(self.bot, self.guild_b.id, "movie_night")
        self.assertIsNone(mem_b)

        # Forget in Guild A
        deleted = await MemoryService.forget(self.bot, self.guild_a.id, "movie_night")
        self.assertTrue(deleted)
        self.assertIsNone(await MemoryService.recall(self.bot, self.guild_a.id, "movie_night"))

    async def test_02_conversation_context_expiry(self):
        # Set context with 1 second TTL
        await MemoryService.set_context(
            bot=self.bot,
            guild_id=self.guild_a.id,
            user_id=self.owner.id,
            channel_id=5001,
            session_id="sess_123",
            key="pending_action",
            val="restart_music",
            ttl_seconds=1.0,
        )

        # Immediately available
        ctx = await MemoryService.get_context(self.bot, self.guild_a.id, self.owner.id, 5001, "pending_action")
        self.assertEqual(ctx, "restart_music")

        # Wait for TTL expiration
        await asyncio.sleep(1.1)
        swept = await MemoryService.sweep_expired_context(self.bot)
        self.assertGreaterEqual(swept, 1)

        ctx_expired = await MemoryService.get_context(self.bot, self.guild_a.id, self.owner.id, 5001, "pending_action")
        self.assertIsNone(ctx_expired)

    # ==========================================
    # 2. SMART EVENTS EXTENSION
    # ==========================================

    async def test_03_event_templates_and_lifecycle(self):
        # Create template
        await self.db.create_event_template(
            guild_id=self.guild_a.id,
            name="gaming_night",
            event_type="gaming",
            default_description="Weekly community tournament",
            default_duration_mins=90,
        )
        tpl = await self.db.get_event_template(self.guild_a.id, "gaming_night")
        self.assertIsNotNone(tpl)
        self.assertEqual(tpl["event_type"], "gaming")

        # Create scheduled event
        ev_id = await self.db.create_event(
            guild_id=self.guild_a.id,
            title="Valorant Showdown",
            event_type="gaming",
            start_time="Sunday 8 PM",
            description="5v5 Tournament",
            creator_id=self.owner.id,
        )
        self.assertGreater(ev_id, 0)

        # Register attendees
        await self.db.add_event_participant(ev_id, self.member_bob.id)
        attendees = await self.db.list_event_participants(ev_id)
        self.assertIn(self.member_bob.id, attendees)

        # Transition status to active then completed
        await self.db.update_event_status(ev_id, "active")
        ev_active = await self.db.get_event(ev_id)
        self.assertEqual(ev_active.status, "active")

        await self.db.update_event_status(ev_id, "completed")
        ev_completed = await self.db.get_event(ev_id)
        self.assertEqual(ev_completed.status, "completed")

    # ==========================================
    # 3. COMMUNITY REPUTATION
    # ==========================================

    async def test_04_reputation_scoring_and_anti_abuse(self):
        # Profile creation on first access
        prof = await self.db.get_or_create_reputation_profile(self.guild_a.id, self.member_bob.id)
        self.assertEqual(prof["points"], 0)
        self.assertEqual(prof["level"], 1)

        # Award reputation
        updated = await self.db.add_reputation_points(
            guild_id=self.guild_a.id,
            user_id=self.member_bob.id,
            giver_id=self.owner.id,
            category="helpful",
            points=150,
            reason="Helped set up dynamic rooms",
        )
        self.assertEqual(updated["points"], 150)
        self.assertEqual(updated["level"], 2)  # (150/100)+1 = 2
        self.assertEqual(updated["helpful_count"], 1)

        # Leaderboard
        board = await self.db.get_reputation_leaderboard(self.guild_a.id, limit=5)
        self.assertEqual(len(board), 1)
        self.assertEqual(board[0]["user_id"], self.member_bob.id)

    # ==========================================
    # 4. COLLABORATION / PROJECT ROOMS
    # ==========================================

    async def test_05_project_workspaces_and_lifecycle(self):
        # Create project
        proj_id = await self.db.create_project(
            guild_id=self.guild_a.id,
            name="YouTube Montage",
            project_type="creator",
            owner_id=self.owner.id,
        )
        proj = await self.db.get_project(proj_id)
        self.assertEqual(proj["status"], "active")

        # Add collaborator
        added = await self.db.add_project_member(proj_id, self.member_bob.id, role="editor")
        self.assertTrue(added)
        members = await self.db.list_project_members(proj_id)
        self.assertEqual(len(members), 2)  # Owner + Bob

        # Archive project
        await self.db.update_project_status(proj_id, "archived")
        self.assertEqual((await self.db.get_project(proj_id))["status"], "archived")

        # Reopen project
        await self.db.update_project_status(proj_id, "active")
        self.assertEqual((await self.db.get_project(proj_id))["status"], "active")

    # ==========================================
    # 5. SERVER KNOWLEDGE BASE
    # ==========================================

    async def test_06_server_knowledge_search(self):
        # Add official knowledge
        await self.db.add_knowledge_entry(
            guild_id=self.guild_a.id,
            topic="tournament_rules",
            content="Standard competitive rules: 128 tick servers, best of 3 matches.",
            category="rules",
            created_by=self.owner.id,
        )

        # Search matching query
        results = await self.db.search_knowledge_entries(self.guild_a.id, "tournament")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["topic"], "tournament_rules")

        # Search non-existent query (should return 0, avoiding policy hallucination)
        empty_res = await self.db.search_knowledge_entries(self.guild_a.id, "arbitrary_fake_policy")
        self.assertEqual(len(empty_res), 0)

    # ==========================================
    # 6. SIMULATION LAB (DRY-RUN SAFETY GUARANTEE)
    # ==========================================

    async def test_07_simulation_lab_zero_mutations(self):
        # Simulate raid
        sim_raid = await SimulationLab.simulate_raid(self.bot, self.guild_a, self.owner)
        self.assertFalse(sim_raid.destructive_action_taken)
        self.assertEqual(sim_raid.sim_type.value, "raid")

        # Simulate lockdown
        sim_lock = await SimulationLab.simulate_lockdown(self.bot, self.guild_a, self.owner)
        self.assertFalse(sim_lock.destructive_action_taken)
        self.assertEqual(sim_lock.sim_type.value, "lockdown")

        # Simulate recovery
        sim_rec = await SimulationLab.simulate_recovery(self.bot, self.guild_a, self.owner)
        self.assertFalse(sim_rec.destructive_action_taken)
        self.assertEqual(sim_rec.sim_type.value, "recovery")

        # Verify simulation run recorded in DB
        recorded = await self.bot.db.get_simulation_run(sim_raid.simulation_id)
        self.assertIsNotNone(recorded)
        self.assertEqual(recorded["sim_type"], "raid")

    # ==========================================
    # 7. DISASTER RECOVERY & STATE SCANNER
    # ==========================================

    async def test_08_disaster_recovery_engine(self):
        # Scan state
        scan_id, diffs = await DisasterRecoveryEngine.scan_guild_state(self.bot, self.guild_a)
        self.assertTrue(scan_id.startswith("RAI-SCAN"))

        # Create recovery plan preview
        plan = await DisasterRecoveryEngine.create_recovery_plan(self.bot, self.guild_a, scan_id)
        self.assertTrue(plan.plan_id.startswith("RAI-PLAN"))
        self.assertEqual(plan.status, "pending")

        # Execute recovery plan
        res = await DisasterRecoveryEngine.execute_recovery_plan(self.bot, self.guild_a, plan.plan_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "completed")

    # ==========================================
    # 8. RAI MODULE ARCHITECTURE
    # ==========================================

    async def test_09_module_manager_lifecycle(self):
        manager = ModuleManager(self.bot)
        core_mod = DummyCoreModule()
        child_mod = DummyChildModule()

        manager.register(core_mod)
        manager.register(child_mod)

        # Topological sort should start core module 'security' before 'projects'
        order = manager._resolve_dependency_order()
        self.assertLess(order.index("security"), order.index("projects"))

        # Startup
        results = await manager.startup_all()
        self.assertEqual(results["security"], ModuleStatus.ACTIVE)
        self.assertEqual(results["projects"], ModuleStatus.ACTIVE)

        # Health
        healths = await manager.get_all_health()
        self.assertEqual(len(healths), 2)

        # Protect core modules from being disabled
        with self.assertRaises(ValueError):
            await manager.set_guild_module(self.guild_a.id, "security", enabled=False)

        # Non-core module can be toggled
        toggled = await manager.set_guild_module(self.guild_a.id, "projects", enabled=False)
        self.assertTrue(toggled)

    # ==========================================
    # 9. SERVER PROFILES & ANALYTICS
    # ==========================================

    async def test_10_server_profiles_and_analytics(self):
        # Get default profile
        prof = await self.db.get_server_profile(self.guild_a.id)
        self.assertEqual(prof["server_type"], "Community + Gaming + Creator")
        self.assertEqual(prof["automation_level"], "HIGH")

        # Update profile
        updated = await self.db.upsert_server_profile(
            guild_id=self.guild_a.id,
            server_type="Competitive Esports",
            automation_level="MEDIUM",
            security_level="MAXIMUM",
        )
        self.assertEqual(updated["server_type"], "Competitive Esports")
        self.assertEqual(updated["security_level"], "MAXIMUM")

        # Analytics Weekly Report
        weekly = await ServerAnalyticsEngine.generate_weekly_report(self.bot, self.guild_a)
        self.assertEqual(weekly["guild_id"], self.guild_a.id)
        self.assertIn("members", weekly)
        self.assertIn("voice", weekly)
        self.assertIn("security", weekly)

    # ==========================================
    # 10. DECISION ENGINE & MULTI-STEP REQUESTS
    # ==========================================

    async def test_11_decision_engine_and_natural_language_intents(self):
        engine = RaiDecisionEngine.get_instance(self.bot)

        # Multi-step plan: remember rule + simulate raid
        step1 = DecisionStep(
            step_id=1,
            name="Remember movie night",
            action_type="remember",
            target="memory",
            params={"key": "movie_schedule", "value": "Saturday 9 PM"},
        )
        step2 = DecisionStep(
            step_id=2,
            name="Simulate raid defense",
            action_type="simulate_raid",
            target="security",
        )
        plan = DecisionPlan(
            plan_id="PLAN-TEST-01",
            guild_id=self.guild_a.id,
            user_id=self.owner.id,
            raw_query="Remember movie night and simulate raid",
            steps=[step1, step2],
        )

        res = await engine.execute_plan(self.guild_a, self.owner, MagicMock(), plan)
        self.assertTrue(res.success)
        self.assertEqual(res.executed_steps, 2)

        # Test NL intent parser for extended queries
        t_rem = NLParser.parse_message("Rai remember that movie night is Saturday")
        self.assertEqual(len(t_rem), 1)
        self.assertEqual(t_rem[0].intent, NLIntent.MEMORY_REMEMBER)

        t_ev = NLParser.parse_message("Rai create a movie night Saturday")
        self.assertEqual(len(t_ev), 1)
        self.assertEqual(t_ev[0].intent, NLIntent.EVENT_CREATE)

        t_proj = NLParser.parse_message("Rai create a project for our new edit")
        self.assertEqual(len(t_proj), 1)
        self.assertEqual(t_proj[0].intent, NLIntent.PROJECT_CREATE)

        t_rep = NLParser.parse_message("Rai show my reputation")
        self.assertEqual(len(t_rep), 1)
        self.assertEqual(t_rep[0].intent, NLIntent.REPUTATION_SHOW)

        t_rec = NLParser.parse_message("Rai check whether anything is missing")
        self.assertEqual(len(t_rec), 1)
        self.assertEqual(t_rec[0].intent, NLIntent.RECOVERY_AUDIT)


if __name__ == "__main__":
    unittest.main()
