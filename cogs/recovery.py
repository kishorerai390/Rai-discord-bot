"""
RAI — DISASTER RECOVERY & AUDIT COG.
Provides:
- Comprehensive state diff scanner comparing Discord Live state with Database Desired state.
- Interactive recovery planning with preview and mandatory owner confirmation.
- Commands:
  /recovery audit
  /recovery preview <scan_id>
  /recovery execute <plan_id>
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from config import Colors
from core.recovery import DisasterRecoveryEngine, RecoveryPlan, StateDifference
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.RecoveryCog")


class RecoveryConfirmationView(ui.View):
    """Requires explicit confirmation before executing disaster recovery repairs."""

    def __init__(self, bot: SentinelBot, plan_id: str, actor_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.plan_id = plan_id
        self.actor_id = actor_id

    @ui.button(label="Execute Repair", emoji="🛠️", style=discord.ButtonStyle.danger)
    async def confirm_repair(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.actor_id and not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Unauthorized: Only the initiating administrator can confirm repair.", ephemeral=True)
            return

        await interaction.response.defer()
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)

        res = await DisasterRecoveryEngine.execute_recovery_plan(self.bot, interaction.guild, self.plan_id)  # type: ignore

        embed = success_embed(
            title="🛠️ Disaster Recovery Execution Complete",
            description=(
                f"**Plan ID:** `{self.plan_id}`\n"
                f"**Actions Executed:** `{res.get('executed', 0)} / {res.get('total_actions', 0)}`\n"
                f"**Verification:** State repaired and verified against database baseline."
            ),
        )
        await interaction.followup.send(embed=embed)

    @ui.button(label="Cancel", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def cancel_repair(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.actor_id and not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Unauthorized.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Recovery repair cancelled.", view=self)


class RecoveryCog(commands.Cog, name="Recovery"):
    """Disaster Recovery and State Difference Engine."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    rec_group = app_commands.Group(name="recovery", description="Disaster recovery state scanner and repair engine")
    restore_group = app_commands.Group(name="restore", description="Disaster recovery restoration and state repair")

    @rec_group.command(name="audit", description="Audit live Discord state against database desired configuration")
    async def audit_cmd(self, interaction: discord.Interaction):
        await self._do_audit(interaction)

    @restore_group.command(name="audit", description="Audit live Discord state against database desired configuration")
    async def restore_audit_cmd(self, interaction: discord.Interaction):
        await self._do_audit(interaction)

    async def _do_audit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Unauthorized: Administrator permissions required.", ephemeral=True)
            return

        scan_id, diffs = await DisasterRecoveryEngine.scan_guild_state(self.bot, interaction.guild)  # type: ignore

        embed = create_embed(
            title=f"🔍 DISASTER RECOVERY AUDIT — {interaction.guild.name}",
            description=(
                f"**Scan ID:** `{scan_id}`\n"
                f"**Total Discrepancies:** `{len(diffs)}`\n\n"
                + (
                    "\n".join([f"• `[{d.diff_type}]` **{d.resource_name}**" for d in diffs[:8]])
                    if diffs
                    else "✅ All live Discord resources and database records match expected desired state!"
                )
            ),
            color=Colors.PRIMARY if not diffs else Colors.WARNING,
        )

        if diffs:
            embed.set_footer(text=f"Generate a repair plan with: /restore preview {scan_id}")
        await interaction.followup.send(embed=embed)

    @rec_group.command(name="preview", description="Preview a recovery plan before executing repairs")
    @app_commands.describe(scan_id="The scan ID from /recovery audit or /restore audit")
    async def preview_cmd(self, interaction: discord.Interaction, scan_id: str):
        await self._do_preview(interaction, scan_id)

    @restore_group.command(name="preview", description="Preview a recovery plan before executing repairs")
    @app_commands.describe(scan_id="The scan ID from /restore audit")
    async def restore_preview_cmd(self, interaction: discord.Interaction, scan_id: str):
        await self._do_preview(interaction, scan_id)

    async def _do_preview(self, interaction: discord.Interaction, scan_id: str):
        await interaction.response.defer()
        if not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Unauthorized: Administrator permissions required.", ephemeral=True)
            return

        try:
            plan = await DisasterRecoveryEngine.create_recovery_plan(self.bot, interaction.guild, scan_id)  # type: ignore
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create plan: {e}", ephemeral=True)
            return

        actions_str = "\n".join([f"• `{a['action_type']}` on `{a['target_name']}`" for a in plan.planned_actions]) or "No repairs necessary."
        embed = create_embed(
            title=f"📋 RECOVERY PLAN PREVIEW — {plan.plan_id}",
            description=(
                f"**Scan ID:** `{plan.scan_id}`\n"
                f"**Status:** `PENDING CONFIRMATION 🟡`\n\n"
                f"**Planned Repair Actions ({len(plan.planned_actions)}):**\n"
                f"{actions_str}\n\n"
                f"⚠️ *No changes have been made yet. Click 'Execute Repair' below to apply.*"
            ),
            color=Colors.GOLD,
        )

        view = RecoveryConfirmationView(self.bot, plan.plan_id, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

    @rec_group.command(name="execute", description="Execute a pre-generated recovery plan")
    @app_commands.describe(plan_id="The recovery plan ID")
    async def execute_cmd(self, interaction: discord.Interaction, plan_id: str):
        await self._do_execute(interaction, plan_id)

    @restore_group.command(name="execute", description="Execute a pre-generated recovery plan")
    @app_commands.describe(plan_id="The recovery plan ID")
    async def restore_execute_cmd(self, interaction: discord.Interaction, plan_id: str):
        await self._do_execute(interaction, plan_id)

    async def _do_execute(self, interaction: discord.Interaction, plan_id: str):
        await interaction.response.defer()
        if not is_admin_or_owner(interaction.user):
            await interaction.followup.send("❌ Unauthorized: Administrator permissions required.", ephemeral=True)
            return

        view = RecoveryConfirmationView(self.bot, plan_id, interaction.user.id)
        embed = create_embed(
            title="⚠️ Confirm Recovery Plan Execution",
            description=f"Are you sure you want to execute recovery plan **`{plan_id}`**? This will restore and repair missing resources.",
            color=Colors.WARNING,
        )
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: SentinelBot):
    await bot.add_cog(RecoveryCog(bot))
