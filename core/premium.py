"""
RAI — Official Discord Premium App Monetization Subsystem.

Provides:
- Architecture integrating official Discord Entitlements and SKUs without fake payment flows.
- Strict separation between Free Tier and Premium Features.
- Personal (User) and Server (Guild) entitlement scoping without scope mixing.
- Deterministic, client-untrusted PremiumFeatureGate.has_access() evaluation.
- Subscription lifecycle tracking: ACTIVE, EXPIRING, EXPIRED, CANCELLED, REVOKED.
- Native Discord SKU button integration (discord.ui.Button(sku_id=...)).
- Upsell embeds with clear, friendly upgrade paths when premium features are gated.
- Audit event logging with unique RAI-PREM-XXXXXX identifiers.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

import discord
from discord import ui

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed
from utils.owner_reporter import OWNER_ID, OwnerReporter, generate_incident_id

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger(__name__)


# =============================================================================
# 1. ENUMS & DATA MODELS
# =============================================================================

class EntitlementScope(str, Enum):
    """Scope of entitlement benefits: Personal (User) or Server-wide (Guild)."""
    USER = "user"
    GUILD = "guild"
    ANY = "any"


class EntitlementStatus(str, Enum):
    """Official Discord entitlement lifecycle state."""
    ACTIVE = "active"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REVOKED = "revoked"
    TEST = "test"


class PremiumFeature(str, Enum):
    """Catalog of feature gates managed by the Premium System."""
    ADVANCED_OPERATIONS = "advanced_operations"
    ADVANCED_ROOMS = "advanced_rooms"
    ADVANCED_MUSIC = "advanced_music"
    ADVANCED_SECURITY = "advanced_security"
    SECURITY_SIMULATION = "security_simulation"
    AUTOMATED_BACKUPS = "automated_backups"
    CONFIGURATION_VERSIONS = "configuration_versions"
    ADVANCED_ANALYTICS = "advanced_analytics"
    ADVANCED_AUTOMATION = "advanced_automation"
    ADVANCED_HEALTH = "advanced_health"
    CUSTOM_TEMPLATES = "custom_templates"


@dataclass
class FeatureAccessResult:
    """Detailed result of a feature entitlement evaluation."""
    has_access: bool
    feature: str
    reason: str
    required_scope: EntitlementScope = EntitlementScope.ANY
    active_entitlement: Optional[Dict[str, Any]] = None
    upgrade_sku_id: Optional[int] = None

    @property
    def is_upgrade_required(self) -> bool:
        return not self.has_access


# Default feature access requirements
DEFAULT_FEATURE_RULES: Dict[str, Tuple[str, str, EntitlementScope]] = {
    PremiumFeature.ADVANCED_OPERATIONS.value: (
        "Advanced Operations Assistant",
        "Multi-step chained operations, deep telemetry, and proactive analysis",
        EntitlementScope.ANY,
    ),
    PremiumFeature.ADVANCED_ROOMS.value: (
        "Advanced Dynamic Voice Rooms",
        "Custom bitrate, high user limits, advanced delegation, and templates",
        EntitlementScope.ANY,
    ),
    PremiumFeature.ADVANCED_MUSIC.value: (
        "Advanced Music Engine",
        "Unlimited queue depth, lossless playback DSP, and autoplay streaming",
        EntitlementScope.ANY,
    ),
    PremiumFeature.ADVANCED_SECURITY.value: (
        "Advanced Threat Intelligence",
        "Deep audit histories, automated risk scoring, and threat timelines",
        EntitlementScope.GUILD,
    ),
    PremiumFeature.SECURITY_SIMULATION.value: (
        "Raid & Nuke Attack Simulation",
        "Safe sandbox attack simulations testing real mitigation thresholds",
        EntitlementScope.GUILD,
    ),
    PremiumFeature.AUTOMATED_BACKUPS.value: (
        "High-Frequency Automated Backups",
        "Extended retention (up to 30 backups) with automated hourly snapshots",
        EntitlementScope.GUILD,
    ),
    PremiumFeature.CONFIGURATION_VERSIONS.value: (
        "Configuration Versioning & Rollback",
        "Snapshot, inspect, and safely restore past bot configuration versions",
        EntitlementScope.GUILD,
    ),
    PremiumFeature.ADVANCED_ANALYTICS.value: (
        "Extended Operations Analytics",
        "30-day comprehensive historical operational summaries and telemetry",
        EntitlementScope.ANY,
    ),
    PremiumFeature.ADVANCED_AUTOMATION.value: (
        "Cron-Based Scheduled Tasks",
        "Persistent background recurring task execution and reminders",
        EntitlementScope.GUILD,
    ),
    PremiumFeature.ADVANCED_HEALTH.value: (
        "Deep Subsystem Observability",
        "Real-time health telemetry exports and continuous watchdog monitoring",
        EntitlementScope.GUILD,
    ),
    PremiumFeature.CUSTOM_TEMPLATES.value: (
        "Custom Voice Room Templates",
        "Server-specific custom presets for gaming, chill, creator, and watch parties",
        EntitlementScope.ANY,
    ),
}


# =============================================================================
# 2. SKU SERVICE (DISCORD MONETIZATION CATALOG)
# =============================================================================

class SKUService:
    """Manages official Discord Premium App SKU configuration and product catalog."""

    @classmethod
    def get_user_premium_sku_id(cls) -> Optional[int]:
        sku_str = os.getenv("DISCORD_USER_PREMIUM_SKU_ID", "").strip()
        return int(sku_str) if sku_str.isdigit() else None

    @classmethod
    def get_guild_premium_sku_id(cls) -> Optional[int]:
        sku_str = os.getenv("DISCORD_GUILD_PREMIUM_SKU_ID", "").strip()
        return int(sku_str) if sku_str.isdigit() else None

    @classmethod
    def get_lifetime_premium_sku_id(cls) -> Optional[int]:
        sku_str = os.getenv("DISCORD_LIFETIME_PREMIUM_SKU_ID", "").strip()
        return int(sku_str) if sku_str.isdigit() else None

    @classmethod
    def is_monetization_configured(cls) -> bool:
        """Returns True if at least one official Discord SKU is configured."""
        return bool(cls.get_user_premium_sku_id() or cls.get_guild_premium_sku_id())

    @classmethod
    def get_sku_for_scope(cls, scope: EntitlementScope) -> Optional[int]:
        if scope == EntitlementScope.USER:
            return cls.get_user_premium_sku_id()
        elif scope == EntitlementScope.GUILD:
            return cls.get_guild_premium_sku_id()
        else:
            return cls.get_guild_premium_sku_id() or cls.get_user_premium_sku_id()

    @classmethod
    async def initialize_products(cls, bot: SentinelBot) -> None:
        """Initializes default products into SQLite catalog."""
        products = [
            (cls.get_user_premium_sku_id() or 100000000000000001, "Rai Personal Premium", "Personal access across all voice rooms and audio tools", "user", 5, 499),
            (cls.get_guild_premium_sku_id() or 100000000000000002, "Rai Server Premium", "Server-wide unlock for all members, anti-raid simulations, and backups", "guild", 5, 999),
        ]
        for sku_id, name, desc, scope, sku_type, price in products:
            await bot.db.upsert_premium_product(
                sku_id=sku_id,
                name=name,
                description=desc,
                scope=scope,
                sku_type=sku_type,
                price_cents=price,
                is_active=1,
            )


# =============================================================================
# 3. ENTITLEMENT SERVICE (OFFICIAL DISCORD INTEGRATION)
# =============================================================================

class EntitlementService:
    """
    Ingests, reconciles, and manages official Discord Entitlements.
    Never relies on client-side claims or button clicks alone.
    """

    @classmethod
    async def ingest_discord_entitlement(
        cls,
        bot: SentinelBot,
        entitlement: discord.Entitlement,
        is_test: bool = False,
    ) -> bool:
        """
        Processes an official discord.Entitlement event or fetched object.
        Stores entitlement securely in SQLite and dispatches audit events.
        """
        entitlement_id = entitlement.id
        sku_id = entitlement.sku_id
        user_id = entitlement.user_id
        guild_id = entitlement.guild_id

        # Determine scope from entitlement attributes or known SKUs
        if guild_id:
            scope = EntitlementScope.GUILD.value
        else:
            scope = EntitlementScope.USER.value

        # Check start and end timestamps
        starts_at = entitlement.starts_at.isoformat() if entitlement.starts_at else datetime.datetime.now(datetime.timezone.utc).isoformat()
        ends_at = entitlement.ends_at.isoformat() if entitlement.ends_at else None

        # Determine status
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        if entitlement.deleted:
            status = EntitlementStatus.REVOKED.value
        elif entitlement.ends_at and entitlement.ends_at <= now_dt:
            status = EntitlementStatus.EXPIRED.value
        else:
            status = EntitlementStatus.ACTIVE.value

        # Persist entitlement
        success = await bot.db.upsert_premium_entitlement(
            entitlement_id=entitlement_id,
            user_id=user_id,
            guild_id=guild_id,
            sku_id=sku_id,
            scope=scope,
            status=status,
            starts_at=starts_at,
            ends_at=ends_at,
            is_test=1 if is_test else 0,
            consumed=1 if getattr(entitlement, "consumed", False) else 0,
        )

        if success:
            event_id = generate_incident_id("RAI-PREM")
            await bot.db.record_premium_event(
                event_id=event_id,
                event_type=f"entitlement_{status}",
                entitlement_id=entitlement_id,
                user_id=user_id,
                guild_id=guild_id,
                sku_id=sku_id,
                details={
                    "scope": scope,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "is_test": is_test,
                },
            )

            # Dispatch notification
            await PremiumNotificationService.notify_status_change(
                bot=bot,
                scope=EntitlementScope(scope),
                status=EntitlementStatus(status),
                user_id=user_id,
                guild_id=guild_id,
                sku_id=sku_id,
                event_id=event_id,
            )

        return success

    @classmethod
    async def reconcile_with_discord(cls, bot: SentinelBot) -> int:
        """
        Fetches official entitlements from the Discord API and updates the local database.
        Safe for startup reconciliation and disaster recovery.
        """
        reconciled = 0
        try:
            if hasattr(bot, "fetch_entitlements"):
                async for entitlement in bot.fetch_entitlements(exclude_ended=True):
                    await cls.ingest_discord_entitlement(bot, entitlement)
                    reconciled += 1
        except Exception as e:
            logger.warning(f"Entitlement reconciliation note: {e}")
        return reconciled

    @classmethod
    async def expire_stale_entitlements(cls, bot: SentinelBot) -> int:
        """Periodic safety worker checking for expired subscription periods."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        expired = await bot.db.get_expired_entitlements(now_iso)
        count = 0
        for ent in expired:
            ent_id = ent["entitlement_id"]
            await bot.db.update_entitlement_status(ent_id, EntitlementStatus.EXPIRED.value)
            event_id = generate_incident_id("RAI-PREM")
            await bot.db.record_premium_event(
                event_id=event_id,
                event_type="entitlement_expired",
                entitlement_id=ent_id,
                user_id=ent.get("user_id"),
                guild_id=ent.get("guild_id"),
                sku_id=ent.get("sku_id"),
                details={"reason": "subscription_period_elapsed"},
            )
            count += 1
        return count


# =============================================================================
# 4. PREMIUM FEATURE GATE (AUTHORITATIVE ACCESS CHECK)
# =============================================================================

class PremiumFeatureGate:
    """
    Authoritative gatekeeper for Free vs Premium features.
    Never trusts client-side inputs or unverified parameters.
    """

    @classmethod
    async def initialize_default_rules(cls, bot: SentinelBot) -> None:
        """Initializes configurable feature access rules in the database."""
        for feat_key, (name, desc, req_scope) in DEFAULT_FEATURE_RULES.items():
            existing = await bot.db.get_feature_access_config(feat_key)
            if not existing:
                await bot.db.set_feature_access_config(
                    feature_key=feat_key,
                    name=name,
                    description=desc,
                    scope_required=req_scope.value,
                    is_enabled=1,
                )

    @classmethod
    async def has_access(
        cls,
        bot: SentinelBot,
        feature: str | PremiumFeature,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ) -> FeatureAccessResult:
        """
        Determines whether a user or guild has valid entitlement for a feature.
        Evaluates:
        1. Feature availability toggle.
        2. Scope requirements (USER vs GUILD).
        3. Active, non-expired entitlements in SQLite.
        """
        feat_name = feature.value if isinstance(feature, PremiumFeature) else str(feature)

        # 1. Fetch feature config from DB
        cfg = await bot.db.get_feature_access_config(feat_name)
        if cfg and cfg.get("is_enabled") == 0:
            return FeatureAccessResult(
                has_access=False,
                feature=feat_name,
                reason="This feature is temporarily disabled by administrative maintenance.",
            )

        req_scope_str = cfg.get("scope_required", "any") if cfg else "any"
        req_scope = EntitlementScope(req_scope_str) if req_scope_str in ("user", "guild", "any") else EntitlementScope.ANY

        # 2. Check Server/Guild Entitlement
        if guild_id and req_scope in (EntitlementScope.GUILD, EntitlementScope.ANY):
            guild_ents = await bot.db.get_active_guild_entitlements(guild_id)
            if guild_ents:
                return FeatureAccessResult(
                    has_access=True,
                    feature=feat_name,
                    reason="Server has active Rai Server Premium.",
                    required_scope=req_scope,
                    active_entitlement=guild_ents[0],
                )

        # 3. Check Personal/User Entitlement
        if user_id and req_scope in (EntitlementScope.USER, EntitlementScope.ANY):
            user_ents = await bot.db.get_active_user_entitlements(user_id)
            if user_ents:
                return FeatureAccessResult(
                    has_access=True,
                    feature=feat_name,
                    reason="User has active Rai Personal Premium.",
                    required_scope=req_scope,
                    active_entitlement=user_ents[0],
                )

        # 4. Check if Guild Owner has User Premium (Personal delegation where permitted)
        if guild_id and user_id:
            guild = bot.get_guild(guild_id)
            if guild and user_id == guild.owner_id and req_scope == EntitlementScope.ANY:
                owner_ents = await bot.db.get_active_user_entitlements(user_id)
                if owner_ents:
                    return FeatureAccessResult(
                        has_access=True,
                        feature=feat_name,
                        reason="Server Owner has active Personal Premium.",
                        required_scope=req_scope,
                        active_entitlement=owner_ents[0],
                    )

        # Access Denied: Return upgrade requirement
        upgrade_sku = SKUService.get_sku_for_scope(req_scope)
        return FeatureAccessResult(
            has_access=False,
            feature=feat_name,
            reason=f"Requires Rai {'Server' if req_scope == EntitlementScope.GUILD else 'Personal'} Premium.",
            required_scope=req_scope,
            upgrade_sku_id=upgrade_sku,
        )


# =============================================================================
# 5. PREMIUM NOTIFICATION SERVICE
# =============================================================================

class PremiumNotificationService:
    """Dispatches lifecycle notifications to users and server administrative channels."""

    @classmethod
    async def notify_status_change(
        cls,
        bot: SentinelBot,
        scope: EntitlementScope,
        status: EntitlementStatus,
        user_id: Optional[int],
        guild_id: Optional[int],
        sku_id: int,
        event_id: str,
    ) -> None:
        """Sends clean, non-spammy notification upon premium lifecycle changes."""
        scope_name = "Server Premium" if scope == EntitlementScope.GUILD else "Personal Premium"

        if status == EntitlementStatus.ACTIVE:
            title = f"⭐ RAI {scope_name.upper()} ACTIVATED"
            desc = (
                f"Your subscription is now **active**!\n\n"
                f"• **Audit ID:** `{event_id}`\n"
                f"• **SKU:** `{sku_id}`\n"
                f"• **Status:** 🟢 `ACTIVE`\n\n"
                f"**Unlocked Capabilities:**\n"
                f"• Advanced Dynamic Voice Room controls & custom templates\n"
                f"• Extended music streaming DSP & unlimited queues\n"
                f"• Safe raid attack simulations & threat timelines\n"
                f"• Automated backup retention & configuration version rollback"
            )
            embed = create_embed(title=title, description=desc, color=Colors.GOLD)
        elif status == EntitlementStatus.EXPIRED:
            title = f"⚠️ RAI {scope_name.upper()} EXPIRED"
            desc = (
                f"Your subscription has expired. Premium features have been safely suspended.\n\n"
                f"• **Audit ID:** `{event_id}`\n"
                f"• *Your existing rooms, backups, and configurations remain safely preserved.*"
            )
            embed = warning_embed(title, desc)
        elif status == EntitlementStatus.REVOKED:
            title = f"ℹ️ RAI {scope_name.upper()} REVOKED"
            desc = f"Your entitlement was cancelled or revoked. Audit code: `{event_id}`."
            embed = error_embed(title, desc)
        else:
            return

        # Route to user DM if user scope
        if user_id and scope == EntitlementScope.USER:
            try:
                user = bot.get_user(user_id) or await bot.fetch_user(user_id)
                if user:
                    await user.send(embed=embed)
            except Exception:
                pass

        # Route to guild private control if guild scope
        if guild_id:
            OwnerReporter.send_bot_report(
                bot=bot,
                guild_id=guild_id,
                event=f"Monetization: {scope_name} {status.value.capitalize()}",
                details={"Audit ID": event_id, "SKU": sku_id, "Status": status.value},
            )


# =============================================================================
# 6. HIGH-LEVEL FACADE: PREMIUM SERVICE
# =============================================================================

class PremiumService:
    """Master facade providing access to products, entitlements, and feature gating."""

    @classmethod
    async def initialize(cls, bot: SentinelBot) -> None:
        """Initializes database products and default feature rules."""
        await SKUService.initialize_products(bot)
        await PremiumFeatureGate.initialize_default_rules(bot)
        await EntitlementService.reconcile_with_discord(bot)

    @classmethod
    async def get_status_overview(
        cls,
        bot: SentinelBot,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Gathers active entitlements for user and server."""
        user_ents = await bot.db.get_active_user_entitlements(user_id) if user_id else []
        guild_ents = await bot.db.get_active_guild_entitlements(guild_id) if guild_id else []

        return {
            "has_user_premium": bool(user_ents),
            "has_guild_premium": bool(guild_ents),
            "user_entitlements": user_ents,
            "guild_entitlements": guild_ents,
            "is_monetization_configured": SKUService.is_monetization_configured(),
        }


# =============================================================================
# 7. INTERACTIVE UI VIEWS (STORE, UPSELL, & COMPARISON)
# =============================================================================

class PremiumStoreView(ui.View):
    """Interactive storefront for Discord Premium Apps monetization."""

    def __init__(self, bot: SentinelBot, user_id: int, guild_id: Optional[int] = None):
        super().__init__(timeout=180)
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id

        # If official Discord SKUs are configured, attach official Discord purchase buttons!
        guild_sku = SKUService.get_guild_premium_sku_id()
        user_sku = SKUService.get_user_premium_sku_id()

        if guild_sku:
            btn_guild = ui.Button(
                label="Server Premium",
                emoji="⭐",
                style=discord.ButtonStyle.primary,
                sku_id=guild_sku,
                row=0,
            )
            self.add_item(btn_guild)

        if user_sku:
            btn_user = ui.Button(
                label="Personal Premium",
                emoji="👤",
                style=discord.ButtonStyle.secondary,
                sku_id=user_sku,
                row=0,
            )
            self.add_item(btn_user)

    @ui.button(label="Compare Plans", emoji="📋", style=discord.ButtonStyle.secondary, row=1)
    async def compare_btn(self, interaction: discord.Interaction, button: ui.Button):
        embed = create_plans_comparison_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="My Subscription", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def my_sub_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        status = await PremiumService.get_status_overview(self.bot, interaction.user.id, interaction.guild_id)

        user_status = "🟢 Active" if status["has_user_premium"] else "⚪ Free Tier"
        guild_status = "🟢 Active" if status["has_guild_premium"] else "⚪ Free Tier"

        desc = (
            f"👤 **Personal Premium:** {user_status}\n"
            f"🏰 **Server Premium:** {guild_status}\n\n"
            f"*Subscriptions are automatically managed and renewed through Discord.*"
        )
        embed = create_embed(title="⭐ Your Subscription Status", description=desc, color=Colors.PRIMARY)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="FAQ", emoji="❓", style=discord.ButtonStyle.secondary, row=1)
    async def faq_btn(self, interaction: discord.Interaction, button: ui.Button):
        desc = (
            "**Q: How does purchasing work?**\n"
            "A: Rai uses Discord's official Premium Apps checkout. All payments and subscriptions are processed directly and securely by Discord.\n\n"
            "**Q: What is the difference between Personal and Server Premium?**\n"
            "A: **Personal Premium** unlocks advanced voice room controls for your own rooms anywhere. **Server Premium** unlocks all features (backups, simulations, room presets) for everyone in this server.\n\n"
            "**Q: What happens if my subscription expires?**\n"
            "A: Your configurations and voice rooms are safely preserved. Gated features will gracefully revert to Free Tier limits."
        )
        embed = info_embed("❓ Rai Premium FAQ", desc)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PremiumUpgradeView(ui.View):
    """Rendered when a non-premium user attempts to access a gated premium feature."""

    def __init__(self, bot: SentinelBot, user_id: int, feature_key: str, required_scope: EntitlementScope):
        super().__init__(timeout=120)
        self.bot = bot
        self.user_id = user_id
        self.feature_key = feature_key
        self.required_scope = required_scope

        # Attach official Discord purchase button if SKU configured
        sku_id = SKUService.get_sku_for_scope(required_scope)
        if sku_id:
            btn_upgrade = ui.Button(
                label=f"Upgrade to {'Server' if required_scope == EntitlementScope.GUILD else 'Personal'} Premium",
                emoji="⭐",
                style=discord.ButtonStyle.primary,
                sku_id=sku_id,
                row=0,
            )
            self.add_item(btn_upgrade)

    @ui.button(label="Compare Plans", emoji="📋", style=discord.ButtonStyle.secondary, row=1)
    async def compare_btn(self, interaction: discord.Interaction, button: ui.Button):
        embed = create_plans_comparison_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)


def create_plans_comparison_embed() -> discord.Embed:
    """Generates the official Free vs Personal vs Server plan comparison matrix."""
    desc = (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "**Feature Matrix**\n\n"
        "| Feature | Free Tier | Personal ⭐ | Server Premium 🏰 |\n"
        "| :--- | :---: | :---: | :---: |\n"
        "| Basic Moderation & Security | ✅ | ✅ | ✅ |\n"
        "| Dynamic Voice Rooms | Basic | Advanced | Advanced Server-Wide |\n"
        "| Music Playback | Standard | Lossless DSP | Lossless DSP |\n"
        "| Raid Simulation Mode | ❌ | ❌ | ✅ |\n"
        "| Automated Backups | Manual | Manual | Automated 30-Day |\n"
        "| Configuration Rollback | ❌ | ❌ | ✅ |\n"
        "| Multi-Step Chained Tasks | Basic | Full | Full |\n"
        "| Custom Room Templates | ❌ | ✅ | ✅ |\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "*Core safety and basic server moderation remain 100% free forever.*"
    )
    return create_embed(
        title="📋 RAI — PLAN COMPARISON",
        description=desc,
        color=Colors.GOLD,
    )


def create_premium_upgrade_embed(
    feature_key: str,
    feature_name: Optional[str] = None,
    required_scope: EntitlementScope = EntitlementScope.ANY,
) -> discord.Embed:
    """Generates a polished upsell embed when a premium gate is encountered."""
    rule = DEFAULT_FEATURE_RULES.get(feature_key)
    name = feature_name or (rule[0] if rule else feature_key.replace("_", " ").title())
    desc_str = rule[1] if rule else "Advanced Rai operational capability"
    scope_str = "Server Premium" if required_scope == EntitlementScope.GUILD else "Personal or Server Premium"

    desc = (
        f"This capability requires **Rai {scope_str}**.\n\n"
        f"• **Feature:** `{name}`\n"
        f"• **Capability:** {desc_str}\n"
        f"• **Required Tier:** ⭐ **{scope_str}**\n\n"
        f"*Upgrade securely via official Discord In-App checkout below.*"
    )
    embed = create_embed(
        title="⭐ RAI PREMIUM REQUIRED",
        description=desc,
        color=Colors.GOLD,
    )
    embed.set_footer(text="Official Discord Premium Apps • Safe & Seamless In-App Subscriptions")
    return embed
