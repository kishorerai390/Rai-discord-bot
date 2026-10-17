"""
Official Razorpay Payment Gateway & Order Verification Service.
Designed for Indian individual developers and students.
Provides:
- Cryptographic HMAC-SHA256 signature verification for orders and webhooks
- Safe Sandbox / Test vs Live mode isolation
- Idempotent entitlement grants with duration extensions
- Prevention of forged client-side payment confirmations
- Zero storage of card numbers, CVVs, or bank secrets
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import aiohttp

from music_bot import config

logger = logging.getLogger("MusicMaid.Razorpay")


class RazorpayService:
    """Server-side Razorpay Order Creator, Payment Verifier, and Entitlement Manager."""

    API_BASE = "https://api.razorpay.com/v1"

    @classmethod
    def get_key_id(cls) -> str:
        return os.getenv("RAZORPAY_KEY_ID", "").strip() or getattr(config, "RAZORPAY_KEY_ID", "")

    @classmethod
    def get_key_secret(cls) -> str:
        return os.getenv("RAZORPAY_KEY_SECRET", "").strip() or getattr(config, "RAZORPAY_KEY_SECRET", "")

    @classmethod
    def get_webhook_secret(cls) -> str:
        return os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip() or getattr(config, "RAZORPAY_WEBHOOK_SECRET", "")

    @classmethod
    def is_configured(cls) -> bool:
        """True if Razorpay Key ID and Key Secret are present in server environment."""
        return bool(cls.get_key_id() and cls.get_key_secret())

    @classmethod
    def is_live_mode(cls) -> bool:
        """True only if using Razorpay live credentials (rzp_live_...)."""
        return cls.get_key_id().startswith("rzp_live_")

    @classmethod
    def get_plan_pricing(cls, plan_id: str) -> Dict[str, Any]:
        """Server-controlled plan pricing in INR."""
        plan_key = plan_id.lower().strip()
        monthly_inr = int(os.getenv("PREMIUM_MONTHLY_AMOUNT_INR", "199"))
        yearly_inr = int(os.getenv("PREMIUM_YEARLY_AMOUNT_INR", "1799"))

        if plan_key == "yearly":
            amount_inr = yearly_inr
            amount_paise = yearly_inr * 100
            name = "NyxTune / MusicMaid Premium Yearly"
            duration_days = 365
        else:
            amount_inr = monthly_inr
            amount_paise = monthly_inr * 100
            name = "NyxTune / MusicMaid Premium Monthly"
            duration_days = 30

        return {
            "plan_id": plan_key,
            "name": name,
            "currency": "INR",
            "amount_inr": amount_inr,
            "amount_paise": amount_paise,
            "duration_days": duration_days,
        }

    @classmethod
    async def create_order(
        cls,
        user_id: int,
        plan_id: str,
        user_name: str,
        user_email: Optional[str] = None,
        db: Any = None,
    ) -> Dict[str, Any]:
        """
        Creates an official server-side Razorpay Order.
        Returns: { order_id, amount, currency, key_id, plan_id, ... }
        """
        if not cls.is_configured():
            raise RuntimeError(
                "Razorpay credentials not configured. Please set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in server environment."
            )

        pricing = cls.get_plan_pricing(plan_id)
        key_id = cls.get_key_id()
        key_secret = cls.get_key_secret()

        receipt = f"rcpt_{user_id}_{int(time.time())}"
        payload = {
            "amount": pricing["amount_paise"],
            "currency": pricing["currency"],
            "receipt": receipt,
            "notes": {
                "user_id": str(user_id),
                "user_name": str(user_name),
                "plan": pricing["plan_id"],
                "platform": "MusicMaid/NyxTune",
            },
        }

        # Make server-side call to Razorpay Orders API
        auth_str = base64.b64encode(f"{key_id}:{key_secret}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                f"{cls.API_BASE}/orders",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10.0),
            ) as resp:
                if resp.status not in (200, 201):
                    err_text = await resp.text()
                    logger.error(f"[Razorpay] Order creation failed (HTTP {resp.status}): {err_text}")
                    raise RuntimeError(f"Razorpay order creation error (HTTP {resp.status}): {err_text}")

                data = await resp.json()
                order_id = data.get("id")

        logger.info(
            f"[Razorpay] Created order {order_id} for user {user_id} ({pricing['plan_id']} - ₹{pricing['amount_inr']})"
        )

        return {
            "order_id": order_id,
            "amount": pricing["amount_paise"],
            "amount_inr": pricing["amount_inr"],
            "currency": pricing["currency"],
            "key_id": key_id,
            "plan_id": pricing["plan_id"],
            "plan_name": pricing["name"],
            "user_id": str(user_id),
            "user_name": user_name,
            "user_email": user_email or "",
            "is_live_mode": cls.is_live_mode(),
        }

    @classmethod
    def verify_signature(
        cls,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> bool:
        """
        Cryptographically verifies the HMAC-SHA256 signature returned by Razorpay Checkout.
        Formula: HMAC_SHA256(order_id + "|" + payment_id, secret) == signature
        """
        secret = cls.get_key_secret()
        if not secret:
            logger.error("[Razorpay] Cannot verify signature: RAZORPAY_KEY_SECRET is missing.")
            return False

        message = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        generated_signature = hmac.new(
            secret.encode("utf-8"), message, hashlib.sha256
        ).hexdigest()

        is_valid = hmac.compare_digest(generated_signature, razorpay_signature)
        if not is_valid:
            logger.warning(
                f"[Razorpay] Signature mismatch for order {razorpay_order_id} and payment {razorpay_payment_id}!"
            )
        return is_valid

    @classmethod
    def verify_webhook_signature(cls, raw_payload: bytes, signature_header: str) -> bool:
        """
        Cryptographically verifies X-Razorpay-Signature for incoming webhooks.
        """
        webhook_secret = cls.get_webhook_secret() or cls.get_key_secret()
        if not webhook_secret:
            logger.error("[Razorpay] Cannot verify webhook: RAZORPAY_WEBHOOK_SECRET is missing.")
            return False

        expected = hmac.new(
            webhook_secret.encode("utf-8"), raw_payload, hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature_header)

    @classmethod
    async def fetch_payment_status(cls, razorpay_payment_id: str) -> Optional[Dict[str, Any]]:
        """
        Server-side lookup of payment details from Razorpay to confirm payment status is captured/authorized.
        """
        key_id = cls.get_key_id()
        key_secret = cls.get_key_secret()
        if not key_id or not key_secret:
            return None

        auth = aiohttp.BasicAuth(key_id, key_secret)
        try:
            async with aiohttp.ClientSession(auth=auth) as session:
                async with session.get(
                    f"{cls.API_BASE}/payments/{razorpay_payment_id}",
                    timeout=aiohttp.ClientTimeout(total=8.0),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    err = await resp.text()
                    logger.warning(f"[Razorpay] Payment lookup error (HTTP {resp.status}): {err}")
                    return None
        except Exception as e:
            logger.error(f"[Razorpay] Exception looking up payment {razorpay_payment_id}: {e}")
            return None

    @classmethod
    async def grant_verified_entitlement(
        cls,
        user_id: int,
        plan_id: str,
        razorpay_payment_id: str,
        razorpay_order_id: str,
        db: Any,
        amount_paise: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Idempotently grants Premium subscription and updates user entitlement records.
        """
        event_id = f"rzp_pay_{razorpay_payment_id}"
        if hasattr(db, "is_webhook_event_processed"):
            if await db.is_webhook_event_processed(event_id):
                logger.info(f"[Razorpay] Payment {razorpay_payment_id} already granted. Skipping duplicate.")
                return True, "Payment already processed."

        pricing = cls.get_plan_pricing(plan_id)
        now = datetime.now(timezone.utc)
        duration = timedelta(days=pricing["duration_days"])

        # Check existing subscription for renewal extension
        current_end_dt = now
        if hasattr(db, "get_user_subscription"):
            try:
                sub = await db.get_user_subscription(user_id)
                if sub and sub.get("status") in ("active", "trialing") and sub.get("current_period_end"):
                    existing_end = datetime.fromisoformat(sub["current_period_end"].replace("Z", "+00:00"))
                    if existing_end > now:
                        current_end_dt = existing_end
            except Exception as e:
                logger.debug(f"[Razorpay] Existing sub query notice: {e}")

        new_period_end = current_end_dt + duration

        if hasattr(db, "upsert_user_subscription"):
            await db.upsert_user_subscription(
                user_id=user_id,
                plan=pricing["plan_id"],
                status="active",
                provider="razorpay",
                provider_customer_id=f"rzp_user_{user_id}",
                provider_subscription_id=razorpay_order_id,
                payment_reference=razorpay_payment_id,
                currency="INR",
                amount=amount_paise or pricing["amount_paise"],
                current_period_start=now.isoformat(),
                current_period_end=new_period_end.isoformat(),
                cancel_at_period_end=False,
            )

        if hasattr(db, "record_webhook_event"):
            await db.record_webhook_event(
                event_id=event_id,
                provider="razorpay",
                event_type="payment.captured",
                payload_json=json.dumps({
                    "user_id": user_id,
                    "plan": pricing["plan_id"],
                    "order_id": razorpay_order_id,
                    "payment_id": razorpay_payment_id,
                    "amount": amount_paise or pricing["amount_paise"],
                    "expires_at": new_period_end.isoformat(),
                }),
                status="processed",
            )

        logger.info(
            f"[Razorpay] Successfully granted {pricing['plan_id']} entitlement to user {user_id} until {new_period_end.isoformat()}"
        )
        return True, "Premium entitlement granted successfully."
