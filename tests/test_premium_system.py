"""
Unit and Integration Tests for RAI Premium Monetization System (Discord Premium Apps).
Tests:
- Product and SKU catalog configuration.
- Entitlement ingestion, update, revocation, deduplication, and expiration.
- User vs Server entitlement scopes.
- PremiumFeatureGate.has_access() evaluation under Free, Personal Premium, and Server Premium.
- Feature toggle override (administrative maintenance).
- Natural language command gating ("simulate raid" blocked when Free, allowed when Server Premium).
- Zero storage of payment/card details.
"""

import asyncio
import datetime
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from core.nl_control import (
    NLActionDispatcher,
    NLContextManager,
    NLIntent,
    NLParser,
    ParsedTask,
)
from core.premium import (
    EntitlementScope,
    EntitlementService,
    EntitlementStatus,
    FeatureAccessResult,
    PremiumFeature,
    PremiumFeatureGate,
    PremiumNotificationService,
    PremiumService,
    SKUService,
    create_plans_comparison_embed,
    create_premium_upgrade_embed,
)
from database.manager import DatabaseManager


class TestPremiumMonetizationSystem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_bot.db"

        import aiosqlite
        from database.database import Database
        from database.migrations import run_migrations

        DatabaseManager._instance = None
        self.conn = await aiosqlite.connect(str(self.db_path))
        self.conn.row_factory = aiosqlite.Row
        await run_migrations(self.conn)

        self.db = Database(str(self.db_path))
        self.db._db = self.conn

        self.db_mgr = DatabaseManager(self.db_path)
        self.db_mgr.sqlite = self.db
        DatabaseManager._instance = self.db_mgr

        # Mock Bot
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.db_manager = self.db_mgr
        self.bot.user = MagicMock(id=1554732669072445532, spec=discord.ClientUser)
        self.bot.cogs = {}

        # Mock Guild, Owner & Casual Member
        self.guild = MagicMock(spec=discord.Guild, id=1001, name="Premium Test Guild")
        self.guild.owner_id = 9999
        self.guild.member_count = 50
        self.guild.members = []
        self.guild.text_channels = []

        self.owner = MagicMock(spec=discord.Member, id=9999, name="ServerOwner")
        self.owner.mention = "<@9999>"
        self.owner.bot = False
        self.owner.guild_permissions = discord.Permissions(administrator=True)

        self.user = MagicMock(spec=discord.Member, id=2222, name="CasualMember")
        self.user.mention = "<@2222>"
        self.user.bot = False
        self.user.guild_permissions = discord.Permissions(send_messages=True)

        self.channel = MagicMock(spec=discord.TextChannel, id=5001, name="general")
        self.channel.guild = self.guild
        self.channel.send = AsyncMock()

        # Initialize Default Products and Feature Rules in DB
        await PremiumService.initialize(self.bot)

    async def asyncTearDown(self):
        DatabaseManager._instance = None
        if hasattr(self, "conn") and self.conn:
            await self.conn.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_sku_and_products_catalog(self):
        """Phase 8: Products catalog initialization and SKU scope resolution."""
        products = await self.db.list_premium_products(active_only=True)
        self.assertGreaterEqual(len(products), 2)

        scopes = [p["scope"] for p in products]
        self.assertIn("user", scopes)
        self.assertIn("guild", scopes)

    async def test_ingest_discord_entitlement_user_scope(self):
        """Phase 9: Ingesting an official Discord Entitlement for Personal Premium."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        mock_ent = MagicMock(spec=discord.Entitlement)
        mock_ent.id = 555001
        mock_ent.sku_id = 100000000000000001
        mock_ent.user_id = self.user.id
        mock_ent.guild_id = None  # User Scope
        mock_ent.deleted = False
        mock_ent.starts_at = now_dt
        mock_ent.ends_at = now_dt + datetime.timedelta(days=30)
        mock_ent.consumed = False

        success = await EntitlementService.ingest_discord_entitlement(self.bot, mock_ent)
        self.assertTrue(success)

        # Verify entitlement in DB
        ent = await self.db.get_premium_entitlement(555001)
        self.assertIsNotNone(ent)
        self.assertEqual(ent["user_id"], self.user.id)
        self.assertIsNone(ent["guild_id"])
        self.assertEqual(ent["scope"], "user")
        self.assertEqual(ent["status"], "active")

        # Verify audit event logged
        events = await self.db.get_recent_premium_events(user_id=self.user.id)
        self.assertGreaterEqual(len(events), 1)
        self.assertTrue(events[0]["event_id"].startswith("RAI-PREM-"))

    async def test_ingest_discord_entitlement_guild_scope(self):
        """Phase 9: Ingesting an official Discord Entitlement for Server Premium."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        mock_ent = MagicMock(spec=discord.Entitlement)
        mock_ent.id = 555002
        mock_ent.sku_id = 100000000000000002
        mock_ent.user_id = self.owner.id
        mock_ent.guild_id = self.guild.id  # Guild Scope
        mock_ent.deleted = False
        mock_ent.starts_at = now_dt
        mock_ent.ends_at = now_dt + datetime.timedelta(days=30)
        mock_ent.consumed = False

        success = await EntitlementService.ingest_discord_entitlement(self.bot, mock_ent)
        self.assertTrue(success)

        # Verify guild entitlements
        guild_ents = await self.db.get_active_guild_entitlements(self.guild.id)
        self.assertEqual(len(guild_ents), 1)
        self.assertEqual(guild_ents[0]["entitlement_id"], 555002)

    async def test_entitlement_deduplication(self):
        """Phase 9: Idempotent updates do not create duplicate entitlement records."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        mock_ent = MagicMock(spec=discord.Entitlement)
        mock_ent.id = 555003
        mock_ent.sku_id = 100000000000000001
        mock_ent.user_id = self.user.id
        mock_ent.guild_id = None
        mock_ent.deleted = False
        mock_ent.starts_at = now_dt
        mock_ent.ends_at = now_dt + datetime.timedelta(days=30)
        mock_ent.consumed = False

        # Ingest twice
        await EntitlementService.ingest_discord_entitlement(self.bot, mock_ent)
        await EntitlementService.ingest_discord_entitlement(self.bot, mock_ent)

        user_ents = await self.db.get_active_user_entitlements(self.user.id)
        matching = [e for e in user_ents if e["entitlement_id"] == 555003]
        self.assertEqual(len(matching), 1)

    async def test_entitlement_revocation_and_expiration(self):
        """Phase 10: Revoked and expired entitlements immediately deactivate access."""
        past_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        mock_ent = MagicMock(spec=discord.Entitlement)
        mock_ent.id = 555004
        mock_ent.sku_id = 100000000000000001
        mock_ent.user_id = self.user.id
        mock_ent.guild_id = None
        mock_ent.deleted = False
        mock_ent.starts_at = past_dt - datetime.timedelta(days=30)
        mock_ent.ends_at = past_dt  # Already ended
        mock_ent.consumed = False

        await EntitlementService.ingest_discord_entitlement(self.bot, mock_ent)

        # Check access before sweeping
        res_expired = await PremiumFeatureGate.has_access(
            self.bot, PremiumFeature.ADVANCED_ROOMS, user_id=self.user.id, guild_id=self.guild.id
        )
        self.assertFalse(res_expired.has_access)

        # Test revocation (deleted = True)
        mock_ent.deleted = True
        await EntitlementService.ingest_discord_entitlement(self.bot, mock_ent)
        ent_record = await self.db.get_premium_entitlement(555004)
        self.assertEqual(ent_record["status"], EntitlementStatus.REVOKED.value)

    async def test_feature_gate_free_tier(self):
        """Phase 2 & 5: Free users without active subscriptions are properly gated."""
        res = await PremiumFeatureGate.has_access(
            self.bot, PremiumFeature.SECURITY_SIMULATION, user_id=self.user.id, guild_id=self.guild.id
        )
        self.assertFalse(res.has_access)
        self.assertTrue(res.is_upgrade_required)
        self.assertEqual(res.required_scope, EntitlementScope.GUILD)

    async def test_feature_gate_user_premium_vs_server_premium(self):
        """Phase 4 & 5: Personal Premium unlocks user-scoped features, but not guild-only features."""
        # Grant user personal premium
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        await self.db.upsert_premium_entitlement(
            entitlement_id=777001,
            user_id=self.user.id,
            guild_id=None,
            sku_id=100000000000000001,
            scope="user",
            status="active",
            starts_at=now_dt.isoformat(),
            ends_at=(now_dt + datetime.timedelta(days=30)).isoformat(),
        )

        # User-scoped feature: ADVANCED_ROOMS (ANY scope) -> Access Granted!
        res_rooms = await PremiumFeatureGate.has_access(
            self.bot, PremiumFeature.ADVANCED_ROOMS, user_id=self.user.id, guild_id=self.guild.id
        )
        self.assertTrue(res_rooms.has_access)

        # Guild-scoped feature: SECURITY_SIMULATION (GUILD scope) -> Access Denied!
        res_sim = await PremiumFeatureGate.has_access(
            self.bot, PremiumFeature.SECURITY_SIMULATION, user_id=self.user.id, guild_id=self.guild.id
        )
        self.assertFalse(res_sim.has_access)

    async def test_feature_gate_server_premium_unlocks_all_members(self):
        """Phase 4 & 5: Server Premium unlocks guild and any scoped features for any member."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        await self.db.upsert_premium_entitlement(
            entitlement_id=777002,
            user_id=self.owner.id,
            guild_id=self.guild.id,
            sku_id=100000000000000002,
            scope="guild",
            status="active",
            starts_at=now_dt.isoformat(),
            ends_at=(now_dt + datetime.timedelta(days=30)).isoformat(),
        )

        # Regular member on this server checks guild-scoped feature -> Access Granted!
        res_sim = await PremiumFeatureGate.has_access(
            self.bot, PremiumFeature.SECURITY_SIMULATION, user_id=self.user.id, guild_id=self.guild.id
        )
        self.assertTrue(res_sim.has_access)

    async def test_feature_access_administrative_toggle(self):
        """Phase 15: Disabling a feature rule blocks access even for premium users."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        await self.db.upsert_premium_entitlement(
            entitlement_id=777003,
            user_id=None,
            guild_id=self.guild.id,
            sku_id=100000000000000002,
            scope="guild",
            status="active",
        )

        # Disable feature in DB
        await self.db.set_feature_access_config(
            feature_key=PremiumFeature.SECURITY_SIMULATION.value,
            name="Raid Simulation",
            description="Safe attack simulation",
            scope_required="guild",
            is_enabled=0,  # Disabled
        )

        res = await PremiumFeatureGate.has_access(
            self.bot, PremiumFeature.SECURITY_SIMULATION, user_id=self.owner.id, guild_id=self.guild.id
        )
        self.assertFalse(res.has_access)
        self.assertIn("temporarily disabled", res.reason)

    async def test_natural_language_premium_gate(self):
        """Phase 17: Natural language 'simulate raid' triggers premium gate on Free server."""
        session = NLContextManager.get_session(self.guild.id, self.owner.id, self.channel.id)
        task = ParsedTask(intent=NLIntent.SIMULATE_RAID, raw_segment="simulate raid", confidence=1.0)

        # 1. On Free Server -> Dispatches Premium Required upsell embed!
        res_free = await NLActionDispatcher.dispatch(
            bot=self.bot,
            guild=self.guild,
            user=self.owner,
            channel=self.channel,
            task=task,
            session=session,
        )
        self.assertFalse(res_free.success)
        self.assertEqual(res_free.title, "Premium Required")
        self.assertIn("RAI PREMIUM REQUIRED", res_free.embed.title)

        # 2. Grant Server Premium
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        await self.db.upsert_premium_entitlement(
            entitlement_id=777004,
            user_id=self.owner.id,
            guild_id=self.guild.id,
            sku_id=100000000000000002,
            scope="guild",
            status="active",
            starts_at=now_dt.isoformat(),
        )

        # Re-execute on Premium Server -> Simulation Completes!
        res_prem = await NLActionDispatcher.dispatch(
            bot=self.bot,
            guild=self.guild,
            user=self.owner,
            channel=self.channel,
            task=task,
            session=session,
        )
        self.assertTrue(res_prem.success)
        self.assertEqual(res_prem.title, "Simulation Complete")

    async def test_no_payment_data_stored(self):
        """Phase 25: Compliance check asserting zero payment credentials in database."""
        # Query column names of all premium tables
        for table in ("premium_products", "premium_entitlements", "premium_feature_access", "premium_events"):
            async with self.conn.execute(f"PRAGMA table_info({table})") as cur:
                columns = [row[1].lower() for row in await cur.fetchall()]
                for forbidden in ("card", "cvv", "credit", "bank", "account_number", "password"):
                    self.assertNotIn(forbidden, columns)


if __name__ == "__main__":
    unittest.main()
