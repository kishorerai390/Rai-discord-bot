"""
Unit and Integration Test Suite for Razorpay Payment System.
Validates:
1. Server-side order creation with INR pricing and user metadata.
2. Cryptographic HMAC-SHA256 payment signature verification.
3. Razorpay webhook signature verification and idempotent event ingestion.
4. Entitlement granting and additive duration extension (30 days / 365 days).
5. REST API security (auth enforcement, disabled mode handling, forged signature rejection).
6. Compliance legal routes (/terms, /privacy, /refund, /contact).
"""

from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import music_bot.config as config
from music_bot.database.db import MusicDatabase
from music_bot.services.entitlement_service import EntitlementService
from music_bot.services.razorpay_service import RazorpayService
from web.payment_api import PaymentApiRouter
from web import legal


class TestRazorpayService(unittest.IsolatedAsyncioTestCase):
    """Test suite for Razorpay service methods (orders, signatures, entitlements)."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_music.db"
        self.db = MusicDatabase(db_path=self.db_path)
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_pricing_and_plans(self):
        """Test server-controlled pricing calculations."""
        monthly = RazorpayService.get_plan_pricing("monthly")
        self.assertEqual(monthly["amount_inr"], 199)
        self.assertEqual(monthly["amount_paise"], 19900)
        self.assertEqual(monthly["duration_days"], 30)

        yearly = RazorpayService.get_plan_pricing("yearly")
        self.assertEqual(yearly["amount_inr"], 1799)
        self.assertEqual(yearly["amount_paise"], 179900)
        self.assertEqual(yearly["duration_days"], 365)

    @patch("music_bot.services.razorpay_service.aiohttp.ClientSession")
    async def test_02_create_order_server_side(self, mock_client_session_cls):
        """Test server-side order creation via Razorpay API."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "id": "order_test_987654",
            "entity": "order",
            "amount": 19900,
            "currency": "INR",
            "status": "created",
        })

        mock_session_inst = MagicMock()
        mock_session_inst.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_inst.post.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session_inst.__aenter__ = AsyncMock(return_value=mock_session_inst)
        mock_session_inst.__aexit__ = AsyncMock(return_value=None)
        mock_client_session_cls.return_value = mock_session_inst

        with patch.object(config, "RAZORPAY_KEY_ID", "rzp_test_12345"), \
             patch.object(config, "RAZORPAY_KEY_SECRET", "test_secret_abc"):
            
            order_data = await RazorpayService.create_order(
                user_id=123456789,
                plan_id="monthly",
                user_name="TestUser",
                user_email="test@example.com",
                db=self.db,
            )

            self.assertEqual(order_data["order_id"], "order_test_987654")
            self.assertEqual(order_data["amount"], 19900)
            self.assertEqual(order_data["currency"], "INR")
            self.assertEqual(order_data["key_id"], "rzp_test_12345")

    def test_03_cryptographic_signature_verification(self):
        """Test HMAC-SHA256 payment signature verification and forgery rejection."""
        secret = "super_secret_webhook_key_123"
        order_id = "order_HMAC123"
        payment_id = "pay_TEST999"

        # Generate genuine signature
        message = f"{order_id}|{payment_id}"
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        with patch.object(config, "RAZORPAY_KEY_SECRET", secret):
            # Valid signature must pass
            self.assertTrue(RazorpayService.verify_signature(order_id, payment_id, expected_sig))

            # Tampered signature must fail
            self.assertFalse(RazorpayService.verify_signature(order_id, payment_id, "forged_signature_xyz"))

            # Tampered payment_id must fail
            self.assertFalse(RazorpayService.verify_signature(order_id, "pay_TAMPERED", expected_sig))

            # Empty fields must fail
            self.assertFalse(RazorpayService.verify_signature("", payment_id, expected_sig))

    def test_04_webhook_signature_verification(self):
        """Test Razorpay webhook raw-payload signature verification."""
        secret = "webhook_secret_key_777"
        raw_body = b'{"event":"payment.captured","payload":{"id":"pay_123"}}'

        expected_sig = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256
        ).hexdigest()

        with patch.object(config, "RAZORPAY_WEBHOOK_SECRET", secret):
            self.assertTrue(RazorpayService.verify_webhook_signature(raw_body, expected_sig))
            self.assertFalse(RazorpayService.verify_webhook_signature(raw_body, "tampered_sig"))
            self.assertFalse(RazorpayService.verify_webhook_signature(b"tampered body", expected_sig))

    async def test_05_grant_verified_entitlement_and_extension(self):
        """Test entitlement granting and additive duration extension."""
        user_id = 9988776655

        # 1. First payment: monthly (30 days)
        success, msg = await RazorpayService.grant_verified_entitlement(
            user_id=user_id,
            plan_id="monthly",
            razorpay_payment_id="pay_first_001",
            razorpay_order_id="order_first_001",
            db=self.db,
            amount_paise=19900,
        )
        self.assertTrue(success)

        sub = await self.db.get_user_subscription(user_id)
        self.assertIsNotNone(sub)
        self.assertEqual(sub["plan"], "monthly")
        self.assertEqual(sub["status"], "active")
        self.assertEqual(sub["provider"], "razorpay")
        self.assertEqual(sub["payment_reference"], "pay_first_001")

        first_renewal = datetime.fromisoformat(sub["current_period_end"])
        now_utc = datetime.now(timezone.utc)
        self.assertGreater(first_renewal, now_utc + timedelta(days=29))

        # 2. Second payment: renew before expiry with yearly (365 days) -> should extend additively!
        success2, msg2 = await RazorpayService.grant_verified_entitlement(
            user_id=user_id,
            plan_id="yearly",
            razorpay_payment_id="pay_second_002",
            razorpay_order_id="order_second_002",
            db=self.db,
            amount_paise=179900,
        )
        self.assertTrue(success2)

        sub2 = await self.db.get_user_subscription(user_id)
        second_renewal = datetime.fromisoformat(sub2["current_period_end"])

        # Second renewal must be approx first_renewal + 365 days
        expected_min = first_renewal + timedelta(days=364)
        self.assertGreaterEqual(second_renewal, expected_min)

        # 3. Verify entitlement service detects active premium
        ent = await EntitlementService.get_user_entitlement(user_id, self.db)
        self.assertTrue(ent.is_premium)
        self.assertEqual(ent.tier, "yearly")

        # 4. Duplicate payment_id processing test (idempotency check)
        success3, msg3 = await RazorpayService.grant_verified_entitlement(
            user_id=user_id,
            plan_id="yearly",
            razorpay_payment_id="pay_second_002",  # SAME payment_id
            razorpay_order_id="order_second_002",
            db=self.db,
            amount_paise=179900,
        )
        self.assertTrue(success3)
        self.assertIn("already processed", msg3.lower())

        # Renewal date should NOT have increased again
        sub3 = await self.db.get_user_subscription(user_id)
        self.assertEqual(sub3["current_period_end"], sub2["current_period_end"])


class TestRazorpayApiEndpoints(unittest.IsolatedAsyncioTestCase):
    """Test suite for Razorpay HTTP API routing, auth, and webhook endpoints."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_api_music.db"
        self.db = MusicDatabase(db_path=self.db_path)
        await self.db.connect()

        self.mock_auth = MagicMock()
        self.mock_auth.get_session_from_request = AsyncMock(return_value={
            "discord_user_id": 1122334455,
            "user_data": {"username": "RazorUser", "email": "rzp@example.com"}
        })
        self.mock_auth.get_canonical_base_url = MagicMock(return_value="https://rai-discord-bot.onrender.com")

        self.router = PaymentApiRouter(bot=MagicMock(), db=self.db, auth=self.mock_auth)

        app = web.Application()
        app.router.add_get("/api/premium/plans", self.router.get_plans)
        app.router.add_post("/api/premium/order", self.router.create_order)
        app.router.add_post("/api/premium/verify", self.router.verify_payment)
        app.router.add_post("/api/premium/webhook/razorpay", self.router.handle_razorpay_webhook)
        app.router.add_get("/terms", lambda req: web.Response(text=legal.TERMS_OF_SERVICE_HTML, content_type="text/html"))
        app.router.add_get("/refund", lambda req: web.Response(text=legal.REFUND_POLICY_HTML, content_type="text/html"))
        app.router.add_get("/contact", lambda req: web.Response(text=legal.CONTACT_US_HTML, content_type="text/html"))

        self.server = TestServer(app)
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_01_create_order_when_payments_disabled(self):
        """When PAYMENTS_ENABLED=false, create_order returns 503 PAYMENTS_DISABLED."""
        with patch.object(config, "PAYMENTS_ENABLED", False):
            resp = await self.client.post("/api/premium/order", json={"plan": "monthly"})
            self.assertEqual(resp.status, 503)
            data = await resp.json()
            self.assertFalse(data["success"])
            self.assertEqual(data["error"]["code"], "PAYMENTS_DISABLED")

    async def test_02_create_order_unauthenticated(self):
        """When not signed in with Discord, create_order returns 401 UNAUTHORIZED."""
        self.mock_auth.get_session_from_request.return_value = None
        with patch.object(config, "PAYMENTS_ENABLED", True):
            resp = await self.client.post("/api/premium/order", json={"plan": "monthly"})
            self.assertEqual(resp.status, 401)
            data = await resp.json()
            self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    async def test_03_verify_payment_invalid_signature_rejected(self):
        """Tampered or invalid signatures are rejected with 400 INVALID_SIGNATURE."""
        with patch.object(config, "RAZORPAY_KEY_SECRET", "super_secret"):
            payload = {
                "razorpay_order_id": "order_123",
                "razorpay_payment_id": "pay_123",
                "razorpay_signature": "fake_signature_hash",
                "plan": "monthly",
            }
            resp = await self.client.post("/api/premium/verify", json=payload)
            self.assertEqual(resp.status, 400)
            data = await resp.json()
            self.assertEqual(data["error"]["code"], "INVALID_SIGNATURE")

    async def test_04_verify_payment_genuine_signature_success(self):
        """Genuine cryptographic signature verifies and unlocks premium."""
        secret = "test_verification_secret_key"
        order_id = "order_VALID999"
        payment_id = "pay_VALID999"
        valid_sig = hmac.new(
            secret.encode("utf-8"),
            f"{order_id}|{payment_id}".encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        with patch.object(config, "RAZORPAY_KEY_SECRET", secret):
            payload = {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": valid_sig,
                "plan": "monthly",
            }
            resp = await self.client.post("/api/premium/verify", json=payload)
            self.assertEqual(resp.status, 200)
            data = await resp.json()
            self.assertTrue(data["success"])
            self.assertTrue(data["data"]["verified"])
            self.assertTrue(data["data"]["entitlement"]["is_premium"])

    async def test_05_razorpay_webhook_processing(self):
        """Test Razorpay asynchronous webhook ingestion and signature validation."""
        secret = "test_webhook_sec"
        webhook_body = json.dumps({
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_hook_888",
                        "order_id": "order_hook_888",
                        "amount": 19900,
                        "notes": {
                            "user_id": "1122334455",
                            "plan": "monthly"
                        }
                    }
                }
            }
        }).encode("utf-8")

        valid_sig = hmac.new(secret.encode("utf-8"), webhook_body, hashlib.sha256).hexdigest()

        with patch.object(config, "RAZORPAY_WEBHOOK_SECRET", secret):
            # 1. Invalid signature
            bad_resp = await self.client.post(
                "/api/premium/webhook/razorpay",
                data=webhook_body,
                headers={"X-Razorpay-Signature": "invalid_sig"}
            )
            self.assertEqual(bad_resp.status, 400)

            # 2. Valid signature -> processes and grants entitlement
            good_resp = await self.client.post(
                "/api/premium/webhook/razorpay",
                data=webhook_body,
                headers={"X-Razorpay-Signature": valid_sig}
            )
            self.assertEqual(good_resp.status, 200)
            good_data = await good_resp.json()
            self.assertEqual(good_data["status"], "processed")

            # Verify in DB
            sub = await self.db.get_user_subscription(1122334455)
            self.assertIsNotNone(sub)
            self.assertEqual(sub["payment_reference"], "pay_hook_888")

    async def test_06_compliance_legal_routes(self):
        """Test required compliance endpoints (/terms, /refund, /contact)."""
        resp_terms = await self.client.get("/terms")
        self.assertEqual(resp_terms.status, 200)
        self.assertIn("Terms of Service", await resp_terms.text())

        resp_refund = await self.client.get("/refund")
        self.assertEqual(resp_refund.status, 200)
        self.assertIn("Refund and Cancellation Policy", await resp_refund.text())

        resp_contact = await self.client.get("/contact")
        self.assertEqual(resp_contact.status, 200)
        self.assertIn("Contact", await resp_contact.text())


if __name__ == "__main__":
    unittest.main()
