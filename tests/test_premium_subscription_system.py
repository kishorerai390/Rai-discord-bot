"""
Comprehensive Unit & Integration Test Suite for MusicMaid Premium Subscription & Purchase System.
Tests SQLite database persistence, EntitlementService, PaymentService checkout creation,
session verification against Stripe, idempotent webhook handlers, and public config masking.
"""

from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import stripe

import music_bot.config as config
from music_bot.database.db import MusicDatabase
from music_bot.services.entitlement_service import EntitlementService
from music_bot.services.payment_service import PaymentService


class TestPremiumSubscriptionSystem(unittest.IsolatedAsyncioTestCase):
    """Test suite for MusicMaid Premium Subscription and Payment System."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_music.db"
        self.db = MusicDatabase(db_path=self.db_path)
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_01_database_subscription_lifecycle(self):
        """Test creating, querying, updating, and cancelling user subscriptions."""
        user_id = 1234567890

        # Initially no subscription
        sub = await self.db.get_user_subscription(user_id)
        self.assertIsNone(sub)
        is_prem = await self.db.is_premium(user_id=user_id)
        self.assertFalse(is_prem)

        # Upsert active monthly subscription
        now_iso = datetime.now(timezone.utc).isoformat()
        renewal_iso = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        await self.db.upsert_user_subscription(
            user_id=user_id,
            plan="monthly",
            status="active",
            provider="stripe",
            customer_id="cus_test_abc123",
            subscription_id="sub_test_abc123",
            payment_ref="cs_test_abc123",
            start_date=now_iso,
            renewal_date=renewal_iso,
        )

        sub = await self.db.get_user_subscription(user_id)
        self.assertIsNotNone(sub)
        self.assertEqual(sub["plan"], "monthly")
        self.assertEqual(sub["status"], "active")
        self.assertEqual(sub["provider_customer_id"], "cus_test_abc123")
        self.assertEqual(sub["provider_subscription_id"], "sub_test_abc123")

        is_prem = await self.db.is_premium(user_id=user_id)
        self.assertTrue(is_prem)

        # Cancel subscription
        success = await self.db.cancel_user_subscription(user_id, reason="User cancelled auto-renewal")
        self.assertTrue(success)

        sub_after_cancel = await self.db.get_user_subscription(user_id)
        self.assertEqual(sub_after_cancel["status"], "cancelled")
        self.assertIsNotNone(sub_after_cancel["cancelled_at"])

        # Audit logs recorded
        logs = await self.db.get_subscription_audit_logs(user_id)
        self.assertGreaterEqual(len(logs), 2)
        actions = [log["action"] for log in logs]
        self.assertIn("subscription_upserted", actions)
        self.assertIn("subscription_cancelled", actions)

    async def test_02_webhook_idempotency(self):
        """Test idempotent tracking of Stripe webhook events."""
        event_id = "evt_test_unique_456"

        # Initially unprocessed
        processed = await self.db.is_webhook_event_processed(event_id)
        self.assertFalse(processed)

        # Record event
        await self.db.record_webhook_event(
            event_id=event_id,
            provider="stripe",
            event_type="checkout.session.completed",
            payload='{"id": "evt_test_unique_456"}',
            status="processed",
        )

        # Now processed
        processed_again = await self.db.is_webhook_event_processed(event_id)
        self.assertTrue(processed_again)

    async def test_03_entitlement_service_free_and_premium(self):
        """Test entitlement resolution for free, active premium, and expired users."""
        free_user_id = 999900001
        active_user_id = 999900002
        expired_user_id = 999900003

        # Free user
        ent_free = await EntitlementService.get_user_entitlement(free_user_id, self.db)
        self.assertFalse(ent_free.is_premium)
        self.assertEqual(ent_free.plan, "free")
        self.assertFalse(ent_free.perks["boosted_volume"])
        self.assertFalse(ent_free.perks["twenty_four_seven"])
        self.assertFalse(await EntitlementService.can_access_feature(free_user_id, "boosted_volume", self.db))

        # Active premium user
        now_iso = datetime.now(timezone.utc).isoformat()
        future_iso = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        await self.db.upsert_user_subscription(
            user_id=active_user_id,
            plan="yearly",
            status="active",
            provider="stripe",
            customer_id="cus_active_1",
            subscription_id="sub_active_1",
            payment_ref="cs_active_1",
            start_date=now_iso,
            renewal_date=future_iso,
        )

        ent_prem = await EntitlementService.get_user_entitlement(active_user_id, self.db)
        self.assertTrue(ent_prem.is_premium)
        self.assertEqual(ent_prem.plan, "yearly")
        self.assertTrue(ent_prem.perks["boosted_volume"])
        self.assertTrue(ent_prem.perks["twenty_four_seven"])
        self.assertTrue(ent_prem.perks["maid_voice_dj"])
        self.assertTrue(await EntitlementService.can_access_feature(active_user_id, "twenty_four_seven", self.db))

        # Expired subscription
        past_iso = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        past_start = (datetime.now(timezone.utc) - timedelta(days=32)).isoformat()
        await self.db.upsert_user_subscription(
            user_id=expired_user_id,
            plan="monthly",
            status="active",
            provider="stripe",
            customer_id="cus_exp_1",
            subscription_id="sub_exp_1",
            payment_ref="cs_exp_1",
            start_date=past_start,
            renewal_date=past_iso,
        )

        ent_exp = await EntitlementService.get_user_entitlement(expired_user_id, self.db)
        self.assertFalse(ent_exp.is_premium)
        self.assertEqual(ent_exp.status, "expired")

    async def test_04_payment_service_unconfigured_guard(self):
        """Verify payment service throws clear error when Stripe is unconfigured."""
        with patch.object(config, "is_stripe_configured", return_value=False):
            with self.assertRaises(RuntimeError) as ctx:
                await PaymentService.create_checkout_session(
                    user_id=123,
                    user_email="test@example.com",
                    user_name="AnimeHero",
                    plan_id="monthly",
                    success_url="https://musicmaid.com/premium/success",
                    cancel_url="https://musicmaid.com/premium/cancel",
                )
            self.assertIn("Payment gateway is not configured", str(ctx.exception))

    async def test_05_payment_service_create_session(self):
        """Verify Stripe checkout session creation parameters."""
        mock_session = MagicMock()
        mock_session.id = "cs_test_session_xyz"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_session_xyz"

        with patch.object(config, "is_stripe_configured", return_value=True), \
             patch.object(config, "STRIPE_SECRET_KEY", "sk_test_12345"), \
             patch("music_bot.services.payment_service.stripe.checkout.Session.create", return_value=mock_session) as mock_create:

            res = await PaymentService.create_checkout_session(
                user_id=777888,
                user_email="user@discord.gg",
                user_name="TsundereFan#1234",
                plan_id="monthly",
                success_url="https://musicmaid.onrender.com/premium/success",
                cancel_url="https://musicmaid.onrender.com/premium/cancel",
                db=self.db,
            )

            self.assertEqual(res["session_id"], "cs_test_session_xyz")
            self.assertEqual(res["checkout_url"], "https://checkout.stripe.com/pay/cs_test_session_xyz")
            mock_create.assert_called_once()
            kwargs = mock_create.call_args[1]
            self.assertEqual(kwargs["client_reference_id"], "777888")
            self.assertEqual(kwargs["customer_email"], "user@discord.gg")
            self.assertEqual(kwargs["metadata"]["plan"], "monthly")

    async def test_06_payment_service_verify_session(self):
        """Verify cryptographically checking completed Stripe session and activating subscription."""
        mock_session = MagicMock()
        mock_session.id = "cs_verified_777"
        mock_session.payment_status = "paid"
        mock_session.status = "complete"
        mock_session.client_reference_id = "5551234"
        mock_session.customer = "cus_mock_888"
        mock_session.subscription = "sub_mock_999"
        mock_session.payment_intent = "pi_mock_000"
        mock_session.metadata = {"plan": "yearly", "user_id": "5551234"}
        mock_session.amount_total = 4999
        mock_session.currency = "usd"

        with patch.object(config, "is_stripe_configured", return_value=True), \
             patch("music_bot.services.payment_service.stripe.checkout.Session.retrieve", return_value=mock_session):

            res = await PaymentService.verify_checkout_session(
                session_id="cs_verified_777",
                expected_user_id=5551234,
                db=self.db,
            )

            self.assertTrue(res["verified"])
            self.assertEqual(res["plan"], "yearly")
            self.assertEqual(res["user_id"], 5551234)

            # Check DB updated
            sub = await self.db.get_user_subscription(5551234)
            self.assertIsNotNone(sub)
            self.assertEqual(sub["status"], "active")
            self.assertEqual(sub["plan"], "yearly")
            self.assertEqual(sub["provider_customer_id"], "cus_mock_888")

    async def test_07_payment_service_webhook_idempotency_and_event_handling(self):
        """Verify webhook processing for checkout.session.completed and subscription deletion."""
        event_payload = {
            "id": "evt_webhook_live_123",
            "object": "event",
            "api_version": "2024-06-20",
            "created": 1729000000,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_webhook_session_999",
                    "object": "checkout.session",
                    "payment_status": "paid",
                    "client_reference_id": "8882221",
                    "customer": "cus_wh_1",
                    "subscription": "sub_wh_1",
                    "currency": "usd",
                    "amount_total": 499,
                    "metadata": {"plan": "monthly", "user_id": "8882221"},
                }
            },
        }

        mock_event = stripe.Event.construct_from(event_payload, key="whsec_test_secret")

        with patch.object(config, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret"), \
             patch("music_bot.services.payment_service.stripe.Webhook.construct_event", return_value=mock_event):

            # First delivery: processes successfully
            res1 = await PaymentService.verify_and_process_webhook(
                payload_bytes=b'{"test": 1}',
                sig_header="t=123,v1=mock_signature",
                db=self.db,
            )
            self.assertTrue(res1["success"])
            self.assertEqual(res1["event_type"], "checkout.session.completed")

            # Check DB was populated
            sub = await self.db.get_user_subscription(8882221)
            self.assertIsNotNone(sub)
            self.assertEqual(sub["status"], "active")
            self.assertEqual(sub["plan"], "monthly")

            # Second delivery (duplicate): skipped idempotently
            res2 = await PaymentService.verify_and_process_webhook(
                payload_bytes=b'{"test": 1}',
                sig_header="t=123,v1=mock_signature",
                db=self.db,
            )
            self.assertTrue(res2["success"])
            self.assertTrue(res2.get("duplicate"))

    def test_08_payment_public_config_security(self):
        """Ensure sensitive Stripe keys are NEVER exposed in public config."""
        pub = config.get_payment_public_config()
        self.assertNotIn("STRIPE_SECRET_KEY", pub)
        self.assertNotIn("STRIPE_WEBHOOK_SECRET", pub)
        self.assertIn("enabled", pub)
        self.assertIn("configured", pub)
        self.assertIn("plans", pub)
        self.assertIn("monthly", pub["plans"])
        self.assertIn("yearly", pub["plans"])
        self.assertIn("amount", pub["plans"]["monthly"])


if __name__ == "__main__":
    unittest.main()
