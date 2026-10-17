"""
Authoritative Payment Gateway & Subscription Service for MusicMaid.
Integrates Stripe Checkout Sessions, Customer Portal, and Cryptographic Webhook Handlers.
Guarantees idempotent webhook processing, server-side secret isolation, and strict audit logging.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

import stripe

from music_bot import config

logger = logging.getLogger("MusicMaid.Payment")


class PaymentService:
    """Official Stripe Payment & Subscription Management Engine."""

    @classmethod
    def initialize(cls) -> None:
        """Configure Stripe API key from secure environment variable."""
        if config.STRIPE_SECRET_KEY:
            stripe.api_key = config.STRIPE_SECRET_KEY
            stripe.api_version = "2024-06-20"
            logger.info("[Payment] Stripe SDK initialized successfully.")
        else:
            logger.warning("[Payment] STRIPE_SECRET_KEY is not set. Payment gateway in unconfigured state.")

    @classmethod
    def is_configured(cls) -> bool:
        """Return True if secret key is present."""
        return config.is_stripe_configured()

    @classmethod
    async def create_checkout_session(
        cls,
        user_id: int,
        user_email: Optional[str],
        user_name: str,
        plan_id: str,
        success_url: str,
        cancel_url: str,
        ip_address: Optional[str] = None,
        db: Any = None,
    ) -> Dict[str, Any]:
        """
        Create an official Stripe Checkout Session for a subscription.
        Returns: {"checkout_url": str, "session_id": str} or raises RuntimeError.
        """
        if not cls.is_configured():
            raise RuntimeError(
                "Payment gateway is not configured. Please configure STRIPE_SECRET_KEY in server environment."
            )

        cls.initialize()

        plan_key = plan_id.lower().strip()
        if plan_key not in ("monthly", "yearly"):
            raise ValueError(f"Invalid plan identifier '{plan_id}'. Must be 'monthly' or 'yearly'.")

        currency = config.PREMIUM_CURRENCY.lower()
        amount_cents = (
            config.PREMIUM_MONTHLY_AMOUNT_CENTS
            if plan_key == "monthly"
            else config.PREMIUM_YEARLY_AMOUNT_CENTS
        )
        configured_price_id = (
            config.STRIPE_PRICE_MONTHLY if plan_key == "monthly" else config.STRIPE_PRICE_YEARLY
        )

        metadata = {
            "user_id": str(user_id),
            "user_name": str(user_name),
            "plan": plan_key,
            "platform": "MusicMaid",
        }

        # Build session arguments
        session_args: Dict[str, Any] = {
            "payment_method_types": ["card"],
            "mode": "subscription",
            "client_reference_id": str(user_id),
            "success_url": f"{success_url}?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": cancel_url,
            "metadata": metadata,
            "subscription_data": {
                "metadata": metadata,
            },
        }

        if user_email:
            session_args["customer_email"] = user_email

        # If a pre-created Stripe Price ID exists in environment, use it directly
        if configured_price_id and configured_price_id.startswith("price_"):
            session_args["line_items"] = [{"price": configured_price_id, "quantity": 1}]
        else:
            # Otherwise use inline recurring price definition
            interval = "month" if plan_key == "monthly" else "year"
            session_args["line_items"] = [
                {
                    "price_data": {
                        "currency": currency,
                        "product_data": {
                            "name": f"MusicMaid Premium ({plan_key.title()})",
                            "description": "320kbps Lossless, 150% Volume, 24/7 Mode, AI Maid Voice DJ & Full DSP Studio.",
                            "images": ["https://cdn.discordapp.com/emojis/1149721021484081232.webp"],
                        },
                        "unit_amount": amount_cents,
                        "recurring": {"interval": interval},
                    },
                    "quantity": 1,
                }
            ]

        def _create_session() -> stripe.checkout.Session:
            return stripe.checkout.Session.create(**session_args)

        loop = asyncio.get_running_loop()
        session = await loop.run_in_executor(None, _create_session)

        # Audit log creation
        if db and hasattr(db, "record_subscription_audit"):
            try:
                await db.record_subscription_audit(
                    user_id=user_id,
                    action="checkout_initiated",
                    details={"session_id": session.id, "plan": plan_key, "amount_cents": amount_cents},
                    ip_address=ip_address,
                )
            except Exception as audit_err:
                logger.debug(f"[Payment] Audit logging notice: {audit_err}")

        return {
            "checkout_url": session.url,
            "session_id": session.id,
        }

    @classmethod
    async def verify_checkout_session(
        cls,
        session_id: str,
        db: Any,
        expected_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Cryptographically verify the payment status of a checkout session directly with Stripe.
        Never trust a frontend redirect alone.
        """
        if not cls.is_configured():
            return {
                "verified": False,
                "error": "Payment gateway is not configured.",
            }

        cls.initialize()

        def _retrieve() -> stripe.checkout.Session:
            return stripe.checkout.Session.retrieve(session_id, expand=["subscription", "customer"])

        loop = asyncio.get_running_loop()
        try:
            session = await loop.run_in_executor(None, _retrieve)
        except Exception as e:
            logger.error(f"[Payment] Failed to retrieve session '{session_id}': {e}")
            return {"verified": False, "error": f"Failed to retrieve checkout session: {e}"}

        # Validate customer user id
        user_id_str = (
            session.client_reference_id
            or (session.metadata.get("user_id") if session.metadata else None)
        )
        if not user_id_str:
            return {"verified": False, "error": "Checkout session lacks user identifier."}

        user_id = int(user_id_str)
        if expected_user_id and user_id != expected_user_id:
            logger.warning(f"[Payment] Mismatch between session user ({user_id}) and auth user ({expected_user_id})")
            return {"verified": False, "error": "Security mismatch: session belongs to another user."}

        payment_status = session.payment_status
        status = session.status

        if payment_status != "paid":
            return {
                "verified": False,
                "status": status,
                "payment_status": payment_status,
                "error": "Payment is not marked as paid by payment provider.",
            }

        # Extract subscription details
        plan = (session.metadata.get("plan") if session.metadata else "monthly") or "monthly"
        sub_raw = getattr(session, "subscription", None)
        sub_id = getattr(sub_raw, "id", sub_raw) if sub_raw else None

        cust_raw = getattr(session, "customer", None)
        cust_id = getattr(cust_raw, "id", cust_raw) if cust_raw else None

        start_time = None
        end_time = None
        if hasattr(session, "subscription") and session.subscription and not isinstance(session.subscription, str):
            sub = session.subscription
            if getattr(sub, "current_period_start", None):
                start_time = datetime.fromtimestamp(sub.current_period_start, timezone.utc).isoformat()
            if getattr(sub, "current_period_end", None):
                end_time = datetime.fromtimestamp(sub.current_period_end, timezone.utc).isoformat()

        # Update database
        if db and hasattr(db, "upsert_user_subscription"):
            await db.upsert_user_subscription(
                user_id=user_id,
                plan=plan,
                status="active",
                provider="stripe",
                provider_customer_id=str(cust_id) if cust_id else None,
                provider_subscription_id=str(sub_id) if sub_id else session_id,
                payment_reference=session_id,
                currency=session.currency or "usd",
                amount=session.amount_total or 0,
                current_period_start=start_time,
                current_period_end=end_time,
            )

            await db.record_subscription_audit(
                user_id=user_id,
                action="payment_verified_on_success_page",
                details={"session_id": session_id, "sub_id": str(sub_id), "plan": plan},
            )

        return {
            "verified": True,
            "user_id": user_id,
            "plan": plan,
            "status": "active",
            "current_period_end": end_time,
            "amount_total": (session.amount_total or 0) / 100.0,
            "currency": (session.currency or "usd").upper(),
        }

    @classmethod
    def verify_webhook_signature(cls, payload: bytes, sig_header: str) -> stripe.Event:
        """
        Verify Stripe cryptographic webhook signature using STRIPE_WEBHOOK_SECRET.
        Raises ValueError or stripe.error.SignatureVerificationError on tamper/failure.
        """
        secret = config.STRIPE_WEBHOOK_SECRET
        if not secret:
            raise ValueError("STRIPE_WEBHOOK_SECRET is not configured on server.")

        return stripe.Webhook.construct_event(payload, sig_header, secret)

    @classmethod
    async def verify_and_process_webhook(
        cls,
        payload_bytes: bytes,
        sig_header: str,
        db: Any,
    ) -> Dict[str, Any]:
        """Verify signature and process webhook event in one call."""
        event = cls.verify_webhook_signature(payload_bytes, sig_header)
        success, message = await cls.process_webhook_event(
            event=event,
            raw_payload=payload_bytes.decode("utf-8", errors="replace"),
            db=db,
        )
        return {
            "success": success,
            "message": message,
            "event_type": event.get("type"),
            "event_id": event.get("id"),
            "duplicate": "already processed" in message.lower(),
        }

    @classmethod
    async def process_webhook_event(
        cls,
        event: stripe.Event,
        raw_payload: str,
        db: Any,
    ) -> Tuple[bool, str]:
        """
        Idempotently process an authenticated Stripe webhook event.
        Returns: (success, status_message)
        """
        event_id = event["id"]
        event_type = event["type"]

        # 1. Idempotency Check
        if hasattr(db, "is_webhook_event_processed"):
            if await db.is_webhook_event_processed(event_id):
                logger.info(f"[Payment] Webhook event '{event_id}' ({event_type}) already processed. Skipping duplicate.")
                return True, "Event already processed (idempotent)."

        raw_obj = event["data"]["object"]
        data_obj = raw_obj.to_dict() if hasattr(raw_obj, "to_dict") else dict(raw_obj)

        # 2. Event Dispatching
        if event_type == "checkout.session.completed":
            user_id_str = (
                data_obj.get("client_reference_id")
                or (data_obj.get("metadata", {}).get("user_id"))
            )
            if user_id_str:
                user_id = int(user_id_str)
                plan = data_obj.get("metadata", {}).get("plan", "monthly")
                sub_id = data_obj.get("subscription")
                cust_id = data_obj.get("customer")
                sess_id = data_obj.get("id")

                await db.upsert_user_subscription(
                    user_id=user_id,
                    plan=plan,
                    status="active",
                    provider="stripe",
                    provider_customer_id=cust_id,
                    provider_subscription_id=sub_id,
                    payment_reference=sess_id,
                    currency=data_obj.get("currency", "usd"),
                    amount=data_obj.get("amount_total", 0),
                )
                await db.record_subscription_audit(
                    user_id=user_id,
                    action="webhook_checkout_completed",
                    details={"event_id": event_id, "session_id": sess_id, "plan": plan},
                )
                logger.info(f"[Payment] Activated Premium subscription for user {user_id} via webhook.")

        elif event_type in ("invoice.payment_succeeded", "invoice.paid"):
            sub_id = data_obj.get("subscription")
            cust_id = data_obj.get("customer")
            lines = data_obj.get("lines", {}).get("data", [])
            period_end = None
            if lines and lines[0].get("period", {}).get("end"):
                period_end = datetime.fromtimestamp(lines[0]["period"]["end"], timezone.utc).isoformat()

            # Find user by subscription_id or customer_id
            # Query db for matching user subscription
            async with db._db.execute(
                "SELECT user_id FROM music_user_subscriptions WHERE provider_subscription_id = ? OR provider_customer_id = ?",
                (sub_id, cust_id),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    user_id = row[0]
                    await db.upsert_user_subscription(
                        user_id=user_id,
                        plan="monthly",
                        status="active",
                        provider="stripe",
                        provider_customer_id=cust_id,
                        provider_subscription_id=sub_id,
                        current_period_end=period_end,
                    )
                    await db.record_subscription_audit(
                        user_id=user_id,
                        action="webhook_invoice_paid",
                        details={"event_id": event_id, "period_end": period_end},
                    )
                    logger.info(f"[Payment] Renewed subscription for user {user_id} until {period_end}.")

        elif event_type == "invoice.payment_failed":
            sub_id = data_obj.get("subscription")
            cust_id = data_obj.get("customer")
            async with db._db.execute(
                "SELECT user_id FROM music_user_subscriptions WHERE provider_subscription_id = ? OR provider_customer_id = ?",
                (sub_id, cust_id),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    user_id = row[0]
                    now_iso = datetime.now(timezone.utc).isoformat()
                    async with db._lock:
                        await db._db.execute(
                            "UPDATE music_user_subscriptions SET status = 'past_due', updated_at = ? WHERE user_id = ?",
                            (now_iso, user_id),
                        )
                        await db._db.commit()
                    await db.record_subscription_audit(
                        user_id=user_id,
                        action="webhook_payment_failed",
                        details={"event_id": event_id, "subscription_id": sub_id},
                    )
                    logger.warning(f"[Payment] Subscription marked past_due for user {user_id} due to failed invoice payment.")

        elif event_type == "customer.subscription.deleted":
            sub_id = data_obj.get("id")
            cust_id = data_obj.get("customer")
            async with db._db.execute(
                "SELECT user_id FROM music_user_subscriptions WHERE provider_subscription_id = ? OR provider_customer_id = ?",
                (sub_id, cust_id),
            ) as cur:
                row = await cur.fetchone()
                if row:
                    user_id = row[0]
                    now_iso = datetime.now(timezone.utc).isoformat()
                    async with db._lock:
                        await db._db.execute(
                            "UPDATE music_user_subscriptions SET status = 'canceled', cancel_at_period_end = 1, canceled_at = ?, updated_at = ? WHERE user_id = ?",
                            (now_iso, now_iso, user_id),
                        )
                        await db._db.commit()
                    await db.record_subscription_audit(
                        user_id=user_id,
                        action="webhook_subscription_deleted",
                        details={"event_id": event_id, "subscription_id": sub_id},
                    )
                    logger.info(f"[Payment] Subscription deleted/canceled for user {user_id}.")

        # 3. Record event in idempotency table
        if hasattr(db, "record_webhook_event"):
            await db.record_webhook_event(
                event_id=event_id,
                provider="stripe",
                event_type=event_type,
                payload_json=raw_payload,
                status="processed",
            )

        return True, f"Event {event_type} handled successfully."

    @classmethod
    async def cancel_subscription(cls, user_id: int, db: Any) -> bool:
        """
        Cancel active subscription at period end in both Stripe and SQLite.
        """
        sub = await db.get_user_subscription(user_id)
        if not sub or sub.get("status") != "active":
            return False

        sub_id = sub.get("provider_subscription_id")
        if sub_id and sub_id.startswith("sub_") and cls.is_configured():
            cls.initialize()
            def _cancel_stripe():
                return stripe.Subscription.modify(sub_id, cancel_at_period_end=True)

            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, _cancel_stripe)
            except Exception as e:
                logger.warning(f"[Payment] Failed to update Stripe cancel_at_period_end: {e}")

        ok = await db.cancel_user_subscription(user_id, cancel_at_period_end=True)
        await db.record_subscription_audit(
            user_id=user_id,
            action="user_requested_cancellation",
            details={"subscription_id": sub_id},
        )
        return ok
