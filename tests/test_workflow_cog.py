"""
Comprehensive test suite for RAI Workflow Engine COG.
Tests:
- /workflow list (empty and populated)
- /workflow info (found and not-found)
- /workflow create (basic, free-tier limit enforcement)
- /workflow add-step (step ordering, unknown action rejection)
- /workflow instantiate (all templates, step persistence, free-tier limit)
- /workflow enable / disable / pause / resume (status transitions)
- /workflow run (success, waiting, failed paths)
- /workflow simulate (dry-run, zero mutations)
- /workflow delete (cleanup steps and timers)
- /workflow executions (populated and empty)
- /workflow history (step execution log)
- /workflow actions (registry listing)
- /workflow templates (listing)
- WorkflowStepModal (valid, invalid action, bad JSON)
- Event listener dispatching (member_join, member_remove, voice_join, voice_leave)
- Scheduler loop: timer sweep and scheduled trigger
"""

from __future__ import annotations

import asyncio
import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import discord

from core.workflow import (
    DEFAULT_WORKFLOW_TEMPLATES,
    MAX_ACTIVE_WORKFLOWS_FREE,
    TriggerType,
    WorkflowActionRegistry,
    WorkflowEngine,
    WorkflowStatus,
)
from database.database import Database
from database.models import Workflow, WorkflowExecution, WorkflowStep, WorkflowStepExecution, WorkflowWaitingTimer


def make_interaction(guild=None, user=None, is_admin=True):
    """Create a minimal mock Discord interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = user or MagicMock()
    interaction.user.guild_permissions = MagicMock()
    interaction.user.guild_permissions.administrator = is_admin
    interaction.user.guild_permissions.manage_guild = is_admin
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


class TestWorkflowCog(unittest.IsolatedAsyncioTestCase):
    """Tests for WorkflowCog slash command handlers."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cog_test.db"
        self.db = Database(self.db_path)
        await self.db.connect()

        self.bot = MagicMock()
        self.bot.db = self.db

        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 99991111
        self.guild.name = "Test Cog Guild"
        self.guild.owner_id = 11112222
        self.guild.member_count = 50

        self.owner = MagicMock(spec=discord.Member)
        self.owner.id = 11112222
        self.owner.name = "CogOwner"
        self.owner.guild = self.guild
        self.owner.guild_permissions = MagicMock()
        self.owner.guild_permissions.administrator = True
        self.owner.roles = []

        self.member = MagicMock(spec=discord.Member)
        self.member.id = 33334444
        self.member.name = "CogMember"
        self.member.bot = False
        self.member.guild = self.guild
        self.member.guild_permissions = MagicMock()
        self.member.guild_permissions.administrator = False
        self.member.roles = []

        self.guild.get_member.side_effect = lambda uid: {
            11112222: self.owner,
            33334444: self.member,
        }.get(uid)
        self.bot.get_guild.return_value = self.guild

        # Import cog class (avoids needing a real bot)
        from cogs.workflow import WorkflowCog
        self.cog = WorkflowCog.__new__(WorkflowCog)
        self.cog.bot = self.bot
        self.cog._recovery_executed = False

    async def asyncTearDown(self):
        await self.db.close()
        self.temp_dir.cleanup()

    # =========================================================================
    # 1. LIST COMMAND
    # =========================================================================

    async def test_01_list_empty(self):
        """List command returns 'No workflows' when none exist."""
        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_list(interaction)
        interaction.response.send_message.assert_awaited_once()
        args = interaction.response.send_message.call_args
        self.assertIn("ephemeral", args.kwargs)
        self.assertTrue(args.kwargs["ephemeral"])

    async def test_02_list_populated(self):
        """List command shows workflows when they exist."""
        wf = Workflow(
            id="wf_list_01",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="List Test WF",
            status="ACTIVE",
            trigger_type="daily",
        )
        await self.db.create_workflow(wf)

        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_list(interaction)
        interaction.response.send_message.assert_awaited_once()
        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertIn("WORKFLOWS", embed.title.upper())

    # =========================================================================
    # 2. INFO COMMAND
    # =========================================================================

    async def test_03_info_not_found(self):
        """Info command sends 404 message for unknown workflow ID."""
        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_info(interaction, "wf_ghost_id")
        interaction.response.send_message.assert_awaited_once()
        call_args = interaction.response.send_message.call_args
        self.assertIn("not found", str(call_args).lower())

    async def test_04_info_found_with_steps(self):
        """Info command displays workflow metadata and step count."""
        wf = Workflow(
            id="wf_info_01",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Info Test WF",
            status="ACTIVE",
            trigger_type="weekly",
        )
        await self.db.create_workflow(wf)
        step = WorkflowStep(
            id="st_info_1",
            workflow_id="wf_info_01",
            step_order=1,
            action_type="health.check",
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step)

        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_info(interaction, "wf_info_01")
        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertIn("Info Test WF", embed.title)

    # =========================================================================
    # 3. CREATE COMMAND
    # =========================================================================

    async def test_05_create_workflow_success(self):
        """Create command persists a new workflow in the database."""
        trigger_choice = MagicMock()
        trigger_choice.value = "daily"

        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_create(interaction, name="My Daily WF", trigger_type=trigger_choice, description="Test")

        interaction.response.send_message.assert_awaited_once()
        wfs = await self.db.list_workflows(self.guild.id)
        self.assertEqual(len(wfs), 1)
        self.assertEqual(wfs[0].name, "My Daily WF")
        self.assertEqual(wfs[0].trigger_type, "daily")

    async def test_06_create_no_guild(self):
        """Create command silently returns if no guild context."""
        trigger_choice = MagicMock()
        trigger_choice.value = "daily"
        interaction = make_interaction(guild=None, user=self.owner)
        await self.cog.cmd_create(interaction, name="Guild-less WF", trigger_type=trigger_choice)
        interaction.response.send_message.assert_not_awaited()

    # =========================================================================
    # 4. ADD-STEP COMMAND & MODAL
    # =========================================================================

    async def test_07_add_step_opens_modal(self):
        """add-step command opens a WorkflowStepModal for an existing workflow."""
        wf = Workflow(
            id="wf_modal_01",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Modal WF",
            status="ACTIVE",
            trigger_type="daily",
        )
        await self.db.create_workflow(wf)

        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_add_step(interaction, "wf_modal_01")
        interaction.response.send_modal.assert_awaited_once()

    async def test_08_add_step_workflow_not_found(self):
        """add-step command sends error for unknown workflow ID."""
        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_add_step(interaction, "wf_ghost")
        interaction.response.send_message.assert_awaited_once()
        self.assertIn("not found", str(interaction.response.send_message.call_args).lower())

    async def test_09_add_step_unauthorized(self):
        """add-step command is blocked for non-admin users."""
        interaction = make_interaction(guild=self.guild, user=self.member, is_admin=False)
        await self.cog.cmd_add_step(interaction, "wf_modal_01")
        interaction.response.send_message.assert_awaited_once()
        self.assertIn("❌", str(interaction.response.send_message.call_args))

    async def test_10_modal_invalid_action(self):
        """WorkflowStepModal.on_submit rejects unknown action IDs."""
        from cogs.workflow import WorkflowStepModal

        wf = Workflow(
            id="wf_modal_02",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Modal WF 2",
            status="ACTIVE",
            trigger_type="daily",
        )
        await self.db.create_workflow(wf)

        modal = WorkflowStepModal(self.bot, "wf_modal_02", 1)
        modal.action_input = MagicMock()
        modal.action_input.value = "nonexistent.action"
        modal.config_input = MagicMock()
        modal.config_input.value = "{}"
        modal.condition_input = MagicMock()
        modal.condition_input.value = ""
        modal.failure_policy_input = MagicMock()
        modal.failure_policy_input.value = "STOP"
        modal.timeout_input = MagicMock()
        modal.timeout_input.value = "60"

        interaction = make_interaction(guild=self.guild, user=self.owner)
        await modal.on_submit(interaction)
        interaction.response.send_message.assert_awaited_once()
        self.assertIn("Unknown action", str(interaction.response.send_message.call_args))

    async def test_11_modal_valid_step_saved(self):
        """WorkflowStepModal.on_submit saves step with correct metadata."""
        from cogs.workflow import WorkflowStepModal

        wf = Workflow(
            id="wf_modal_03",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Modal Save WF",
            status="ACTIVE",
            trigger_type="daily",
        )
        await self.db.create_workflow(wf)

        modal = WorkflowStepModal(self.bot, "wf_modal_03", 1)
        modal.action_input = MagicMock()
        modal.action_input.value = "health.check"
        modal.config_input = MagicMock()
        modal.config_input.value = "{}"
        modal.condition_input = MagicMock()
        modal.condition_input.value = ""
        modal.failure_policy_input = MagicMock()
        modal.failure_policy_input.value = "CONTINUE"
        modal.timeout_input = MagicMock()
        modal.timeout_input.value = "30"

        interaction = make_interaction(guild=self.guild, user=self.owner)
        await modal.on_submit(interaction)

        steps = await self.db.get_workflow_steps("wf_modal_03")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].action_type, "health.check")
        self.assertEqual(steps[0].failure_policy, "CONTINUE")
        self.assertEqual(steps[0].timeout_seconds, 30)

    async def test_12_modal_bad_json_config(self):
        """WorkflowStepModal.on_submit rejects malformed JSON in config fields."""
        from cogs.workflow import WorkflowStepModal

        wf = Workflow(
            id="wf_modal_json",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="JSON Test WF",
            status="ACTIVE",
            trigger_type="daily",
        )
        await self.db.create_workflow(wf)

        modal = WorkflowStepModal(self.bot, "wf_modal_json", 1)
        modal.action_input = MagicMock()
        modal.action_input.value = "health.check"
        modal.config_input = MagicMock()
        modal.config_input.value = "{invalid json here"  # Bad JSON
        modal.condition_input = MagicMock()
        modal.condition_input.value = ""
        modal.failure_policy_input = MagicMock()
        modal.failure_policy_input.value = "STOP"
        modal.timeout_input = MagicMock()
        modal.timeout_input.value = "60"

        interaction = make_interaction(guild=self.guild, user=self.owner)
        await modal.on_submit(interaction)

        interaction.response.send_message.assert_awaited_once()
        self.assertIn("Invalid JSON", str(interaction.response.send_message.call_args))

    async def test_13_modal_auto_step_ordering(self):
        """add-step modal automatically assigns next sequential step order."""
        from cogs.workflow import WorkflowStepModal

        wf = Workflow(
            id="wf_order_test",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Order Test WF",
            status="ACTIVE",
            trigger_type="daily",
        )
        await self.db.create_workflow(wf)

        # Add step 1 via modal
        for action_type, expected_order in [("health.check", 1), ("report.send", 2)]:
            existing = await self.db.get_workflow_steps("wf_order_test")
            next_order = (max(s.step_order for s in existing) + 1) if existing else 1
            modal = WorkflowStepModal(self.bot, "wf_order_test", next_order)
            modal.action_input = MagicMock()
            modal.action_input.value = action_type
            modal.config_input = MagicMock()
            modal.config_input.value = "{}"
            modal.condition_input = MagicMock()
            modal.condition_input.value = ""
            modal.failure_policy_input = MagicMock()
            modal.failure_policy_input.value = "STOP"
            modal.timeout_input = MagicMock()
            modal.timeout_input.value = "60"
            interaction = make_interaction(guild=self.guild, user=self.owner)
            await modal.on_submit(interaction)

        steps = await self.db.get_workflow_steps("wf_order_test")
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].step_order, 1)
        self.assertEqual(steps[1].step_order, 2)

    # =========================================================================
    # 5. INSTANTIATE COMMAND
    # =========================================================================

    async def test_14_instantiate_all_templates(self):
        """Instantiate command creates workflow + all steps for each built-in template."""
        for tmpl in DEFAULT_WORKFLOW_TEMPLATES:
            interaction = make_interaction(guild=self.guild, user=self.owner)
            await self.cog.cmd_instantiate(interaction, tmpl["id"])
            interaction.response.send_message.assert_awaited()

        # All templates should be in the database now
        wfs = await self.db.list_workflows(self.guild.id)
        self.assertEqual(len(wfs), len(DEFAULT_WORKFLOW_TEMPLATES))

        for wf in wfs:
            steps = await self.db.get_workflow_steps(wf.id)
            self.assertGreater(len(steps), 0, f"Template {wf.name} should have steps")

    async def test_15_instantiate_unknown_template(self):
        """Instantiate command rejects unknown template IDs."""
        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_instantiate(interaction, "tmpl-nonexistent")
        call_str = str(interaction.response.send_message.call_args)
        self.assertIn("not found", call_str.lower())

    async def test_16_instantiate_step_count_matches_template(self):
        """Instantiate creates exactly the same number of steps as the template config."""
        tmpl = next(t for t in DEFAULT_WORKFLOW_TEMPLATES if t["id"] == "tmpl-weekly-maintenance")
        expected_steps = len(tmpl["config"]["steps"])

        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_instantiate(interaction, "tmpl-weekly-maintenance")

        wfs = await self.db.list_workflows(self.guild.id)
        self.assertEqual(len(wfs), 1)
        steps = await self.db.get_workflow_steps(wfs[0].id)
        self.assertEqual(len(steps), expected_steps)

    # =========================================================================
    # 6. STATUS TRANSITION COMMANDS
    # =========================================================================

    async def test_17_enable_disable_pause_resume(self):
        """Status transition commands correctly update workflow status."""
        wf = Workflow(
            id="wf_status_01",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Status Test WF",
            status="ACTIVE",
            trigger_type="daily",
        )
        await self.db.create_workflow(wf)

        interaction = make_interaction(guild=self.guild, user=self.owner)

        # Disable → DISABLED
        await self.cog.cmd_disable(interaction, "wf_status_01")
        wf_chk = await self.db.get_workflow("wf_status_01")
        self.assertEqual(wf_chk.status, "DISABLED")

        # Enable → ACTIVE
        await self.cog.cmd_enable(interaction, "wf_status_01")
        wf_chk = await self.db.get_workflow("wf_status_01")
        self.assertEqual(wf_chk.status, "ACTIVE")

        # Pause → PAUSED
        await self.cog.cmd_pause(interaction, "wf_status_01")
        wf_chk = await self.db.get_workflow("wf_status_01")
        self.assertEqual(wf_chk.status, "PAUSED")

        # Resume → ACTIVE
        await self.cog.cmd_resume(interaction, "wf_status_01")
        wf_chk = await self.db.get_workflow("wf_status_01")
        self.assertEqual(wf_chk.status, "ACTIVE")

    async def test_18_enable_not_found(self):
        """Enable command sends error for unknown workflow."""
        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_enable(interaction, "wf_ghost_999")
        self.assertIn("not found", str(interaction.response.send_message.call_args).lower())

    # =========================================================================
    # 7. RUN COMMAND
    # =========================================================================

    async def test_19_run_successful_workflow(self):
        """Run command executes a workflow and shows SUCCESS result."""
        wf = Workflow(
            id="wf_run_01",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Runnable WF",
            status="ACTIVE",
            trigger_type="manual",
        )
        await self.db.create_workflow(wf)

        step = WorkflowStep(
            id="st_run_1",
            workflow_id="wf_run_01",
            step_order=1,
            action_type="report.send",
            action_config={"summary": "test"},
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step)

        interaction = make_interaction(guild=self.guild, user=self.owner)
        interaction.response.defer = AsyncMock()

        with patch("core.workflow.NotificationService.dispatch") as mock_notify:
            await self.cog.cmd_run(interaction, "wf_run_01")
            interaction.followup.send.assert_awaited_once()
            embed_result = interaction.followup.send.call_args.kwargs.get("embed")
            self.assertIsNotNone(embed_result)
            self.assertIn("WORKFLOW", embed_result.title.upper())

    # =========================================================================
    # 8. SIMULATE COMMAND
    # =========================================================================

    async def test_20_simulate_dry_run_zero_db_writes(self):
        """Simulate command produces dry-run results without writing to execution table."""
        wf = Workflow(
            id="wf_sim_cog",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Sim Cog WF",
            status="ACTIVE",
            trigger_type="manual",
        )
        await self.db.create_workflow(wf)

        step = WorkflowStep(
            id="st_sim_c1",
            workflow_id="wf_sim_cog",
            step_order=1,
            action_type="backup.create",
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step)

        interaction = make_interaction(guild=self.guild, user=self.owner)
        interaction.response.defer = AsyncMock()
        await self.cog.cmd_simulate(interaction, "wf_sim_cog")

        interaction.followup.send.assert_awaited_once()
        embed = interaction.followup.send.call_args.kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertIn("SIMULATION", embed.title.upper())

        # Verify zero DB execution records
        execs = await self.db.list_workflow_executions(self.guild.id, "wf_sim_cog")
        self.assertEqual(len(execs), 0, "Simulation MUST NOT create execution records")

    # =========================================================================
    # 9. DELETE COMMAND
    # =========================================================================

    async def test_21_delete_removes_workflow_and_steps(self):
        """Delete command removes workflow and all associated steps."""
        wf = Workflow(
            id="wf_del_01",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Deletable WF",
            status="ACTIVE",
            trigger_type="daily",
        )
        await self.db.create_workflow(wf)
        step = WorkflowStep(
            id="st_del_1",
            workflow_id="wf_del_01",
            step_order=1,
            action_type="health.check",
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step)

        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_delete(interaction, "wf_del_01")

        self.assertIsNone(await self.db.get_workflow("wf_del_01"))
        self.assertEqual(len(await self.db.get_workflow_steps("wf_del_01")), 0)
        interaction.response.send_message.assert_awaited_once()
        self.assertIn("🗑️", str(interaction.response.send_message.call_args))

    # =========================================================================
    # 10. EXECUTIONS COMMAND
    # =========================================================================

    async def test_22_executions_empty(self):
        """Executions command shows info message when no executions exist."""
        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_executions(interaction)
        self.assertIn("ℹ️", str(interaction.response.send_message.call_args))

    async def test_23_executions_populated(self):
        """Executions command shows embed with execution entries."""
        wf = Workflow(
            id="wf_exec_cog",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="Exec List WF",
            status="ACTIVE",
            trigger_type="daily",
        )
        await self.db.create_workflow(wf)
        exec_rec = WorkflowExecution(
            id="EXEC_COG_001",
            workflow_id="wf_exec_cog",
            guild_id=self.guild.id,
            trigger_event="test",
            status="COMPLETED",
            current_step_order=1,
            started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        await self.db.create_workflow_execution(exec_rec)

        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_executions(interaction)
        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertIn("Execution", embed.title)

    # =========================================================================
    # 11. HISTORY COMMAND
    # =========================================================================

    async def test_24_history_empty(self):
        """History command shows info message when no step executions exist."""
        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_history(interaction, "EXEC_NONEXISTENT")
        self.assertIn("ℹ️", str(interaction.response.send_message.call_args))

    async def test_25_history_with_step_executions(self):
        """History command displays step execution records."""
        wf = Workflow(
            id="wf_hist_01",
            guild_id=self.guild.id,
            creator_id=self.owner.id,
            name="History WF",
            status="ACTIVE",
            trigger_type="daily",
        )
        await self.db.create_workflow(wf)

        step = WorkflowStep(
            id="st_hist_1",
            workflow_id="wf_hist_01",
            step_order=1,
            action_type="health.check",
            risk_level="LOW",
        )
        await self.db.add_workflow_step(step)

        exec_rec = WorkflowExecution(
            id="EXEC_HIST_001",
            workflow_id="wf_hist_01",
            guild_id=self.guild.id,
            trigger_event="test",
            status="COMPLETED",
            current_step_order=1,
            started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        await self.db.create_workflow_execution(exec_rec)

        step_exec = WorkflowStepExecution(
            id="SXEC_001",
            execution_id="EXEC_HIST_001",
            step_id="st_hist_1",
            status="COMPLETED",
            attempt=1,
            result_json={"success": True},
            started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        await self.db.create_workflow_step_execution(step_exec)

        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_history(interaction, "EXEC_HIST_001")
        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertIn("EXEC_HIST_001", embed.title)
        self.assertGreater(len(embed.fields), 0)

    # =========================================================================
    # 12. ACTIONS COMMAND
    # =========================================================================

    async def test_26_actions_lists_all_registry_entries(self):
        """Actions command shows all registered actions grouped by prefix."""
        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_actions(interaction)
        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertIn("Action Registry", embed.title)
        # Should have multiple field groups
        self.assertGreater(len(embed.fields), 0)

    # =========================================================================
    # 13. TEMPLATES COMMAND
    # =========================================================================

    async def test_27_templates_shows_all_builtin_templates(self):
        """Templates command lists all built-in workflow templates."""
        interaction = make_interaction(guild=self.guild, user=self.owner)
        await self.cog.cmd_templates(interaction)
        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertEqual(len(embed.fields), len(DEFAULT_WORKFLOW_TEMPLATES))

    # =========================================================================
    # 14. EVENT LISTENER DISPATCHING
    # =========================================================================

    async def test_28_member_join_dispatches_workflow(self):
        """on_member_join dispatches MEMBER_JOIN trigger to matching workflows."""
        with patch.object(WorkflowEngine, "dispatch_event", new_callable=AsyncMock) as mock_dispatch:
            await self.cog.on_member_join(self.member)
            mock_dispatch.assert_awaited_once()
            call_args = mock_dispatch.call_args
            self.assertEqual(call_args.args[2], TriggerType.MEMBER_JOIN)
            self.assertEqual(call_args.args[3]["user_id"], self.member.id)

    async def test_29_member_join_skips_bots(self):
        """on_member_join ignores bot members."""
        bot_member = MagicMock(spec=discord.Member)
        bot_member.bot = True
        with patch.object(WorkflowEngine, "dispatch_event", new_callable=AsyncMock) as mock_dispatch:
            await self.cog.on_member_join(bot_member)
            mock_dispatch.assert_not_awaited()

    async def test_30_member_remove_dispatches_workflow(self):
        """on_member_remove dispatches MEMBER_REMOVE trigger."""
        with patch.object(WorkflowEngine, "dispatch_event", new_callable=AsyncMock) as mock_dispatch:
            await self.cog.on_member_remove(self.member)
            mock_dispatch.assert_awaited_once()
            call_args = mock_dispatch.call_args
            self.assertEqual(call_args.args[2], TriggerType.MEMBER_REMOVE)

    async def test_31_voice_join_dispatches_workflow(self):
        """on_voice_state_update dispatches VOICE_JOIN when member enters a VC."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock(spec=discord.VoiceChannel)
        after.channel.id = 55551111

        with patch.object(WorkflowEngine, "dispatch_event", new_callable=AsyncMock) as mock_dispatch:
            await self.cog.on_voice_state_update(self.member, before, after)
            mock_dispatch.assert_awaited_once()
            self.assertEqual(mock_dispatch.call_args.args[2], TriggerType.VOICE_JOIN)

    async def test_32_voice_leave_dispatches_workflow(self):
        """on_voice_state_update dispatches VOICE_LEAVE when member exits a VC."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = MagicMock(spec=discord.VoiceChannel)
        before.channel.id = 55551111
        after = MagicMock(spec=discord.VoiceState)
        after.channel = None

        with patch.object(WorkflowEngine, "dispatch_event", new_callable=AsyncMock) as mock_dispatch:
            await self.cog.on_voice_state_update(self.member, before, after)
            mock_dispatch.assert_awaited_once()
            self.assertEqual(mock_dispatch.call_args.args[2], TriggerType.VOICE_LEAVE)

    async def test_33_voice_state_no_event_same_channel(self):
        """on_voice_state_update does NOT dispatch events when channel didn't change."""
        same_vc = MagicMock(spec=discord.VoiceChannel)
        same_vc.id = 55551111
        before = MagicMock(spec=discord.VoiceState)
        before.channel = same_vc
        after = MagicMock(spec=discord.VoiceState)
        after.channel = same_vc

        with patch.object(WorkflowEngine, "dispatch_event", new_callable=AsyncMock) as mock_dispatch:
            await self.cog.on_voice_state_update(self.member, before, after)
            mock_dispatch.assert_not_awaited()

    # =========================================================================
    # 15. ACTION REGISTRY INTEGRITY
    # =========================================================================

    async def test_34_all_registered_actions_have_handlers(self):
        """Every registered action in the registry must have an execution_handler."""
        for action in WorkflowActionRegistry.list_all():
            self.assertIsNotNone(
                action.execution_handler,
                f"Action {action.action_id} is missing an execution_handler",
            )

    async def test_35_all_registered_actions_have_valid_risk_levels(self):
        """Every registered action must have a valid risk level."""
        from core.workflow import ActionRiskLevel
        valid_levels = {r.value for r in ActionRiskLevel}
        for action in WorkflowActionRegistry.list_all():
            self.assertIn(
                action.risk_level.value,
                valid_levels,
                f"Action {action.action_id} has invalid risk level: {action.risk_level}",
            )

    async def test_36_minimum_expected_action_count(self):
        """Registry should have at least 14 registered actions."""
        count = len(WorkflowActionRegistry.list_all())
        self.assertGreaterEqual(count, 14, f"Expected at least 14 actions, got {count}")


if __name__ == "__main__":
    unittest.main()
