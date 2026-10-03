"""
RAI — SIMULATION LAB COG.
Provides:
- 100% safe dry-run simulations:
  /simulate raid
  /simulate lockdown
  /simulate recovery
  /simulate permission-rebuild
  /simulate room-cleanup
  /simulate incident
- SIMULATION MODE NEVER MODIFIES DISCORD PRODUCTION RESOURCES.
- Premium Feature Integration: Checked through PremiumFeatureGate.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from core.premium import EntitlementScope, PremiumFeature, PremiumFeatureGate, PremiumUpgradeView, create_premium_upgrade_embed
from core.simulation import SimulationLab, SimulationResult
from utils.embeds import create_embed, error_embed, info_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.SimulationCog")


class SimulationCog(commands.Cog, name="Simulation"):
    """Rai Simulation Lab — 100% Safe Dry-Run Simulations."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    sim_group = app_commands.Group(name="simulate", description="Safe dry-run operations and security simulations")

    async def _check_simulation_gate(self, interaction: discord.Interaction) -> bool:
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Unauthorized: Only server administrators can execute simulations.", ephemeral=True)
            return False

        gate = await PremiumFeatureGate.has_access(
            self.bot, PremiumFeature.SECURITY_SIMULATION, interaction.user.id, interaction.guild.id
        )
        if not gate.has_access:
            embed = create_premium_upgrade_embed("security_simulation", "Raid & Operations Simulation Lab", EntitlementScope.GUILD)
            view = PremiumUpgradeView(self.bot, interaction.user.id, "security_simulation", EntitlementScope.GUILD)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return False
        return True

    def _render_simulation_embed(self, sim: SimulationResult) -> discord.Embed:
        embed = create_embed(
            title=f"🧪 SIMULATION LAB — {sim.scenario.upper()}",
            description=(
                f"**Simulation ID:** `{sim.simulation_id}`\n"
                f"⚠️ **STATUS:** `100% SAFE DRY-RUN — ZERO REAL ACTIONS EXECUTED`\n\n"
                f"🔍 **Detected Signals:**\n" + "\n".join([f"• {d}" for d in sim.detected]) + "\n\n"
                f"⚡ **Would Execute:**\n" + "\n".join([f"• {w}" for w in sim.would_execute]) + "\n\n"
                f"🛡️ **Permissions Changed:**\n" + "\n".join([f"• {p}" for p in sim.permissions_changed]) + "\n\n"
                f"🎯 **Affected Targets:**\n" + "\n".join([f"• {t}" for t in sim.affected_targets[:6]])
            ),
            color=Colors.GOLD,
        )
        embed.set_footer(text="Verification complete. No live Discord permissions or channels were altered.")
        return embed

    @sim_group.command(name="raid", description="Simulate automated raid response and anti-nuke defense")
    async def simulate_raid_cmd(self, interaction: discord.Interaction):
        if not await self._check_simulation_gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        res = await SimulationLab.simulate_raid(self.bot, interaction.guild, interaction.user)  # type: ignore
        await interaction.followup.send(embed=self._render_simulation_embed(res), ephemeral=True)

    @sim_group.command(name="lockdown", description="Simulate full emergency server lockdown")
    async def simulate_lockdown_cmd(self, interaction: discord.Interaction):
        if not await self._check_simulation_gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        res = await SimulationLab.simulate_lockdown(self.bot, interaction.guild, interaction.user)  # type: ignore
        await interaction.followup.send(embed=self._render_simulation_embed(res), ephemeral=True)

    @sim_group.command(name="recovery", description="Simulate disaster recovery state scan and difference planning")
    async def simulate_recovery_cmd(self, interaction: discord.Interaction):
        if not await self._check_simulation_gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        res = await SimulationLab.simulate_recovery(self.bot, interaction.guild, interaction.user)  # type: ignore
        await interaction.followup.send(embed=self._render_simulation_embed(res), ephemeral=True)

    @sim_group.command(name="permission-rebuild", description="Simulate permission audit and role hierarchy scan")
    async def simulate_permission_cmd(self, interaction: discord.Interaction):
        if not await self._check_simulation_gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        res = await SimulationLab.simulate_permission_rebuild(self.bot, interaction.guild, interaction.user)  # type: ignore
        await interaction.followup.send(embed=self._render_simulation_embed(res), ephemeral=True)

    @sim_group.command(name="room-cleanup", description="Simulate dynamic room sweep identifying empty channels")
    async def simulate_cleanup_cmd(self, interaction: discord.Interaction):
        if not await self._check_simulation_gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        res = await SimulationLab.simulate_room_cleanup(self.bot, interaction.guild, interaction.user)  # type: ignore
        await interaction.followup.send(embed=self._render_simulation_embed(res), ephemeral=True)

    @sim_group.command(name="incident", description="Simulate incident ticket generation and owner alert dispatch")
    async def simulate_incident_cmd(self, interaction: discord.Interaction):
        if not await self._check_simulation_gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        res = await SimulationLab.simulate_incident(self.bot, interaction.guild, interaction.user)  # type: ignore
        await interaction.followup.send(embed=self._render_simulation_embed(res), ephemeral=True)

    @sim_group.command(name="dynamic-vc", description="Simulate dynamic temporary voice room creation and cleanup")
    async def simulate_dynamic_vc_cmd(self, interaction: discord.Interaction):
        if not await self._check_simulation_gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        res = await SimulationLab.simulate_dynamic_vc(self.bot, interaction.guild, interaction.user)  # type: ignore
        await interaction.followup.send(embed=self._render_simulation_embed(res), ephemeral=True)

    @sim_group.command(name="music-queue", description="Simulate bounded music queue insertion and source resolution")
    async def simulate_music_queue_cmd(self, interaction: discord.Interaction):
        if not await self._check_simulation_gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        res = await SimulationLab.simulate_music_queue(self.bot, interaction.guild, interaction.user)  # type: ignore
        await interaction.followup.send(embed=self._render_simulation_embed(res), ephemeral=True)

    @sim_group.command(name="soundboard-timeout", description="Simulate soundboard playback and strict auto-timeout ducking")
    async def simulate_soundboard_timeout_cmd(self, interaction: discord.Interaction):
        if not await self._check_simulation_gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        res = await SimulationLab.simulate_soundboard_timeout(self.bot, interaction.guild, interaction.user)  # type: ignore
        await interaction.followup.send(embed=self._render_simulation_embed(res), ephemeral=True)

    @sim_group.command(name="reports", description="Simulate deduplicated multi-destination report dispatch")
    async def simulate_reports_cmd(self, interaction: discord.Interaction):
        if not await self._check_simulation_gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        res = await SimulationLab.simulate_reports(self.bot, interaction.guild, interaction.user)  # type: ignore
        await interaction.followup.send(embed=self._render_simulation_embed(res), ephemeral=True)

    @sim_group.command(name="automation", description="Simulate scheduled maintenance and background workflow pipeline")
    async def simulate_automation_cmd(self, interaction: discord.Interaction):
        if not await self._check_simulation_gate(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        res = await SimulationLab.simulate_automation(self.bot, interaction.guild, interaction.user)  # type: ignore
        await interaction.followup.send(embed=self._render_simulation_embed(res), ephemeral=True)


async def setup(bot: SentinelBot):
    await bot.add_cog(SimulationCog(bot))
