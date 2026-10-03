"""
RAI — Premium Monetization Cog.

Integrates Discord's official Premium Apps monetization system:
- Listens to Discord entitlement lifecycle events:
  * on_entitlement_create
  * on_entitlement_update
  * on_entitlement_delete
- Periodically checks for expired entitlements.
- Exposes user-friendly slash commands:
  * /premium store
  * /premium server
  * /premium status
  * /premium compare
  * /premium features
  * /premium dashboard
  * /premium test-entitlement (Test Mode Only)
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import TYPE_CHECKING, List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from core.premium import (
    DEFAULT_FEATURE_RULES,
    EntitlementScope,
    EntitlementService,
    EntitlementStatus,
    PremiumFeature,
    PremiumFeatureGate,
    PremiumNotificationService,
    PremiumService,
    PremiumStoreView,
    SKUService,
    create_plans_comparison_embed,
)
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger(__name__)


class PremiumCog(commands.Cog, name="Premium"):
    """Official Discord Premium Apps Monetization & Entitlements Engine."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.expiration_check_task.start()

    def cog_unload(self):
        self.expiration_check_task.cancel()

    # =========================================================================
    # DISCORD ENTITLEMENT EVENT LISTENERS
    # =========================================================================

    @commands.Cog.listener()
    async def on_entitlement_create(self, entitlement: discord.Entitlement) -> None:
        """Fired automatically by Discord when a user or server purchases a SKU."""
        logger.info(
            f"Discord Entitlement Created: ID={entitlement.id} SKU={entitlement.sku_id} "
            f"User={entitlement.user_id} Guild={entitlement.guild_id}"
        )
        try:
            await EntitlementService.ingest_discord_entitlement(self.bot, entitlement)
        except Exception as e:
            logger.error(f"Error handling on_entitlement_create {entitlement.id}: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_entitlement_update(self, entitlement: discord.Entitlement) -> None:
        """Fired when an entitlement is renewed or altered by Discord."""
        logger.info(
            f"Discord Entitlement Updated: ID={entitlement.id} SKU={entitlement.sku_id} "
            f"EndsAt={entitlement.ends_at}"
        )
        try:
            await EntitlementService.ingest_discord_entitlement(self.bot, entitlement)
        except Exception as e:
            logger.error(f"Error handling on_entitlement_update {entitlement.id}: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_entitlement_delete(self, entitlement: discord.Entitlement) -> None:
        """Fired when an entitlement is deleted/revoked or refunded."""
        logger.info(
            f"Discord Entitlement Deleted/Revoked: ID={entitlement.id} SKU={entitlement.sku_id}"
        )
        try:
            await EntitlementService.ingest_discord_entitlement(self.bot, entitlement)
        except Exception as e:
            logger.error(f"Error handling on_entitlement_delete {entitlement.id}: {e}", exc_info=True)

    # =========================================================================
    # BACKGROUND EXPIRATION WORKER
    # =========================================================================

    @tasks.loop(minutes=30)
    async def expiration_check_task(self) -> None:
        """Periodically sweeps local database for subscriptions whose period elapsed."""
        try:
            expired_count = await EntitlementService.expire_stale_entitlements(self.bot)
            if expired_count > 0:
                logger.info(f"Premium Sweeper: Expired {expired_count} subscription entitlements.")
        except Exception as e:
            logger.error(f"Error running premium expiration sweep: {e}", exc_info=True)

    @expiration_check_task.before_loop
    async def before_expiration_check(self) -> None:
        await self.bot.wait_until_ready()

    # =========================================================================
    # SLASH COMMANDS (/premium)
    # =========================================================================

    premium_group = app_commands.Group(
        name="premium",
        description="Official Discord Premium Apps store, entitlements, and features",
    )

    @premium_group.command(name="store", description="Open the Rai Premium In-App Store")
    async def premium_store(self, interaction: discord.Interaction):
        """Displays the official Rai Premium Store with Discord checkout integration."""
        desc = (
            "**Elevate your server operations with Rai Premium.**\n\n"
            "🧠 **Advanced Operations Assistant**\n"
            "• Natural language multi-step command chains and automated operations\n\n"
            "🎙️ **Advanced Dynamic Voice Rooms**\n"
            "• Custom templates, high-bitrate streaming, and automated delegation\n\n"
            "🎵 **Advanced Music Engine**\n"
            "• Unlimited queue depth, lossless audio DSP, and continuous autoplay\n\n"
            "🛡️ **Advanced Security & Anti-Raid**\n"
            "• Deep threat timeline auditing and safe raid simulation sandbox\n\n"
            "💾 **Automated Backups & Rollback**\n"
            "• High-frequency hourly backups and configuration version snapshots\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "*All purchases are processed securely and directly through Discord.*"
        )
        embed = create_embed(title="⭐ RAI PREMIUM — OFFICIAL DISCORD STORE", description=desc, color=Colors.GOLD)
        embed.set_footer(text="Discord Verified Premium Application • Free Core Security Included")

        view = PremiumStoreView(self.bot, interaction.user.id, interaction.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @premium_group.command(name="server", description="View and manage Server Premium for this guild")
    async def premium_server(self, interaction: discord.Interaction):
        """Details Server Premium perks applying to all members in the guild."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Guild context required.", ephemeral=True)
            return

        status = await PremiumService.get_status_overview(self.bot, interaction.user.id, interaction.guild.id)
        guild_active = status["has_guild_premium"]

        state_str = "🟢 **ACTIVE (SERVER UNLOCKED)**" if guild_active else "⚪ **FREE TIER**"

        desc = (
            f"**Server Status:** {state_str}\n\n"
            "**Server Premium Benefits:**\n"
            "• Unlocks advanced voice rooms for **all server members**\n"
            "• Enables automated hourly backups with 30-day retention\n"
            "• Safe raid attack simulations to test server defense\n"
            "• Configuration snapshot versioning and instant rollback\n"
            "• 30-day extended server activity analytics\n\n"
            f"*Server Premium applies to `{interaction.guild.name}` regardless of member personal plans.*"
        )

        embed = create_embed(
            title=f"🏰 RAI SERVER PREMIUM — {interaction.guild.name}",
            description=desc,
            color=Colors.GOLD if guild_active else Colors.PRIMARY,
        )

        view = PremiumStoreView(self.bot, interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @premium_group.command(name="status", description="Check active personal and server premium entitlements")
    async def premium_status(self, interaction: discord.Interaction):
        """Displays verified active entitlement status from the persistent database."""
        await interaction.response.defer(ephemeral=True)
        status = await PremiumService.get_status_overview(self.bot, interaction.user.id, interaction.guild_id)

        user_ents = status["user_entitlements"]
        guild_ents = status["guild_entitlements"]

        lines = ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]

        lines.append("👤 **PERSONAL PREMIUM:**")
        if user_ents:
            for ent in user_ents:
                exp_str = f"Renews/Ends: `{ent.get('ends_at', 'Continuous')[:10]}`"
                lines.append(f"• Active Subscription (ID: `{ent['entitlement_id']}`, SKU: `{ent['sku_id']}`) | {exp_str}")
        else:
            lines.append("• *No active Personal Premium subscription.*")

        lines.append("\n🏰 **SERVER PREMIUM:**")
        if guild_ents:
            for ent in guild_ents:
                exp_str = f"Renews/Ends: `{ent.get('ends_at', 'Continuous')[:10]}`"
                lines.append(f"• Active Server Plan (ID: `{ent['entitlement_id']}`, SKU: `{ent['sku_id']}`) | {exp_str}")
        else:
            lines.append("• *No active Server Premium subscription on this server.*")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        embed = create_embed(
            title="⭐ RAI ENTITLEMENT STATUS",
            description="\n".join(lines),
            color=Colors.GOLD if (user_ents or guild_ents) else Colors.PRIMARY,
        )
        embed.set_footer(text="Official Discord Entitlement Verification")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @premium_group.command(name="compare", description="Compare Free Tier vs Personal vs Server Premium")
    async def premium_compare(self, interaction: discord.Interaction):
        """Displays full comparison matrix across all feature tiers."""
        embed = create_plans_comparison_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @premium_group.command(name="features", description="Inspect all premium feature gates and access status")
    async def premium_features(self, interaction: discord.Interaction):
        """Shows which premium features are active or available on this server."""
        await interaction.response.defer(ephemeral=True)

        lines = []
        for feat_key, (name, desc, req_scope) in DEFAULT_FEATURE_RULES.items():
            res = await PremiumFeatureGate.has_access(
                bot=self.bot,
                feature=feat_key,
                user_id=interaction.user.id,
                guild_id=interaction.guild_id,
            )
            status_emoji = "🟢 Unlocked" if res.has_access else "🔒 Gated"
            scope_tag = f"`{req_scope.value.upper()}`"
            lines.append(f"• **{name}** ({scope_tag}) — {status_emoji}\n  *{desc}*")

        embed = create_embed(
            title="⚙️ Premium Feature Gates Overview",
            description="\n".join(lines),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @premium_group.command(name="dashboard", description="View owner monetization telemetry and subscription counts")
    @app_commands.default_permissions(administrator=True)
    async def premium_dashboard(self, interaction: discord.Interaction):
        """Displays aggregated monetization telemetry for administrators and bot owners."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Guild context required.", ephemeral=True)
            return

        is_owner = (interaction.user.id == interaction.guild.owner_id) or (interaction.user.id == OWNER_ID)
        if not is_owner and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Restricted to administrators.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        analytics = await self.bot.db.get_premium_analytics_summary()
        recent_events = await self.bot.db.get_recent_premium_events(limit=5)

        desc = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⭐ **MONETIZATION OVERVIEW**\n\n"
            f"• **Active Premium Users:** `{analytics['active_users']}`\n"
            f"• **Active Premium Servers:** `{analytics['active_guilds']}`\n"
            f"• **Total Active Entitlements:** `{analytics['active_entitlements']}`\n"
            f"• **Expired Subscriptions:** `{analytics['expired_entitlements']}`\n"
            f"• **Monetization Engine:** {'🟢 Connected' if SKUService.is_monetization_configured() else '⚪ Free Tier Default'}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        event_lines = []
        for ev in recent_events:
            event_lines.append(f"• `[{ev['event_id']}]` **{ev['event_type']}** (SKU: `{ev.get('sku_id')}`) — <t:{int(datetime.datetime.fromisoformat(ev['created_at']).timestamp())}:R>")

        if event_lines:
            desc += "\n\n**Recent Audit Events:**\n" + "\n".join(event_lines)

        embed = create_embed(title="⭐ RAI MONETIZATION CONTROL CENTER", description=desc, color=Colors.GOLD)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @premium_group.command(name="test-entitlement", description="QA Test Mode: inject or revoke test entitlements")
    @app_commands.describe(
        action="Action to perform",
        scope="Entitlement scope (user or guild)",
        target_id="User ID or Guild ID to apply entitlement to",
        sku_id="Mock or test SKU ID",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Inject Test Entitlement", value="inject"),
        app_commands.Choice(name="Revoke Test Entitlement", value="revoke"),
    ])
    @app_commands.choices(scope=[
        app_commands.Choice(name="User Scope", value="user"),
        app_commands.Choice(name="Guild Scope", value="guild"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def premium_test(
        self,
        interaction: discord.Interaction,
        action: str,
        scope: str,
        target_id: str,
        sku_id: Optional[str] = None,
    ):
        """Allows testing entitlement flows in staging without real financial transactions."""
        is_owner = (interaction.user.id == interaction.guild.owner_id) or (interaction.user.id == OWNER_ID)
        if not is_owner:
            await interaction.response.send_message("❌ Test Mode is restricted to the bot owner.", ephemeral=True)
            return

        target_int = int(target_id) if target_id.isdigit() else interaction.user.id
        sku_int = int(sku_id) if sku_id and sku_id.isdigit() else (9990001 if scope == "user" else 9990002)

        if action == "inject":
            test_ent_id = int(f"99{int(datetime.datetime.now().timestamp()) % 10000000}")
            success = await self.bot.db.upsert_premium_entitlement(
                entitlement_id=test_ent_id,
                user_id=target_int if scope == "user" else None,
                guild_id=target_int if scope == "guild" else None,
                sku_id=sku_int,
                scope=scope,
                status=EntitlementStatus.ACTIVE.value,
                is_test=1,
            )
            if success:
                msg = f"✅ Injected test entitlement **#{test_ent_id}** for {scope.upper()} `{target_int}` (SKU `{sku_int}`)."
                await interaction.response.send_message(embed=success_embed("Test Entitlement Active", msg), ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to inject test entitlement.", ephemeral=True)
        else:
            # Revoke
            if scope == "user":
                ents = await self.bot.db.get_active_user_entitlements(target_int)
            else:
                ents = await self.bot.db.get_active_guild_entitlements(target_int)

            if not ents:
                await interaction.response.send_message(f"ℹ️ No active entitlements found for {scope} `{target_int}`.", ephemeral=True)
                return

            for ent in ents:
                await self.bot.db.update_entitlement_status(ent["entitlement_id"], EntitlementStatus.REVOKED.value)

            await interaction.response.send_message(
                embed=info_embed("Test Entitlements Revoked", f"Revoked {len(ents)} active entitlement(s) for {scope} `{target_int}`."),
                ephemeral=True,
            )


async def setup(bot: SentinelBot) -> None:
    await bot.add_cog(PremiumCog(bot))
    # Initialize premium tables & default rules
    await PremiumService.initialize(bot)
