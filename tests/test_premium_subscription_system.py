"""
Test suite for MusicMaid Premium Subscription & Purchase System.
Tests database persistence, entitlement checks, payment session creation,
session verification against Stripe, idempotent webhook handlers, and public config masking.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import pytest
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import stripe

import music_bot.config as config
from music_bot.database.db import MusicDatabase
from music_bot.services.entitlement_service import EntitlementService
from music_bot.services.payment_service import PaymentService


@pytest.fixture
async def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_music.db"
    db = MusicDatabase(db_path=db_path)
    await db.connect()
    yield db
    await db.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_database_subscription_lifecycle(temp_db):
    """Test creating, querying, updating, and cancelling user subscriptions."""
    user_id = 1234567890

    # 1. Initially no subscription
    sub = await temp_db.get_user_subscription(user_id)
    assert sub is None
    is_prem = await temp_db.is_premium(user_id=user_id)
    assert is_prem is False

    # 2. Upsert active subscription
    now_iso = datetime.now(timezone.utc).isoformat()
    renewal_iso = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    await temp_db.upsert_user_subscription(
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

    sub = await temp_db.get_user_subscription(user_id)
    assert sub is not None
    assert sub["plan"] == "monthly"
    assert sub["status"] == "active"
    assert sub["provider_customer_id"] == "cus_test_abc123"
    assert sub["provider_subscription_id"] == "sub_test_abc123"

    is_prem = await temp_db.is_premium(user_id=user_id)
    assert is_prem is True

    # 3. Cancel subscription
    success = await temp_db.cancel_user_subscription(user_id, reason="User cancelled auto-renewal")
    assert success is True

    sub_after_cancel = await temp_db.get_user_subscription(user_id)
    assert sub_after_cancel["status"] == "cancelled"
    assert sub_after_cancel["cancelled_at"] is not None

    # 4. Audit logs recorded
    logs = await temp_db.get_subscription_audit_logs(user_id)
    assert len(logs) >= 2
    actions = [log["action"] for log in logs]
    assert "subscription_upserted" in actions
    assert "subscription_cancelled" in actions


@pytest.mark.asyncio
async def test_webhook_idempotency(temp_db):
    """Test idempotent tracking of Stripe webhook events."""
    event_id = "evt_test_unique_456"

    # Initially unprocessed
    processed = await temp_db.is_webhook_event_processed(event_id)
    assert processed is False

    # Record event
    await temp_db.record_webhook_event(
        event_id=event_id,
        provider="stripe",
        event_type="checkout.session.completed",
        payload='{"id": "evt_test_unique_456"}',
        status="processed",
    )

    # Now processed
    processed_again = await temp_db.is_webhook_event_processed(event_id)
    assert processed_again is True


@pytest.mark.asyncio
async def test_entitlement_service_free_and_premium(temp_db):
    """Test entitlement resolution for free, active premium, and expired users."""
    free_user_id = 999900001
    active_user_id = 999900002
    expired_user_id = 999900003

    # Free user
    ent_free = await EntitlementService.get_user_entitlement(free_user_id, temp_db)
    assert ent_free.is_premium is False
    assert ent_free.plan == "free"
    assert ent_free.perks["boosted_volume"] is False
    assert ent_free.perks["twenty_four_seven"] is False
    assert await EntitlementService.can_access_feature(free_user_id, "boosted_volume", temp_db) is False

    # Active premium user
    now_iso = datetime.now(timezone.utc).isoformat()
    future_iso = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    await temp_db.upsert_user_subscription(
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

    ent_prem = await EntitlementService.get_user_entitlement(active_user_id, temp_db)
    assert ent_prem.is_premium is True
    assert ent_prem.plan == "yearly"
    assert ent_prem.perks["boosted_volume"] is True
    assert ent_prem.perks["twenty_four_seven"] is True
    assert ent_prem.perks["maid_voice_dj"] is True
    assert await EntitlementService.can_access_feature(active_user_id, "twenty_four_seven", temp_db) is True

    # Expired subscription
    past_iso = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    past_start = (datetime.now(timezone.utc) - timedelta(days=32)).isoformat()
    await temp_db.upsert_user_subscription(
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

    ent_exp = await EntitlementService.get_user_entitlement(expired_user_id, temp_db)
    assert ent_exp.is_premium is False
    assert ent_exp.status == "expired"


@pytest.mark.asyncio
async def test_payment_service_unconfigured_guard():
    """Verify payment service throws clear error when Stripe is unconfigured."""
    with patch.object(config, "is_stripe_configured", return_value=False):
        with pytest.raises(RuntimeError) as exc_info:
            await PaymentService.create_checkout_session(
                user_id=123,
                user_email="test@example.com",
                user_name="AnimeHero",
                plan_id="monthly",
                success_url="https://musicmaid.com/premium/success",
                cancel_url="https://musicmaid.com/premium/cancel",
            )
        assert "Payment gateway is not configured" in str(exc_info.value)


@pytest.mark.asyncio
async def test_payment_service_create_session(temp_db):
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
            db=temp_db,
        )

        assert res["session_id"] == "cs_test_session_xyz"
        assert res["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_session_xyz"
        mock_create.assert_called_once()
        kwargs = mock_create.call_args[1]
        assert kwargs["client_reference_id"] == "777888"
        assert kwargs["customer_email"] == "user@discord.gg"
        assert kwargs["metadata"]["plan"] == "monthly"


@pytest.mark.asyncio
async def test_payment_service_verify_session(temp_db):
    """Verify cryptographically checking completed Stripe session and activating subscription."""
    mock_session = MagicMock()
    mock_session.id = "cs_verified_777"
    mock_session.payment_status = "paid"
    mock_session.client_reference_id = "5551234"
    mock_session.customer = "cus_mock_888"
    mock_session.subscription = "sub_mock_999"
    mock_session.payment_intent = "pi_mock_000"
    mock_session.metadata = {"plan": "yearly", "user_id": "5551234"}

    with patch.object(config, "is_stripe_configured", return_value=True), \
         patch("music_bot.services.payment_service.stripe.checkout.Session.retrieve", return_value=mock_session):

        res = await PaymentService.verify_checkout_session(
            session_id="cs_verified_777",
            expected_user_id=5551234,
            db=temp_db,
        )

        assert res["verified"] is True
        assert res["plan"] == "yearly"
        assert res["user_id"] == 5551234

        # Check DB updated
        sub = await temp_db.get_user_subscription(5551234)
        assert sub is not None
        assert sub["status"] == "active"
        assert sub["plan"] == "yearly"
        assert sub["provider_customer_id"] == "cus_mock_888"


@pytest.mark.asyncio
async def test_payment_service_webhook_idempotency_and_event_handling(temp_db):
    """Verify webhook processing for checkout.session.completed and subscription deletion."""
    event_payload = {
        "id": "evt_webhook_live_123",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_webhook_session_999",
                "payment_status": "paid",
                "client_reference_id": "8882221",
                "customer": "cus_wh_1",
                "subscription": "sub_wh_1",
                "metadata": {"plan": "monthly", "user_id": "8882221"},
            }
        },
    }

    mock_event = MagicMock()
    mock_event.id = "evt_webhook_live_123"
    mock_event.type = "checkout.session.completed"
    mock_event.data.object = MagicMock(
        id="cs_webhook_session_999",
        payment_status="paid",
        client_reference_id="8882221",
        customer="cus_wh_1",
        subscription="sub_wh_1",
        metadata={"plan": "monthly", "user_id": "8882221"},
    )
    mock_event.to_dict.return_value = event_payload

    with patch.object(config, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret"), \
         patch("music_bot.services.payment_service.stripe.Webhook.construct_event", return_value=mock_event):

        # First delivery: processes successfully
        res1 = await PaymentService.verify_and_process_webhook(
            payload_bytes=b'{"test": 1}',
            sig_header="t=123,v1=mock_signature",
            db=temp_db,
        )
        assert res1["success"] is True
        assert res1["event_type"] == "checkout.session.completed"

        # Check DB was populated
        sub = await temp_db.get_user_subscription(8882221)
        assert sub is not None
        assert sub["status"] == "active"
        assert sub["plan"] == "monthly"

        # Second delivery (duplicate): skipped idempotently
        res2 = await PaymentService.verify_and_process_webhook(
            payload_bytes=b'{"test": 1}',
            sig_header="t=123,v1=mock_signature",
            db=temp_db,
        )
        assert res2["success"] is True
        assert res2.get("duplicate") is True


def test_payment_public_config_security():
    """Ensure sensitive Stripe keys are NEVER exposed in public config."""
    pub = config.get_payment_public_config()
    assert "STRIPE_SECRET_KEY" not in pub
    assert "STRIPE_WEBHOOK_SECRET" not in pub
    assert "enabled" in pub
    assert "plans" in pub
    assert "monthly" in pub["plans"]
    assert "yearly" in pub["plans"]
    assert "amount_formatted" in pub["plans"]["monthly"]
