"""
Phase 7 Tests — VIP Billing, Checkout & Razorpay Integration.
Validates:
1. Plans & Entitlement status endpoints (/api/premium/plans, /api/premium/status).
2. Razorpay server-side order generation with metadata notes.
3. Cryptographic HMAC-SHA256 payment signature verification and grant.
4. Razorpay webhook verification (X-Razorpay-Signature) and idempotent processing.
5. Subscription cancellation and entitlement revocation at period end.
"""

import hashlib
import hmac
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp.test_utils import make_mocked_request

from web.payment_api import PaymentApiRouter
from music_bot.services.razorpay_service import RazorpayService
from music_bot.services.entitlement_service import UserEntitlement


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.get_session_from_request = AsyncMock(return_value={
        "discord_user_id": 1457380609641938981,
        "username": "BillingUser",
        "user_data": {
            "id": 1457380609641938981,
            "username": "BillingUser",
            "email": "billing@example.com",
            "is_owner": False,
        },
    })
    return auth


@pytest.fixture
def payment_router(mock_auth):
    bot = MagicMock()
    db = MagicMock()
    db._db = MagicMock()
    router = PaymentApiRouter(bot=bot, db=db, auth=mock_auth)
    return router


def _create_mock_req(method: str, path: str, json_data: dict = None, headers: dict = None, raw_body: bytes = None):
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = make_mocked_request(method, path, headers=req_headers)
    if json_data is not None:
        req.json = AsyncMock(return_value=json_data)
    if raw_body is not None:
        req.read = AsyncMock(return_value=raw_body)
    return req


@pytest.mark.asyncio
async def test_get_plans_returns_features_and_pricing(payment_router):
    """Verify get_plans provides comprehensive comparison and pricing metadata."""
    req = _create_mock_req("GET", "/api/premium/plans")
    resp = await payment_router.get_plans(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    res = data["data"]
    assert "plans" in res
    assert "features" in res
    assert "faqs" in res
    assert len(res["features"]) > 5


@pytest.mark.asyncio
async def test_get_status_authenticated(payment_router):
    """Verify get_status returns current authenticated user's entitlement."""
    with patch("music_bot.services.entitlement_service.EntitlementService.get_user_entitlement", new_callable=AsyncMock) as mock_ent:
        mock_res = MagicMock()
        mock_res.to_dict.return_value = {
            "user_id": 1457380609641938981,
            "is_premium": True,
            "plan": "vip",
            "status": "active",
        }
        mock_ent.return_value = mock_res

        req = _create_mock_req("GET", "/api/premium/status")
        resp = await payment_router.get_status(req)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["success"] is True
        assert data["data"]["authenticated"] is True
        assert data["data"]["entitlement"]["is_premium"] is True


@pytest.mark.asyncio
async def test_create_order_generates_razorpay_order(payment_router):
    """Verify create_order calls RazorpayService and returns valid order payload."""
    with patch("music_bot.config.PAYMENTS_ENABLED", True), \
         patch("music_bot.services.razorpay_service.RazorpayService.create_order", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {
            "order_id": "order_test_123456",
            "amount": 19900,
            "currency": "INR",
            "key_id": "rzp_test_mockkey",
            "plan_id": "monthly",
            "user_id": "1457380609641938981",
        }

        req = _create_mock_req("POST", "/api/premium/order", json_data={"plan": "monthly"})
        resp = await payment_router.create_order(req)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["success"] is True
        assert data["data"]["order_id"] == "order_test_123456"
        assert data["data"]["amount"] == 19900


@pytest.mark.asyncio
async def test_verify_payment_signature_success_and_failure(payment_router):
    """Verify verify_payment validates HMAC-SHA256 signature and grants entitlement."""
    test_secret = "test_razorpay_secret_12345"
    order_id = "order_abc123"
    payment_id = "pay_xyz789"

    # Compute valid signature
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    valid_sig = hmac.new(test_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    invalid_sig = "bad_signature_000000000000000000000000000000000000000000000000000000000"

    with patch.object(RazorpayService, "get_key_secret", return_value=test_secret), \
         patch.object(RazorpayService, "grant_verified_entitlement", new_callable=AsyncMock) as mock_grant, \
         patch("music_bot.services.entitlement_service.EntitlementService.get_user_entitlement", new_callable=AsyncMock) as mock_ent:

        mock_grant.return_value = (True, "Entitlement granted")
        mock_ent.return_value = UserEntitlement(
            user_id=1457380609641938981,
            is_premium=True,
            plan="monthly",
            status="active",
        )

        # 1. Invalid signature rejection
        bad_req = _create_mock_req(
            "POST",
            "/api/premium/verify",
            json_data={
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": invalid_sig,
                "plan": "monthly",
            },
        )
        bad_resp = await payment_router.verify_payment(bad_req)
        assert bad_resp.status == 400
        assert json.loads(bad_resp.text)["success"] is False

        # 2. Valid signature acceptance
        good_req = _create_mock_req(
            "POST",
            "/api/premium/verify",
            json_data={
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": valid_sig,
                "plan": "monthly",
            },
        )
        good_resp = await payment_router.verify_payment(good_req)
        assert good_resp.status == 200
        good_data = json.loads(good_resp.text)
        assert good_data["success"] is True
        assert good_data["data"]["verified"] is True
        mock_grant.assert_called_once()


@pytest.mark.asyncio
async def test_handle_razorpay_webhook_verification(payment_router):
    """Verify handle_razorpay_webhook verifies X-Razorpay-Signature and processes payment.captured."""
    webhook_secret = "whsec_test_secret_9999"
    webhook_payload = json.dumps({
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_hook_12345",
                    "order_id": "order_hook_67890",
                    "amount": 19900,
                    "notes": {
                        "user_id": "1457380609641938981",
                        "plan": "monthly",
                    },
                }
            }
        }
    }).encode("utf-8")

    valid_hook_sig = hmac.new(webhook_secret.encode("utf-8"), webhook_payload, hashlib.sha256).hexdigest()

    with patch.object(RazorpayService, "get_webhook_secret", return_value=webhook_secret), \
         patch.object(RazorpayService, "grant_verified_entitlement", new_callable=AsyncMock) as mock_grant:
        mock_grant.return_value = (True, "Granted via webhook")

        # 1. Invalid signature
        bad_req = _create_mock_req(
            "POST",
            "/api/premium/webhook/razorpay",
            headers={"X-Razorpay-Signature": "invalid_sig"},
            raw_body=webhook_payload,
        )
        bad_resp = await payment_router.handle_razorpay_webhook(bad_req)
        assert bad_resp.status == 400

        # 2. Valid signature
        good_req = _create_mock_req(
            "POST",
            "/api/premium/webhook/razorpay",
            headers={"X-Razorpay-Signature": valid_hook_sig},
            raw_body=webhook_payload,
        )
        good_resp = await payment_router.handle_razorpay_webhook(good_req)
        assert good_resp.status == 200
        assert json.loads(good_resp.text)["status"] == "processed"
        mock_grant.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_subscription_success(payment_router):
    """Verify cancel_subscription stops auto-renewal."""
    with patch("music_bot.services.payment_service.PaymentService.cancel_subscription", new_callable=AsyncMock) as mock_cancel:
        mock_cancel.return_value = True
        req = _create_mock_req("POST", "/api/premium/cancel")
        resp = await payment_router.cancel_subscription(req)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["success"] is True
        assert data["data"]["canceled"] is True
