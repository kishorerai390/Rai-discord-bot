import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from music_bot.database.db import DatabaseManager
from music_bot.services.entitlement_service import EntitlementService
from music_bot.services.payment_service import PaymentService
import music_bot.config as config


class TestPremiumSubscriptionSystem(unittest.TestCase):
    def setUp(self):
        # Use an in-memory SQLite database for isolated testing
        self.db = DatabaseManager(":memory:")
        self.entitlement = EntitlementService(self.db)
        self.payment = PaymentService(self.db)

    def tearDown(self):
        self.db.close()

    def test_database_subscription_lifecycle(self):
        """Test creating, reading, updating, and cancelling user subscriptions."""
        user_id = 123456789
        
        # Free by default
        sub = self.db.get_user_subscription(user_id)
        self.assertIsNone(sub)
        self.assertFalse(self.db.is_premium(user_id=user_id))

        # Upsert active monthly subscription
        now_iso = datetime.now(timezone.utc).isoformat()
        future_iso = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        self.db.upsert_user_subscription(
            user_id=user_id,
            plan="monthly",
            status="active",
            provider="stripe",
            customer_id="cus_test123",
            subscription_id="sub_test123",
            payment_ref="pi_test123",
            start_date=now_iso,
            renewal_date=future_iso,
        )

        sub = self.db.get_user_subscription(user_id)
        self.assertIsNotNone(sub)
        self.assertEqual(sub["plan"], "monthly")
        self.assertEqual(sub["status"], "active")
        self.assertEqual(sub["provider_customer_id"], "cus_test123")
        self.assertTrue(self.db.is_premium(user_id=user_id))

        # Check entitlement service
        ent = self.entitlement.get_user_entitlement(user_id)
        self.assertTrue(ent.is_premium)
        self.assertEqual(ent.plan, "monthly")
        self.assertEqual(ent.max_volume, 150)
        self.assertTrue(ent.stay_247_allowed)
        self.assertTrue(self.entitlement.can_access_feature(user_id, "24_7_mode"))
        self.assertTrue(self.entitlement.can_access_feature(user_id, "ai_maid_voice"))

        # Cancel subscription
        cancel_res = self.db.cancel_user_subscription(user_id, reason="User requested test cancellation")
        self.assertTrue(cancel_res)
        
        sub_cancelled = self.db.get_user_subscription(user_id)
        self.assertEqual(sub_cancelled["status"], "cancelled")
        self.assertIsNotNone(sub_cancelled["cancelled_at"])

        # Check audit log was recorded
        audit_logs = self.db.get_subscription_audit_logs(user_id)
        self.assertTrue(len(audit_logs) >= 2)
        actions = [log["action"] for log in audit_logs]
        self.assertIn("UPSERT_SUBSCRIPTION", actions)
        self.assertIn("CANCEL_SUBSCRIPTION", actions)

    def test_webhook_idempotency(self):
        """Test recording and checking duplicate webhook events."""
        event_id = "evt_test_unique_999"
        self.assertFalse(self.db.is_webhook_event_processed(event_id))

        self.db.record_webhook_event(
            event_id=event_id,
            provider="stripe",
            event_type="checkout.session.completed",
            payload='{"id": "evt_test_unique_999"}',
            status="processed",
        )

        self.assertTrue(self.db.is_webhook_event_processed(event_id))

    def test_entitlement_free_user(self):
        """Test entitlement for a standard free tier user."""
        free_user_id = 999999999
        ent = self.entitlement.get_user_entitlement(free_user_id)
        self.assertFalse(ent.is_premium)
        self.assertEqual(ent.plan, "free")
        self.assertEqual(ent.max_volume, 100)
        self.assertFalse(ent.stay_247_allowed)
        self.assertFalse(self.entitlement.can_access_feature(free_user_id, "24_7_mode"))
        self.assertFalse(self.entitlement.can_access_feature(free_user_id, "ai_maid_voice"))
        self.assertFalse(self.entitlement.can_access_feature(free_user_id, "hardware_dsp"))

    def test_payment_service_unconfigured_gateway(self):
        """Ensure payment service detects unconfigured Stripe credentials and errors safely."""
        with patch.object(config, "is_stripe_configured", return_value=False):
            with self.assertRaises(ValueError) as ctx:
                self.payment.create_checkout_session(
                    user_id=123,
                    user_tag="AnimeFan#0001",
                    plan="monthly",
                    return_base_url="https://musicmaid.example.com",
                )
            self.assertIn("Stripe is not configured", str(ctx.exception))

    @patch("music_bot.services.payment_service.stripe.checkout.Session.create")
    def test_payment_service_create_checkout_session(self, mock_session_create):
        """Test Stripe checkout session creation with correct parameters."""
        mock_session_create.return_value = MagicMock(
            id="cs_test_mock_session_123",
            url="https://checkout.stripe.com/c/pay/cs_test_mock_session_123",
        )

        with patch.object(config, "is_stripe_configured", return_value=True), \
             patch.object(config, "STRIPE_SECRET_KEY", "sk_test_mock123"):
            result = self.payment.create_checkout_session(
                user_id=456789,
                user_tag="RemLover#1234",
                plan="yearly",
                return_base_url="https://musicmaid.example.com",
            )
            self.assertEqual(result["session_id"], "cs_test_mock_session_123")
            self.assertEqual(result["url"], "https://checkout.stripe.com/c/pay/cs_test_mock_session_123")
            mock_session_create.assert_called_once()
            call_kwargs = mock_session_create.call_args[1]
            self.assertEqual(call_kwargs["client_reference_id"], "456789")
            self.assertEqual(call_kwargs["metadata"]["plan"], "yearly")

    @patch("music_bot.services.payment_service.stripe.checkout.Session.retrieve")
    def test_payment_service_verify_checkout_session(self, mock_session_retrieve):
        """Test cryptographically verifying a completed session directly against Stripe."""
        mock_session = MagicMock()
        mock_session.id = "cs_verified_123"
        mock_session.payment_status = "paid"
        mock_session.client_reference_id = "7891011"
        mock_session.customer = "cus_mock_999"
        mock_session.subscription = "sub_mock_888"
        mock_session.payment_intent = "pi_mock_777"
        mock_session.metadata = {"plan": "monthly", "user_id": "7891011"}
        mock_session_retrieve.return_value = mock_session

        with patch.object(config, "is_stripe_configured", return_value=True):
            res = self.payment.verify_checkout_session("cs_verified_123", expected_user_id=7891011)
            self.assertTrue(res["verified"])
            self.assertEqual(res["plan"], "monthly")

            # Verify subscription is now active in database
            sub = self.db.get_user_subscription(7891011)
            self.assertIsNotNone(sub)
            self.assertEqual(sub["status"], "active")
            self.assertEqual(sub["plan"], "monthly")
            self.assertEqual(sub["provider_customer_id"], "cus_mock_999")

    def test_payment_public_config_censoring(self):
        """Ensure secret keys are never leaked to public configs."""
        pub_config = config.get_payment_public_config()
        self.assertNotIn("STRIPE_SECRET_KEY", pub_config)
        self.assertNotIn("STRIPE_WEBHOOK_SECRET", pub_config)
        self.assertIn("enabled", pub_config)
        self.assertIn("plans", pub_config)
        self.assertIn("monthly", pub_config["plans"])
        self.assertIn("yearly", pub_config["plans"])


if __name__ == "__main__":
    unittest.main()
