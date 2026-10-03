"""
Unit and integration test suite for the RAI Workflow Engine subsystem.
Tests:
- Migration 27 database schema & persistence
- Workflow creation, steps, and CRUD operations
- Action Registry and permission validation
- Conditional logic evaluation (AND, OR, NOT)
- Sequential action execution & retry policies
- Persistent delay scheduling & timer state machine
- Bot restart recovery & missed schedule handling (SKIP, RUN_ONCE, CATCH_UP)
- Loop and recursion depth protection
- 100% Safe Dry-run simulation mode (zero live mutations)
- Natural language workflow parsing & preview generation
"""

import asyncio
import datetime
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite

from config.permissions import PermissionLevel
from core.nl_control import NLActionDispatcher, NLIntent, NLSessionContext, ParsedTask
from core.workflow import (
    CronParser,
    DEFAULT_WORKFLOW_TEMPLATES,
    ActionRiskLevel,
    FailurePolicy,
    MissedSchedulePolicy,
    TriggerType,
    WorkflowActionDefinition,
    WorkflowActionRegistry,
    WorkflowConditionEvaluator,
    WorkflowEngine,
    WorkflowStatus,
)
from database.database import Database
from database.migrations import run_migrations
from database.models import (
    Workflow,
    WorkflowExecution,
    WorkflowStep,
    WorkflowWaitingTimer,
)


class TestWorkflowEngine(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Create a temporary SQLite database for testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_workflows.db"
        self.db = Database(self.db_path)
        await self.db.connect()

        # Mock Bot
        self.bot = MagicMock()
        self.bot.db = self.db

        # Mock Guild, Owner, and Members
        self.guild = MagicMock()
        self.guild.id = 77770001
        self.guild.name = "Test Workflow Guild"
        self.guild.owner_id = 99990001

        self.owner = MagicMock()
        self.owner.id = 99990001
        self.owner.name = "TestOwner"
        self.owner.guild = self.guild
        self.owner.guild_permissions.administrator = True
        self.owner.roles = []

        self.admin = MagicMock()
        self.admin.id = 88880001
        self.admin.name = "TestAdmin"
        self.admin.guild = self.guild
        self.admin.guild_permissions.administrator = True
        self.admin.roles = []

        self.member = MagicMock()
        self.member.id = 55550001
        self.member.name = "TestMember"
        self.member.guild = self.guild
        self.member.guild_permissions.administrator = False
        self.member.roles = []

        self.guild.get_member.side_effect = lambda uid: {
            99990001: self.owner,
            88880001: self.admin,
            55550001: self.member,
        }.get(uid)

        self.bot.get_guild.return_value = self.guild

    async def asyncTearDown(self):
        await self.db.close()
        self.temp_dir.cleanup()

    # =========================================================================
    # 1. DATABASE & MIGRATION 27 TESTS
    # =========================================================================

    async def test_01_database_persistence_and_crud(self):
        """Verify workflow and step persistence, retrieval, status updates, and deletion."""
        wf = Workflow(
            id="wf_test_01",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Daily Maintenance",
            description="Daily backup and cleanup",
            status="ACTIVE",
            trigger_type="daily",
            trigger_config={"hour": 2},
        )
        saved_wf = await self.db.create_workflow(wf)
        self.assertEqual(saved_wf.id, "wf_test_01")

        # Fetch
        fetched = await self.db.get_workflow("wf_test_01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Daily Maintenance")
        self.assertEqual(fetched.trigger_config.get("hour"), 2)

        # Add steps
        step1 = WorkflowStep(
            id="st_1",
            workflow_id="wf_test_01",
            step_order=1,
            action_type="backup.create",
            risk_level="LOW",
        )
        step2 = WorkflowStep(
            id="st_2",
            workflow_id="wf_test_01",
            step_order=2,
            action_type="health.check",
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step1)
        await self.db.add_workflow_step(step2)

        steps = await self.db.get_workflow_steps("wf_test_01")
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].action_type, "backup.create")
        self.assertEqual(steps[1].action_type, "health.check")

        # Status update
        await self.db.update_workflow_status("wf_test_01", "PAUSED")
        updated = await self.db.get_workflow("wf_test_01")
        self.assertEqual(updated.status, "PAUSED")

        # Delete
        await self.db.delete_workflow_steps("wf_test_01")
        await self.db.delete_workflow("wf_test_01")
        self.assertIsNone(await self.db.get_workflow("wf_test_01"))
        self.assertEqual(len(await self.db.get_workflow_steps("wf_test_01")), 0)

    # =========================================================================
    # 2. CONDITION EVALUATION TESTS (AND, OR, NOT)
    # =========================================================================

    async def test_02_condition_evaluation_logic(self):
        """Test logical evaluation including AND, OR, NOT and role/health conditions."""
        # Simple atomic check
        role_mock = MagicMock()
        role_mock.id = 11112222
        self.member.roles = [role_mock]

        cond_role = {"type": "member_has_role", "role_id": 11112222, "user_id": self.member.id}
        res_role = await WorkflowConditionEvaluator.evaluate(self.bot, self.guild, cond_role, {})
        self.assertTrue(res_role)

        cond_not_role = {"type": "member_has_role", "role_id": 99998888, "user_id": self.member.id}
        res_not_role = await WorkflowConditionEvaluator.evaluate(self.bot, self.guild, cond_not_role, {})
        self.assertFalse(res_not_role)

        # Logical AND
        cond_and = {
            "AND": [
                {"type": "member_has_role", "role_id": 11112222, "user_id": self.member.id},
                {"type": "time_between", "start_hour": 0, "end_hour": 24},
            ]
        }
        res_and = await WorkflowConditionEvaluator.evaluate(self.bot, self.guild, cond_and, {})
        self.assertTrue(res_and)

        # Logical OR
        cond_or = {
            "OR": [
                {"type": "member_has_role", "role_id": 99998888, "user_id": self.member.id},  # False
                {"type": "time_between", "start_hour": 0, "end_hour": 24},  # True
            ]
        }
        res_or = await WorkflowConditionEvaluator.evaluate(self.bot, self.guild, cond_or, {})
        self.assertTrue(res_or)

        # Logical NOT
        cond_not = {
            "NOT": {"type": "member_has_role", "role_id": 99998888, "user_id": self.member.id}
        }
        res_not = await WorkflowConditionEvaluator.evaluate(self.bot, self.guild, cond_not, {})
        self.assertTrue(res_not)

    # =========================================================================
    # 3. ACTION EXECUTION & RETRY POLICY TESTS
    # =========================================================================

    async def test_03_workflow_execution_and_retry(self):
        """Test sequential step execution with retry policy and success report."""
        wf = Workflow(
            id="wf_exec_test",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Sequential Test",
            status="ACTIVE",
            trigger_type="scheduled",
        )
        await self.db.create_workflow(wf)

        # Step 1: Health check
        step1 = WorkflowStep(
            id="s1",
            workflow_id="wf_exec_test",
            step_order=1,
            action_type="health.check",
            risk_level="LOW",
        )
        # Step 2: Send report
        step2 = WorkflowStep(
            id="s2",
            workflow_id="wf_exec_test",
            step_order=2,
            action_type="report.send",
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step1)
        await self.db.add_workflow_step(step2)

        # Execute
        with patch("core.workflow.HealthService.check") as mock_health:
            rep_mock = MagicMock()
            rep_mock.overall_status = "HEALTHY"
            mock_health.return_value = rep_mock

            result = await WorkflowEngine.execute_workflow(
                self.bot, self.guild, "wf_exec_test", trigger_event="test_run"
            )

            self.assertEqual(result["status"], "SUCCESS")
            self.assertEqual(len(result["step_results"]), 2)
            self.assertEqual(result["step_results"][0]["status"], "SUCCESS")
            self.assertEqual(result["step_results"][1]["status"], "SUCCESS")

        # Verify DB execution record
        execs = await self.db.list_workflow_executions(self.guild.id, "wf_exec_test")
        self.assertEqual(len(execs), 1)
        self.assertEqual(execs[0].status, "COMPLETED")

    # =========================================================================
    # 4. DELAY & WAITING TIMERS TESTS
    # =========================================================================

    async def test_04_delay_wait_and_timer_persistence(self):
        """Test delay step creates a persistent waiting timer and suspends execution."""
        wf = Workflow(
            id="wf_delay_test",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Delay Pipeline",
            status="ACTIVE",
            trigger_type="member_join",
        )
        await self.db.create_workflow(wf)

        step1 = WorkflowStep(
            id="sd1",
            workflow_id="wf_delay_test",
            step_order=1,
            action_type="delay.wait",
            action_config={"seconds": 60},  # > 3s creates persistent timer
            risk_level="LOW",
        )
        step2 = WorkflowStep(
            id="sd2",
            workflow_id="wf_delay_test",
            step_order=2,
            action_type="report.send",
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step1)
        await self.db.add_workflow_step(step2)

        result = await WorkflowEngine.execute_workflow(
            self.bot, self.guild, "wf_delay_test", trigger_event="member_join"
        )

        self.assertEqual(result["status"], "WAITING")
        self.assertEqual(result["next_step"], 2)

        # Verify waiting timer in database
        timers = await self.db.get_due_waiting_timers(max_resume_iso="2099-01-01T00:00:00")
        self.assertEqual(len(timers), 1)
        self.assertEqual(timers[0].workflow_id, "wf_delay_test")
        self.assertEqual(timers[0].status, "WAITING")
        self.assertEqual(timers[0].next_step_order, 2)

    # =========================================================================
    # 5. BOT RESTART RECOVERY & MISSED SCHEDULES
    # =========================================================================

    async def test_05_restart_recovery_and_missed_schedule_policies(self):
        """Verify bot restart recovers overdue timers according to missed schedule policy."""
        # Workflow with RUN_ONCE policy
        wf = Workflow(
            id="wf_recover_test",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Recoverable Workflow",
            status="ACTIVE",
            trigger_type="daily",
            missed_schedule_policy="RUN_ONCE",
        )
        await self.db.create_workflow(wf)

        step1 = WorkflowStep(
            id="sr1",
            workflow_id="wf_recover_test",
            step_order=1,
            action_type="health.check",
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step1)

        # Create execution record for the timer to reference (foreign key)
        exec_past = WorkflowExecution(
            id="EXEC_PAST_001",
            workflow_id="wf_recover_test",
            guild_id=self.guild.id,
            trigger_event="daily_scheduled",
            status="WAITING",
            current_step_order=1,
            started_at="2020-01-01T00:00:00",
        )
        await self.db.create_workflow_execution(exec_past)

        # Create an expired timer from when bot was supposedly offline
        past_iso = "2020-01-01T00:00:00"
        timer = WorkflowWaitingTimer(
            id="tmr_past_1",
            execution_id="EXEC_PAST_001",
            workflow_id="wf_recover_test",
            guild_id=self.guild.id,
            resume_at=past_iso,
            next_step_order=1,
            status="WAITING",
        )
        await self.db.create_waiting_timer(timer)

        # Execute recovery
        with patch.object(WorkflowEngine, "execute_workflow", new_callable=AsyncMock) as mock_exec:
            res = await WorkflowEngine.recover_after_restart(self.bot)
            self.assertEqual(res["resumed"], 1)
            self.assertEqual(res["cancelled"], 0)

        # Verify timer marked completed
        due = await self.db.get_due_waiting_timers()
        self.assertEqual(len(due), 0)

    # =========================================================================
    # 6. SIMULATION LAB: 100% DRY-RUN VERIFICATION
    # =========================================================================

    async def test_06_simulation_never_mutates_discord_or_executes_destructive(self):
        """Verify simulation mode executes all steps in dry-run with ZERO Discord mutations."""
        wf = Workflow(
            id="wf_sim_test",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Dangerous Simulation Workflow",
            status="ACTIVE",
            trigger_type="manual",
        )
        await self.db.create_workflow(wf)

        step1 = WorkflowStep(
            id="sim_s1",
            workflow_id="wf_sim_test",
            step_order=1,
            action_type="backup.create",
            risk_level="LOW",
        )
        step2 = WorkflowStep(
            id="sim_s2",
            workflow_id="wf_sim_test",
            step_order=2,
            action_type="room.cleanup",
            risk_level="MEDIUM",
        )
        step3 = WorkflowStep(
            id="sim_s3",
            workflow_id="wf_sim_test",
            step_order=3,
            action_type="channel.delete",
            action_config={"channel_id": 12345},
            risk_level="HIGH",
        )
        await self.db.add_workflow_step(step1)
        await self.db.add_workflow_step(step2)
        await self.db.add_workflow_step(step3)

        # Execute in SIMULATION mode
        sim_res = await WorkflowEngine.execute_workflow(
            self.bot, self.guild, "wf_sim_test", trigger_event="simulation", is_simulation=True
        )

        self.assertEqual(sim_res["status"], "SUCCESS")
        self.assertTrue(sim_res["is_simulation"])
        self.assertEqual(len(sim_res["step_results"]), 3)

        for s in sim_res["step_results"]:
            self.assertEqual(s["status"], "SUCCESS")
            self.assertTrue(s["result"].get("simulated", False))

        # Crucial check: verify that NO database executions were written for simulation
        db_execs = await self.db.list_workflow_executions(self.guild.id, "wf_sim_test")
        self.assertEqual(len(db_execs), 0)

    # =========================================================================
    # 7. NATURAL LANGUAGE WORKFLOW CREATION & PREVIEW
    # =========================================================================

    async def test_07_natural_language_workflow_planner_and_preview(self):
        """Verify NL query translates to preview embed and interactive confirmation view."""
        query = "Rai, every Sunday backup the server, check health, and send me a report"
        session = NLSessionContext(guild_id=self.guild.id, user_id=self.owner.id, channel_id=123)

        task = ParsedTask(intent=NLIntent.WORKFLOW_CREATE, raw_segment=query, confidence=1.0, entities={"query": query})
        channel_mock = MagicMock()

        res = await NLActionDispatcher.dispatch(
            self.bot, self.guild, self.owner, channel_mock, task, session
        )

        self.assertTrue(res.success)
        self.assertEqual(res.title, "Workflow Preview")
        self.assertIn("RAI WORKFLOW PREVIEW", res.embed.title)
        self.assertIsNotNone(res.confirmation_payload)
        self.assertIn("view", res.confirmation_payload)

        # Simulate clicking [Activate] in the preview view
        view = res.confirmation_payload["view"]
        interaction_mock = MagicMock()
        interaction_mock.user = self.owner
        interaction_mock.response.edit_message = AsyncMock()
        interaction_mock.followup.send = AsyncMock()

        await view.activate_btn.callback(interaction_mock)

        # Verify workflow is now active in database
        saved_wfs = await self.db.list_workflows(self.guild.id)
        self.assertEqual(len(saved_wfs), 1)
        self.assertEqual(saved_wfs[0].trigger_type, "weekly")
        self.assertEqual(saved_wfs[0].status, "ACTIVE")

        # Verify steps were saved
        steps = await self.db.get_workflow_steps(saved_wfs[0].id)
        action_types = [s.action_type for s in steps]
        self.assertIn("backup.create", action_types)
        self.assertIn("health.check", action_types)
        self.assertIn("report.send", action_types)

    # =========================================================================
    # 8. LOOP & RECURSION DEPTH PROTECTION
    # =========================================================================

    async def test_08_loop_and_recursion_depth_protection(self):
        """Verify workflow halts when max execution depth is exceeded."""
        wf = Workflow(
            id="wf_loop_test",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Recursive Loop Workflow",
            status="ACTIVE",
            trigger_type="scheduled",
        )
        await self.db.create_workflow(wf)

        step1 = WorkflowStep(
            id="st_loop_1",
            workflow_id="wf_loop_test",
            step_order=1,
            action_type="health.check",
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step1)

        # Execute with simulated depth = 5 (max allowed depth)
        context = {"_execution_depth": 5}
        res = await WorkflowEngine.execute_workflow(
            self.bot, self.guild, "wf_loop_test", trigger_event="recurse", context=context
        )

        self.assertEqual(res["status"], "FAILED")
        self.assertIn("recursion", res["error"].lower())

    # =========================================================================
    # 9. CREATOR PERMISSION REVALIDATION
    # =========================================================================

    async def test_09_creator_permission_revalidation(self):
        """Verify that if creator is a normal member, admin actions are denied."""
        # Non-admin creator
        wf = Workflow(
            id="wf_perm_test",
            guild_id=self.guild.id,
            creator_id=self.member.id,
            name="Unauthorized Admin Workflow",
            status="ACTIVE",
            trigger_type="scheduled",
        )
        await self.db.create_workflow(wf)

        step1 = WorkflowStep(
            id="st_perm_1",
            workflow_id="wf_perm_test",
            step_order=1,
            action_type="backup.create",  # Requires ADMIN
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step1)

        res = await WorkflowEngine.execute_workflow(
            self.bot, self.guild, "wf_perm_test", trigger_event="manual"
        )

        self.assertEqual(res["status"], "PERMISSION_DENIED")
        self.assertIn("permission denied", res["error"].lower())

    # =========================================================================
    # 10. CONCURRENT EXECUTION RATE LIMITS
    # =========================================================================

    async def test_10_concurrent_execution_limits_per_guild(self):
        """Verify per-guild concurrency limits prevent overwhelming bot resources."""
        # Fill active tracking to maximum (10)
        from core.workflow import MAX_CONCURRENT_PER_GUILD

        WorkflowEngine._active_executions_by_guild[self.guild.id] = {f"EXEC_{i}" for i in range(MAX_CONCURRENT_PER_GUILD)}

        wf = Workflow(
            id="wf_limit_test",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Rate Limited Workflow",
            status="ACTIVE",
            trigger_type="scheduled",
        )
        await self.db.create_workflow(wf)

        step1 = WorkflowStep(
            id="st_lim_1",
            workflow_id="wf_limit_test",
            step_order=1,
            action_type="health.check",
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step1)

        try:
            res = await WorkflowEngine.execute_workflow(
                self.bot, self.guild, "wf_limit_test", trigger_event="manual"
            )
            self.assertEqual(res["status"], "RATE_LIMITED")
        finally:
            WorkflowEngine._active_executions_by_guild[self.guild.id].clear()

    # =========================================================================
    # 11. WORKFLOW TEMPLATES & INSTANTIATION
    # =========================================================================

    async def test_11_workflow_templates_and_instantiation(self):
        """Verify built-in templates are defined and can be loaded/saved."""
        self.assertGreaterEqual(len(DEFAULT_WORKFLOW_TEMPLATES), 7)
        weekly_maint = next((t for t in DEFAULT_WORKFLOW_TEMPLATES if t["id"] == "tmpl-weekly-maintenance"), None)
        self.assertIsNotNone(weekly_maint)
        self.assertEqual(weekly_maint["config"]["trigger_type"], "weekly")
        self.assertEqual(len(weekly_maint["config"]["steps"]), 5)

    # =========================================================================
    # 12. CRON PARSER & SCHEDULING TESTS
    # =========================================================================

    def test_12_cron_parser_validation_and_parsing(self):
        """Test standard 5-part cron syntax validation, ranges, steps, and aliases."""
        # Valid expressions
        self.assertTrue(CronParser.validate_expression("*/15 * * * *")[0])
        self.assertTrue(CronParser.validate_expression("0 2 * * SUN")[0])
        self.assertTrue(CronParser.validate_expression("30 9 1,15 * 1-5")[0])
        self.assertTrue(CronParser.validate_expression("@daily")[0])
        self.assertTrue(CronParser.validate_expression("@weekly")[0])
        self.assertTrue(CronParser.validate_expression("@hourly")[0])

        # Invalid expressions
        self.assertFalse(CronParser.validate_expression("not a cron")[0])
        self.assertFalse(CronParser.validate_expression("* * * *")[0])  # 4 parts
        self.assertFalse(CronParser.validate_expression("65 * * * *")[0])  # minute > 59
        self.assertFalse(CronParser.validate_expression("* 25 * * *")[0])  # hour > 23
        self.assertFalse(CronParser.validate_expression("*/0 * * * *")[0])  # step 0
        self.assertFalse(CronParser.validate_expression("* * * * INVALID_DAY")[0])

        # Parsing details
        mins, hours, doms, months, dows = CronParser.parse("*/20 2-4 1 * MON,FRI")
        self.assertEqual(mins, {0, 20, 40})
        self.assertEqual(hours, {2, 3, 4})
        self.assertEqual(doms, {1})
        self.assertEqual(months, set(range(1, 13)))
        self.assertEqual(dows, {1, 5})

    def test_13_cron_parser_is_due_and_next_run(self):
        """Test is_due evaluation and jumping get_next_run algorithm."""
        # Fixed point in time: Friday, October 2, 2026, 14:30 UTC
        test_dt = datetime.datetime(2026, 10, 2, 14, 30, tzinfo=datetime.timezone.utc)

        # Due checks
        self.assertTrue(CronParser.is_due("*/15 * * * *", test_dt))
        self.assertTrue(CronParser.is_due("30 14 * * 5", test_dt)) # 5 = Friday
        self.assertTrue(CronParser.is_due("30 14 * * FRI", test_dt))
        self.assertFalse(CronParser.is_due("*/15 * * * SUN", test_dt)) # Not Sunday
        self.assertFalse(CronParser.is_due("0 14 * * *", test_dt)) # Minute 30 != 0

        # Next run calculations
        next_15 = CronParser.get_next_run("*/15 * * * *", test_dt)
        self.assertEqual(next_15, datetime.datetime(2026, 10, 2, 14, 45, tzinfo=datetime.timezone.utc))

        next_sun = CronParser.get_next_run("0 2 * * SUN", test_dt)
        self.assertEqual(next_sun, datetime.datetime(2026, 10, 4, 2, 0, tzinfo=datetime.timezone.utc))

        desc = CronParser.get_human_description("*/15 * * * *")
        self.assertEqual(desc, "Every 15 minutes")

    async def test_14_cron_workflow_scheduled_sweep(self):
        """Test check_scheduled_workflows triggers active cron workflow and prevents duplicates."""
        now = datetime.datetime.now(datetime.timezone.utc)
        current_cron = f"{now.minute} {now.hour} * * *"

        wf = Workflow(
            id="wf_cron_sched_01",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Cron Active Automation",
            status="ACTIVE",
            trigger_type="cron",
            trigger_config={"cron": current_cron},
        )
        await self.db.create_workflow(wf)
        step = WorkflowStep(
            id="st_cron_1", workflow_id="wf_cron_sched_01", step_order=1,
            action_type="health.check", risk_level="LOW"
        )
        await self.db.add_workflow_step(step)

        with patch.object(WorkflowEngine, "execute_workflow", new_callable=AsyncMock) as mock_exec:
            # First sweep should trigger
            triggered = await WorkflowEngine.check_scheduled_workflows(self.bot)
            self.assertEqual(triggered, 1)
            mock_exec.assert_called_once()

            # Second sweep in the same minute must NOT trigger (duplicate prevention)
            triggered_again = await WorkflowEngine.check_scheduled_workflows(self.bot)
            self.assertEqual(triggered_again, 0)


if __name__ == "__main__":
    unittest.main()
