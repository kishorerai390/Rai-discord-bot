"""
RAI — WORKFLOW ENGINE COG.
Exposes slash commands, Discord event dispatching, and background schedulers for automated workflows.

Commands:
- /workflow create           — Create a new workflow pipeline
- /workflow add-step         — Add an action step to an existing workflow
- /workflow instantiate      — Instantiate a pre-built template in this server
- /workflow list             — List all server workflows
- /workflow info             — View detailed workflow configuration
- /workflow actions          — List all available registered actions
- /workflow enable           — Activate an inactive workflow
- /workflow disable          — Disable a workflow
- /workflow pause            — Pause execution of an active workflow
- /workflow resume           — Resume a paused workflow
- /workflow run              — Manually trigger a workflow immediately
- /workflow simulate         — Dry-run simulation (zero Discord mutations)
- /workflow delete           — Permanently delete a workflow
- /workflow templates        — Browse built-in templates
- /workflow executions       — View recent execution history
- /workflow history          — View step-level details for a specific execution
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from config.permissions import PermissionLevel, get_member_permission_level, is_founder_or_owner
from core.premium import EntitlementScope, PremiumFeature, PremiumFeatureGate, PremiumUpgradeView, create_premium_upgrade_embed
from core.workflow import (
    CronParser,
    DEFAULT_WORKFLOW_TEMPLATES,
    MAX_ACTIVE_WORKFLOWS_FREE,
    MAX_ACTIVE_WORKFLOWS_PREMIUM,
    TriggerType,
    WorkflowActionRegistry,
    WorkflowEngine,
    WorkflowStatus,
)
from database.models import Workflow, WorkflowStep, WorkflowTemplate
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed


if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.WorkflowCog")


# =============================================================================
# STEP BUILDER MODAL — inline JSON config for step creation
# =============================================================================

class WorkflowStepModal(discord.ui.Modal, title="Add Workflow Step"):
    """Discord modal for guided step creation with action type and inline JSON config."""

    action_input = discord.ui.TextInput(
        label="Action ID (e.g. backup.create, health.check)",
        placeholder="backup.create",
        min_length=3,
        max_length=64,
        required=True,
    )
    config_input = discord.ui.TextInput(
        label="Action Config (JSON, or leave blank for {})",
        placeholder='{"seconds": 60}',
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1024,
    )
    condition_input = discord.ui.TextInput(
        label="Condition Config (JSON, or blank for always-run)",
        placeholder='{"type": "time_between", "start_hour": 0, "end_hour": 24}',
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=512,
    )
    failure_policy_input = discord.ui.TextInput(
        label="Failure Policy (STOP / CONTINUE / RETRY / FALLBACK)",
        placeholder="STOP",
        default="STOP",
        max_length=16,
        required=False,
    )
    timeout_input = discord.ui.TextInput(
        label="Timeout Seconds (default 60)",
        placeholder="60",
        default="60",
        max_length=6,
        required=False,
    )

    def __init__(self, bot: SentinelBot, workflow_id: str, next_step_order: int):
        super().__init__()
        self.bot = bot
        self.workflow_id = workflow_id
        self.next_step_order = next_step_order

    async def on_submit(self, interaction: discord.Interaction):
        action_id = self.action_input.value.strip().lower()

        # Validate action exists
        action_def = WorkflowActionRegistry.get(action_id)
        if not action_def:
            known = ", ".join(sorted(a.action_id for a in WorkflowActionRegistry.list_all()))
            await interaction.response.send_message(
                f"❌ Unknown action `{action_id}`.\n**Available actions:**\n`{known}`",
                ephemeral=True,
            )
            return

        # Parse JSON configs
        try:
            action_config = json.loads(self.config_input.value.strip() or "{}")
        except json.JSONDecodeError:
            await interaction.response.send_message("❌ Invalid JSON in Action Config field.", ephemeral=True)
            return

        try:
            condition_config = json.loads(self.condition_input.value.strip() or "{}") if self.condition_input.value.strip() else {}
        except json.JSONDecodeError:
            await interaction.response.send_message("❌ Invalid JSON in Condition Config field.", ephemeral=True)
            return

        failure_policy = (self.failure_policy_input.value.strip().upper() or "STOP")
        valid_policies = {"STOP", "CONTINUE", "RETRY", "FALLBACK"}
        if failure_policy not in valid_policies:
            failure_policy = "STOP"

        try:
            timeout_seconds = int(self.timeout_input.value.strip() or "60")
        except ValueError:
            timeout_seconds = 60

        step = WorkflowStep(
            id=f"stp_{uuid.uuid4().hex[:8]}",
            workflow_id=self.workflow_id,
            step_order=self.next_step_order,
            action_type=action_id,
            action_config=action_config,
            condition_config=condition_config,
            failure_policy=failure_policy,
            risk_level=action_def.risk_level.value,
            timeout_seconds=timeout_seconds,
            retry_policy={"max_retries": 2, "backoff": 2},
        )
        await self.bot.db.add_workflow_step(step)

        embed = success_embed(
            "Step Added",
            f"✅ Step **{self.next_step_order}** added to workflow `{self.workflow_id}`.\n"
            f"**Action:** `{action_id}` ({action_def.name})\n"
            f"**Risk:** `{action_def.risk_level.value}` | **On Fail:** `{failure_policy}` | **Timeout:** {timeout_seconds}s",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class WorkflowCog(commands.Cog, name="Workflow"):
    """Automated multi-step server workflows and scheduled pipelines."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._recovery_executed = False
        self.scheduler_loop.start()

    def cog_unload(self):
        self.scheduler_loop.cancel()

    @tasks.loop(seconds=15)
    async def scheduler_loop(self):
        """Sweeps scheduled workflows and waiting timers."""
        try:
            if not self.bot.is_ready():
                return

            if not self._recovery_executed:
                self._recovery_executed = True
                await WorkflowEngine.recover_after_restart(self.bot)

            # 1. Sweep waiting timers
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            due_timers = await self.bot.db.get_due_waiting_timers(max_resume_iso=now_iso)
            for timer in due_timers:
                guild = self.bot.get_guild(timer.guild_id)
                if not guild:
                    continue
                await self.bot.db.update_waiting_timer_status(timer.id, "COMPLETED")
                asyncio.create_task(
                    WorkflowEngine.execute_workflow(
                        self.bot,
                        guild,
                        timer.workflow_id,
                        trigger_event="timer_resumed",
                        start_step_order=timer.next_step_order,
                        existing_execution_id=timer.execution_id,
                    )
                )

            # 2. Check scheduled time-based workflows
            await WorkflowEngine.check_scheduled_workflows(self.bot)

        except Exception as e:
            logger.error(f"Error in workflow scheduler loop: {e}", exc_info=True)

    @scheduler_loop.before_loop
    async def before_scheduler(self):
        await self.bot.wait_until_ready()

    workflow_group = app_commands.Group(name="workflow", description="Rai Automated Workflow Orchestration Engine")

    # =========================================================================
    # SLASH COMMANDS
    # =========================================================================

    @workflow_group.command(name="list", description="List all workflows configured for this server")
    async def cmd_list(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
            return

        wfs = await self.bot.db.list_workflows(interaction.guild.id)
        if not wfs:
            embed = info_embed(
                "Rai Workflows",
                "No workflows found for this server.\nUse `/workflow create` or `/workflow templates` to get started.",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = create_embed(
            title="⚙️ RAI SERVER WORKFLOWS",
            description=f"Showing **{len(wfs)}** configured automated pipelines for **{interaction.guild.name}**.",
            color=Colors.PRIMARY,
        )
        for wf in wfs[:20]:
            status_emoji = "🟢" if wf.status == "ACTIVE" else ("🟡" if wf.status == "PAUSED" else "⚪")
            embed.add_field(
                name=f"{status_emoji} {wf.name} (`{wf.id}`)",
                value=(
                    f"**Trigger:** `{wf.trigger_type}` | **Status:** `{wf.status}` | **v{wf.version}**\n"
                    f"*{wf.description or 'No description'}*"
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @workflow_group.command(name="info", description="View detailed configuration for a workflow")
    @app_commands.describe(workflow_id="Unique ID of the workflow")
    async def cmd_info(self, interaction: discord.Interaction, workflow_id: str):
        if not interaction.guild:
            return

        wf = await self.bot.db.get_workflow(workflow_id)
        if not wf or wf.guild_id != interaction.guild.id:
            await interaction.response.send_message("❌ Workflow not found in this server.", ephemeral=True)
            return

        steps = await self.bot.db.get_workflow_steps(wf.id)
        embed = create_embed(
            title=f"📋 Workflow: {wf.name}",
            description=wf.description or "No description provided.",
            color=Colors.INFO,
        )
        embed.add_field(name="ID", value=f"`{wf.id}`", inline=True)
        embed.add_field(name="Status", value=f"`{wf.status}`", inline=True)
        embed.add_field(name="Trigger", value=f"`{wf.trigger_type}`", inline=True)
        embed.add_field(name="Version", value=f"v{wf.version}", inline=True)
        embed.add_field(name="Missed Policy", value=f"`{wf.missed_schedule_policy}`", inline=True)
        embed.add_field(name="Last Run", value=wf.last_run_at or "Never", inline=True)

        if steps:
            steps_desc = "\n".join(
                [f"**{s.step_order}.** `{s.action_type}` (Risk: `{s.risk_level}`, Fail: `{s.failure_policy}`)" for s in steps]
            )
        else:
            steps_desc = "*No steps defined yet.*"

        embed.add_field(name=f"Steps ({len(steps)})", value=steps_desc, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @workflow_group.command(name="create", description="Create a new workflow")
    @app_commands.describe(
        name="Name of the workflow",
        trigger_type="Event or schedule trigger",
        description="Optional description",
    )
    @app_commands.choices(
        trigger_type=[
            app_commands.Choice(name="Daily Schedule (02:00 UTC)", value="daily"),
            app_commands.Choice(name="Weekly Schedule (Sunday 02:00 UTC)", value="weekly"),
            app_commands.Choice(name="New Member Joined", value="member_join"),
            app_commands.Choice(name="Member Left", value="member_remove"),
            app_commands.Choice(name="Voice Leave (e.g. empty room)", value="voice_leave"),
            app_commands.Choice(name="Security Incident", value="security_incident"),
            app_commands.Choice(name="Backup Failed", value="backup_failed"),
        ]
    )
    async def cmd_create(
        self, interaction: discord.Interaction, name: str, trigger_type: app_commands.Choice[str], description: Optional[str] = None
    ):
        if not interaction.guild:
            return
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Admin permissions required to create workflows.", ephemeral=True)
            return

        # Check free tier limits
        wfs = await self.bot.db.list_workflows(interaction.guild.id, status="ACTIVE")
        if len(wfs) >= MAX_ACTIVE_WORKFLOWS_FREE:
            gate = await PremiumFeatureGate.has_access(
                self.bot, PremiumFeature.ADVANCED_AUTOMATION, interaction.user.id, interaction.guild.id
            )
            if not gate.has_access:
                embed = create_premium_upgrade_embed(
                    "automation_advanced",
                    f"Free limit reached ({MAX_ACTIVE_WORKFLOWS_FREE} active workflows). Upgrade to Premium for up to {MAX_ACTIVE_WORKFLOWS_PREMIUM} active workflows!",
                    EntitlementScope.GUILD,
                )
                view = PremiumUpgradeView(self.bot, interaction.user.id, "automation_advanced", EntitlementScope.GUILD)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return

        wf_id = f"wf_{uuid.uuid4().hex[:6]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        wf = Workflow(
            id=wf_id,
            guild_id=interaction.guild.id,
            creator_id=interaction.user.id,
            name=name,
            description=description,
            status=WorkflowStatus.ACTIVE.value,
            trigger_type=trigger_type.value,
            created_at=now,
            updated_at=now,
        )
        await self.bot.db.create_workflow(wf)
        embed = success_embed(
            "Workflow Created",
            f"Successfully created workflow **{name}** (`{wf_id}`).\nTrigger: `{trigger_type.value}`\nUse `/workflow edit` or `/workflow info` to inspect.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @workflow_group.command(name="enable", description="Enable an inactive workflow")
    @app_commands.describe(workflow_id="ID of workflow to enable")
    async def cmd_enable(self, interaction: discord.Interaction, workflow_id: str):
        if not interaction.guild or not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
            return
        res = await self.bot.db.update_workflow_status(workflow_id, "ACTIVE")
        if res:
            await interaction.response.send_message(f"✅ Workflow `{workflow_id}` is now **ACTIVE**.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Workflow not found.", ephemeral=True)

    @workflow_group.command(name="disable", description="Disable a workflow")
    @app_commands.describe(workflow_id="ID of workflow to disable")
    async def cmd_disable(self, interaction: discord.Interaction, workflow_id: str):
        if not interaction.guild or not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
            return
        await self.bot.db.cancel_waiting_timers_for_workflow(workflow_id)
        res = await self.bot.db.update_workflow_status(workflow_id, "DISABLED")
        if res:
            await interaction.response.send_message(f"⚪ Workflow `{workflow_id}` has been **DISABLED**.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Workflow not found.", ephemeral=True)

    @workflow_group.command(name="pause", description="Pause an active workflow")
    @app_commands.describe(workflow_id="ID of workflow to pause")
    async def cmd_pause(self, interaction: discord.Interaction, workflow_id: str):
        if not interaction.guild or not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
            return
        res = await self.bot.db.update_workflow_status(workflow_id, "PAUSED")
        if res:
            await interaction.response.send_message(f"🟡 Workflow `{workflow_id}` has been **PAUSED**.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Workflow not found.", ephemeral=True)

    @workflow_group.command(name="resume", description="Resume a paused workflow")
    @app_commands.describe(workflow_id="ID of workflow to resume")
    async def cmd_resume(self, interaction: discord.Interaction, workflow_id: str):
        if not interaction.guild or not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
            return
        res = await self.bot.db.update_workflow_status(workflow_id, "ACTIVE")
        if res:
            await interaction.response.send_message(f"🟢 Workflow `{workflow_id}` has been **RESUMED**.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Workflow not found.", ephemeral=True)

    @workflow_group.command(name="run", description="Manually run a workflow immediately")
    @app_commands.describe(workflow_id="ID of workflow to run")
    async def cmd_run(self, interaction: discord.Interaction, workflow_id: str):
        if not interaction.guild:
            return
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Admin permissions required.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        res = await WorkflowEngine.execute_workflow(
            self.bot, interaction.guild, workflow_id, trigger_event=f"manual_by_{interaction.user.id}"
        )
        if res.get("status") == "SUCCESS":
            embed = success_embed(
                "Workflow Completed",
                f"Workflow `{workflow_id}` ran successfully.\nExecution ID: `{res.get('execution_id')}`\nSteps executed: {len(res.get('step_results', []))}",
            )
        elif res.get("status") == "WAITING":
            embed = info_embed(
                "Workflow Waiting",
                f"Workflow `{workflow_id}` is now waiting for a delay.\nExecution ID: `{res.get('execution_id')}`\nResumes at: `{res.get('resume_at')}`",
            )
        else:
            embed = error_embed(
                "Workflow Failed",
                f"Execution failed: {res.get('error', 'Unknown error')}\nExecution ID: `{res.get('execution_id')}`",
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @workflow_group.command(name="simulate", description="Safely simulate a workflow dry-run with ZERO Discord mutations")
    @app_commands.describe(workflow_id="ID of workflow to simulate")
    async def cmd_simulate(self, interaction: discord.Interaction, workflow_id: str):
        if not interaction.guild:
            return
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        res = await WorkflowEngine.execute_workflow(
            self.bot, interaction.guild, workflow_id, trigger_event="simulation", is_simulation=True
        )
        embed = create_embed(
            title="🔬 WORKFLOW SIMULATION LAB",
            description=f"**100% DRY-RUN SIMULATION** for `{workflow_id}`.\n*Zero Discord resources were modified.*",
            color=Colors.INFO,
        )
        embed.add_field(name="Simulation Result", value=f"`{res.get('status')}`", inline=True)
        steps = res.get("step_results", [])
        if steps:
            lines = [f"✓ Step {s['step_order']}: `{s['action']}` ({s['status']})" for s in steps]
            embed.add_field(name="Executed Actions", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Executed Actions", value="*No steps defined or executed.*", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @workflow_group.command(name="delete", description="Permanently delete a workflow")
    @app_commands.describe(workflow_id="ID of workflow to delete")
    async def cmd_delete(self, interaction: discord.Interaction, workflow_id: str):
        if not interaction.guild or not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
            return

        await self.bot.db.cancel_waiting_timers_for_workflow(workflow_id)
        await self.bot.db.delete_workflow_steps(workflow_id)
        res = await self.bot.db.delete_workflow(workflow_id)
        if res:
            await interaction.response.send_message(f"🗑️ Workflow `{workflow_id}` and its steps deleted.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Workflow not found.", ephemeral=True)

    @workflow_group.command(name="templates", description="View and instantiate pre-built workflow templates")
    async def cmd_templates(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        embed = create_embed(
            title="📦 RAI WORKFLOW TEMPLATES",
            description="Select a template below to view or instantiate it in your server.",
            color=Colors.SECONDARY,
        )
        for tmpl in DEFAULT_WORKFLOW_TEMPLATES:
            embed.add_field(
                name=f"🛠️ {tmpl['name']} (`{tmpl['id']}`)",
                value=f"{tmpl['description']}\nTrigger: `{tmpl['config']['trigger_type']}` | Steps: `{len(tmpl['config']['steps'])}`",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @workflow_group.command(name="executions", description="List recent workflow executions in this server")
    async def cmd_executions(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        execs = await self.bot.db.list_workflow_executions(interaction.guild.id, limit=10)
        if not execs:
            await interaction.response.send_message("ℹ️ No executions recorded yet.", ephemeral=True)
            return

        embed = create_embed(
            title="📊 Recent Workflow Executions",
            description=f"Showing the last {len(execs)} executions in **{interaction.guild.name}**.",
            color=Colors.PRIMARY,
        )
        for ex in execs:
            status_emoji = "✅" if ex.status == "COMPLETED" else ("⏳" if ex.status == "WAITING" else "❌")
            embed.add_field(
                name=f"{status_emoji} {ex.id} (Workflow: `{ex.workflow_id}`)",
                value=f"**Status:** `{ex.status}` | **Trigger:** `{ex.trigger_event}`\nStarted: `{ex.started_at[:19]}`",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @workflow_group.command(name="add-step", description="Add an action step to an existing workflow")
    @app_commands.describe(workflow_id="ID of the workflow to add a step to")
    async def cmd_add_step(self, interaction: discord.Interaction, workflow_id: str):
        if not interaction.guild or not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Admin permissions required.", ephemeral=True)
            return

        wf = await self.bot.db.get_workflow(workflow_id)
        if not wf or wf.guild_id != interaction.guild.id:
            await interaction.response.send_message("❌ Workflow not found in this server.", ephemeral=True)
            return

        existing_steps = await self.bot.db.get_workflow_steps(workflow_id)
        next_order = (max(s.step_order for s in existing_steps) + 1) if existing_steps else 1

        modal = WorkflowStepModal(self.bot, workflow_id, next_order)
        await interaction.response.send_modal(modal)

    @workflow_group.command(name="instantiate", description="Create a live workflow from a built-in template")
    @app_commands.describe(template_id="The ID of the template (e.g. tmpl-weekly-maintenance)")
    async def cmd_instantiate(self, interaction: discord.Interaction, template_id: str):
        if not interaction.guild:
            return
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Admin permissions required.", ephemeral=True)
            return

        tmpl = next((t for t in DEFAULT_WORKFLOW_TEMPLATES if t["id"] == template_id), None)
        if not tmpl:
            known = ", ".join(f"`{t['id']}`" for t in DEFAULT_WORKFLOW_TEMPLATES)
            await interaction.response.send_message(
                f"❌ Template `{template_id}` not found.\n**Available templates:** {known}",
                ephemeral=True,
            )
            return

        # Check free tier limits
        wfs = await self.bot.db.list_workflows(interaction.guild.id, status="ACTIVE")
        if len(wfs) >= MAX_ACTIVE_WORKFLOWS_FREE:
            gate = await PremiumFeatureGate.has_access(
                self.bot, PremiumFeature.ADVANCED_AUTOMATION, interaction.user.id, interaction.guild.id
            )
            if not gate.has_access:
                embed = create_premium_upgrade_embed(
                    "automation_advanced",
                    f"Free limit reached ({MAX_ACTIVE_WORKFLOWS_FREE} active workflows). Upgrade to Premium!",
                    EntitlementScope.GUILD,
                )
                view = PremiumUpgradeView(self.bot, interaction.user.id, "automation_advanced", EntitlementScope.GUILD)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return

        cfg = tmpl["config"]
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        wf_id = f"wf_{uuid.uuid4().hex[:6]}"

        wf = Workflow(
            id=wf_id,
            guild_id=interaction.guild.id,
            creator_id=interaction.user.id,
            name=tmpl["name"],
            description=tmpl["description"],
            status=WorkflowStatus.ACTIVE.value,
            trigger_type=cfg["trigger_type"],
            trigger_config=cfg.get("trigger_config", {}),
            created_at=now,
            updated_at=now,
        )
        await self.bot.db.create_workflow(wf)

        for i, step_cfg in enumerate(cfg.get("steps", []), start=1):
            step = WorkflowStep(
                id=f"stp_{uuid.uuid4().hex[:8]}",
                workflow_id=wf_id,
                step_order=i,
                action_type=step_cfg["action_type"],
                action_config=step_cfg.get("action_config", {}),
                condition_config=step_cfg.get("condition_config", {}),
                risk_level=step_cfg.get("risk_level", "LOW"),
                failure_policy="STOP",
                timeout_seconds=60,
                retry_policy={"max_retries": 2, "backoff": 2},
            )
            await self.bot.db.add_workflow_step(step)

        embed = success_embed(
            "Template Instantiated",
            f"✅ Template **{tmpl['name']}** has been activated!\n"
            f"**Workflow ID:** `{wf_id}`\n"
            f"**Trigger:** `{cfg['trigger_type']}` | **Steps:** {len(cfg.get('steps', []))}\n"
            f"Use `/workflow info {wf_id}` to view or `/workflow simulate {wf_id}` to dry-run.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @workflow_group.command(name="history", description="View step-level execution history for a specific execution")
    @app_commands.describe(execution_id="Execution ID (e.g. RAI-WF-ABCD1234)")
    async def cmd_history(self, interaction: discord.Interaction, execution_id: str):
        if not interaction.guild:
            return

        step_execs = await self.bot.db.list_step_executions(execution_id)
        if not step_execs:
            await interaction.response.send_message(
                f"ℹ️ No step-level history found for execution `{execution_id}`.", ephemeral=True
            )
            return

        embed = create_embed(
            title=f"📋 Execution History: `{execution_id}`",
            description=f"Showing **{len(step_execs)}** step execution records.",
            color=Colors.INFO,
        )
        for sx in step_execs[:15]:
            status_emoji = "✅" if sx.status == "COMPLETED" else "❌"
            result_preview = str(sx.result_json or {})[:80]
            embed.add_field(
                name=f"{status_emoji} Step `{sx.step_id}` — Attempt #{sx.attempt}",
                value=(
                    f"**Status:** `{sx.status}`\n"
                    f"**Result:** `{result_preview}`\n"
                    f"**Started:** `{sx.started_at[:19] if sx.started_at else 'N/A'}`"
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @workflow_group.command(name="actions", description="List all available workflow action types")
    async def cmd_actions(self, interaction: discord.Interaction):
        actions = WorkflowActionRegistry.list_all()
        embed = create_embed(
            title="⚡ Workflow Action Registry",
            description=f"**{len(actions)}** registered actions available for workflow steps.",
            color=Colors.SECONDARY,
        )

        # Group by prefix (backup, health, security, etc.)
        grouped: Dict[str, List] = {}
        for act in sorted(actions, key=lambda a: a.action_id):
            prefix = act.action_id.split(".")[0]
            grouped.setdefault(prefix, []).append(act)

        for prefix, acts in grouped.items():
            lines = []
            for a in acts:
                risk_emoji = "🔴" if a.risk_level.value == "HIGH" else ("🟡" if a.risk_level.value == "MEDIUM" else "🟢")
                lines.append(f"{risk_emoji} `{a.action_id}` — {a.description[:60]}")
            embed.add_field(
                name=f"**{prefix.upper()} Actions**",
                value="\n".join(lines),
                inline=False,
            )

        embed.set_footer(text="🔴 HIGH risk  |  🟡 MEDIUM risk  |  🟢 LOW risk")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =========================================================================
    # DISCORD EVENT LISTENERS
    # =========================================================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        await WorkflowEngine.dispatch_event(
            self.bot, member.guild, TriggerType.MEMBER_JOIN, {"user_id": member.id, "user_name": str(member)}
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        await WorkflowEngine.dispatch_event(
            self.bot, member.guild, TriggerType.MEMBER_REMOVE, {"user_id": member.id, "user_name": str(member)}
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        guild = member.guild
        if before.channel is None and after.channel is not None:
            await WorkflowEngine.dispatch_event(
                self.bot, guild, TriggerType.VOICE_JOIN, {"user_id": member.id, "channel_id": after.channel.id}
            )
        elif before.channel is not None and after.channel is None:
            await WorkflowEngine.dispatch_event(
                self.bot, guild, TriggerType.VOICE_LEAVE, {"user_id": member.id, "channel_id": before.channel.id}
            )


async def setup(bot: SentinelBot):
    await bot.add_cog(WorkflowCog(bot))
