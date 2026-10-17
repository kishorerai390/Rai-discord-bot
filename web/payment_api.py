"""
REST API Router for MusicMaid Premium Subscription & Payment System.
Handles plan discovery, authenticated checkout creation, payment verification,
subscription cancellation, and cryptographic Stripe webhook ingestion.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
import urllib.parse

from aiohttp import web
import stripe

from music_bot import config
from music_bot.services.payment_service import PaymentService
from music_bot.services.razorpay_service import RazorpayService
from music_bot.services.entitlement_service import EntitlementService

logger = logging.getLogger("MusicMaid.PaymentAPI")


def json_success(data: Any = None, message: str = "OK", status: int = 200) -> web.Response:
    return web.json_response({"success": True, "message": message, "data": data}, status=status)


def json_error(message: str, code: str = "ERROR", status: int = 400) -> web.Response:
    return web.json_response({"success": False, "error": {"code": code, "message": message}}, status=status)


class PaymentApiRouter:
    """REST endpoints for Premium subscription management and Stripe payments."""

    def __init__(self, bot: Any, db: Any, auth: Any):
        self.bot = bot
        self.db = db
        self.auth = auth

    def _get_base_url(self, request: web.Request) -> str:
        """Resolve authoritative public HTTPS base URL for redirects."""
        cfg_url = config.get_musicmaid_website_url()
        if cfg_url:
            return cfg_url.rstrip("/")

        if hasattr(self.auth, "get_canonical_base_url"):
            return self.auth.get_canonical_base_url(request)

        proto = request.headers.get("X-Forwarded-Proto") or request.scheme
        host = request.headers.get("X-Forwarded-Host") or request.host
        return f"{proto}://{host}".rstrip("/")

    async def get_plans(self, request: web.Request) -> web.Response:
        """
        GET /api/premium/plans
        Returns public plan details, features comparison, pricing, and provider status.
        """
        payment_cfg = config.get_payment_public_config()

        features_comparison = [
            {"name": "Core Audio Playback & Search", "free": True, "premium": True},
            {"name": "Standard Music Queue", "free": True, "premium": True},
            {"name": "Basic Player Controls (Skip, Pause, Loop)", "free": True, "premium": True},
            {"name": "150% Studio Volume Booster", "free": False, "premium": True},
            {"name": "24/7 Voice Channel Stay Mode", "free": False, "premium": True},
            {"name": "320kbps Lossless Opus Audio Pipeline", "free": False, "premium": True},
            {"name": "AI Anime Maid Voice DJ (All 5 Personalities)", "free": False, "premium": True},
            {"name": "Hardware-Accelerated DSP Studio & Equalizer", "free": False, "premium": True},
            {"name": "Cross-Platform Playlist Importer (Spotify/YT/Apple)", "free": False, "premium": True},
            {"name": "MusicMaid Friend Blend & Taste Compatibility", "free": False, "premium": True},
            {"name": "Zero-Downtime Session Checkpoint Recovery", "free": False, "premium": True},
            {"name": "Interactive Web Master Control Panel", "free": True, "premium": True},
            {"name": "Stage Neon Visualizer & Drag-and-Drop Queue", "free": True, "premium": True},
        ]

        faqs = [
            {
                "q": "What happens after I subscribe to MusicMaid Premium?",
                "a": "All premium features (150% volume cap, 24/7 staying mode, AI Maid Voice DJ, and cross-platform playlist importing) unlock immediately for your Discord account across every server you use."
            },
            {
                "q": "How does payment verification work?",
                "a": "Payments are processed securely via Stripe. The bot backend cryptographically verifies Stripe webhook signatures and checkout receipts before granting access. We never store credit card numbers."
            },
            {
                "q": "Can I cancel my subscription anytime?",
                "a": "Yes! You can cancel anytime from /premium/manage. Your perks remain active until the end of your current paid billing period with no further charges."
            },
            {
                "q": "Do I need to be a server administrator to use Premium?",
                "a": "No! Personal Premium belongs to your Discord user identity and works in any voice room you join. Server owners can also activate 24/7 persistence for their community."
            },
        ]

        return json_success({
            "configured": payment_cfg["configured"],
            "enabled": payment_cfg["enabled"],
            "payments_enabled": payment_cfg.get("payments_enabled", False),
            "is_student_mode": payment_cfg.get("is_student_mode", True),
            "student_notice": payment_cfg.get("student_notice", "Developer Preview Mode"),
            "currency": payment_cfg["currency"],
            "plans": payment_cfg["plans"],
            "features": features_comparison,
            "faqs": faqs,
        })

    async def get_status(self, request: web.Request) -> web.Response:
        """
        GET /api/premium/status
        Returns current logged-in user's verified subscription and entitlements.
        """
        session = await self.auth.get_session_from_request(request)
        if not session:
            return json_success({"authenticated": False, "entitlement": None})

        user_id = session.get("discord_user_id") or session.get("user_id")
        entitlement = await EntitlementService.get_user_entitlement(user_id, self.db)

        return json_success({
            "authenticated": True,
            "user": session.get("user_data"),
            "entitlement": entitlement.to_dict(),
        })

    async def create_order(self, request: web.Request) -> web.Response:
        """
        POST /api/premium/order
        Create a server-side order with Razorpay for authenticated Discord users.
        """
        session = await self.auth.get_session_from_request(request)
        if not session:
            return json_error("You must sign in with Discord before subscribing.", code="UNAUTHORIZED", status=401)

        if not config.PAYMENTS_ENABLED:
            return json_error(
                "Payment processing is currently in Student Developer Showcase Mode. Real checkouts are disabled until account approval.",
                code="PAYMENTS_DISABLED",
                status=503,
            )

        user_id = session.get("discord_user_id") or session.get("user_id")
        user_data = session.get("user_data") or {}
        user_name = user_data.get("display_name") or user_data.get("username") or str(user_id)
        user_email = user_data.get("email")

        try:
            body = await request.json()
        except Exception:
            body = {}

        plan = body.get("plan", "monthly").lower().strip()
        if plan not in ("monthly", "yearly"):
            return json_error("Plan must be either 'monthly' or 'yearly'.", code="INVALID_PLAN")

        try:
            order_data = await RazorpayService.create_order(
                user_id=user_id,
                plan_id=plan,
                user_name=user_name,
                user_email=user_email,
                db=self.db,
            )
            return json_success(order_data, message="Order created successfully.")
        except RuntimeError as e:
            logger.warning(f"[PaymentAPI] Gateway configuration notice: {e}")
            return json_error(str(e), code="GATEWAY_NOT_CONFIGURED", status=503)
        except Exception as e:
            logger.error(f"[PaymentAPI] Order creation error: {e}", exc_info=True)
            return json_error(f"Failed to create order: {e}", code="ORDER_ERROR", status=500)

    async def verify_payment(self, request: web.Request) -> web.Response:
        """
        POST /api/premium/verify
        Cryptographically verify HMAC-SHA256 signature and grant entitlement.
        """
        session = await self.auth.get_session_from_request(request)
        if not session:
            return json_error("Authentication required.", code="UNAUTHORIZED", status=401)

        user_id = session.get("discord_user_id") or session.get("user_id")

        try:
            body = await request.json()
        except Exception:
            return json_error("Invalid JSON payload.", code="INVALID_PAYLOAD")

        razorpay_order_id = body.get("razorpay_order_id", "").strip()
        razorpay_payment_id = body.get("razorpay_payment_id", "").strip()
        razorpay_signature = body.get("razorpay_signature", "").strip()
        plan = body.get("plan", "monthly").lower().strip()

        if not (razorpay_order_id and razorpay_payment_id and razorpay_signature):
            return json_error("Missing payment verification parameters.", code="INVALID_PARAMS")

        is_valid = RazorpayService.verify_signature(
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
        )

        if not is_valid:
            return json_error("Cryptographic signature verification failed.", code="INVALID_SIGNATURE", status=400)

        # Grant verified entitlement
        success, msg = await RazorpayService.grant_verified_entitlement(
            user_id=user_id,
            plan_id=plan,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            db=self.db,
        )

        entitlement = await EntitlementService.get_user_entitlement(user_id, self.db)
        return json_success({
            "verified": True,
            "entitlement": entitlement.to_dict(),
            "payment_id": razorpay_payment_id,
        }, message=msg)

    async def create_checkout(self, request: web.Request) -> web.Response:
        """
        POST /api/premium/create-checkout
        Initiates checkout session (routes to Razorpay order or Stripe session).
        """
        if config.PAYMENT_PROVIDER == "razorpay":
            return await self.create_order(request)

        session = await self.auth.get_session_from_request(request)
        if not session:
            return json_error("You must sign in with Discord before subscribing.", code="UNAUTHORIZED", status=401)

        if not config.PAYMENTS_ENABLED:
            return json_error(
                "Payment processing is currently in Student Developer Showcase Mode. Real checkouts are disabled.",
                code="PAYMENTS_DISABLED",
                status=503,
            )

        user_id = session.get("discord_user_id") or session.get("user_id")
        user_data = session.get("user_data") or {}
        user_name = user_data.get("display_name") or user_data.get("username") or str(user_id)
        user_email = user_data.get("email")

        try:
            body = await request.json()
        except Exception:
            body = {}

        plan = body.get("plan", "monthly").lower().strip()
        if plan not in ("monthly", "yearly"):
            return json_error("Plan must be either 'monthly' or 'yearly'.", code="INVALID_PLAN")

        base_url = self._get_base_url(request)
        success_url = f"{base_url}/premium/success"
        cancel_url = f"{base_url}/premium/cancel"
        ip_addr = request.headers.get("X-Forwarded-For") or request.remote

        try:
            checkout_data = await PaymentService.create_checkout_session(
                user_id=user_id,
                user_email=user_email,
                user_name=user_name,
                plan_id=plan,
                success_url=success_url,
                cancel_url=cancel_url,
                ip_address=ip_addr,
                db=self.db,
            )
            return json_success(checkout_data, message="Checkout session created successfully.")
        except RuntimeError as e:
            logger.warning(f"[PaymentAPI] Gateway configuration notice: {e}")
            return json_error(str(e), code="GATEWAY_NOT_CONFIGURED", status=503)
        except Exception as e:
            logger.error(f"[PaymentAPI] Checkout creation error: {e}", exc_info=True)
            return json_error(f"Failed to create checkout session: {e}", code="CHECKOUT_ERROR", status=500)

    async def verify_session(self, request: web.Request) -> web.Response:
        """
        GET /api/premium/verify-session?session_id=cs_...
        Cryptographically verify the payment status directly with Stripe server-side.
        """
        session = await self.auth.get_session_from_request(request)
        if not session:
            return json_error("Authentication required.", code="UNAUTHORIZED", status=401)

        user_id = session.get("discord_user_id") or session.get("user_id")
        session_id = request.query.get("session_id", "").strip()

        if not session_id:
            return json_error("Missing session_id query parameter.", code="INVALID_REQUEST")

        result = await PaymentService.verify_checkout_session(
            session_id=session_id,
            db=self.db,
            expected_user_id=user_id,
        )

        if not result.get("verified"):
            return json_error(
                result.get("error", "Payment could not be verified by payment provider."),
                code="PAYMENT_NOT_VERIFIED",
                status=400,
            )

        return json_success(result, message="Payment successfully verified.")

    async def cancel_subscription(self, request: web.Request) -> web.Response:
        """
        POST /api/premium/cancel
        Cancel active subscription renewal at period end.
        """
        session = await self.auth.get_session_from_request(request)
        if not session:
            return json_error("Authentication required.", code="UNAUTHORIZED", status=401)

        user_id = session.get("discord_user_id") or session.get("user_id")
        ok = await PaymentService.cancel_subscription(user_id=user_id, db=self.db)
        if ok:
            return json_success(
                {"canceled": True},
                message="Your subscription will not renew after the current billing period concludes.",
            )
        return json_error(
            "No active subscription found to cancel, or cancellation failed.",
            code="CANCEL_FAILED",
            status=400,
        )

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """
        POST /api/premium/webhook
        Ingests and verifies asynchronous webhook events from Stripe.
        """
        payload = await request.read()
        sig_header = request.headers.get("Stripe-Signature", "")

        if not sig_header:
            logger.warning("[PaymentAPI] Webhook received missing Stripe-Signature header.")
            return web.Response(text="Missing Stripe-Signature header", status=400)

        try:
            event = PaymentService.verify_webhook_signature(payload, sig_header)
        except ValueError as val_err:
            logger.warning(f"[PaymentAPI] Webhook verification error: {val_err}")
            return web.Response(text=f"Webhook Error: {val_err}", status=400)
        except stripe.error.SignatureVerificationError as sig_err:
            logger.warning(f"[PaymentAPI] Webhook signature verification failed: {sig_err}")
            return web.Response(text="Invalid signature", status=400)
        except Exception as e:
            logger.error(f"[PaymentAPI] Unexpected webhook verification exception: {e}")
            return web.Response(text="Internal verification error", status=500)

        raw_str = payload.decode("utf-8", errors="ignore")
        success, message = await PaymentService.process_webhook_event(event, raw_str, self.db)

        return web.json_response({"received": True, "status": message}, status=200)

    async def handle_razorpay_webhook(self, request: web.Request) -> web.Response:
        """
        POST /api/premium/webhook/razorpay
        Ingests and verifies asynchronous webhook events from Razorpay.
        """
        payload = await request.read()
        sig_header = request.headers.get("X-Razorpay-Signature", "")

        if not sig_header:
            logger.warning("[PaymentAPI] Razorpay webhook received missing X-Razorpay-Signature header.")
            return web.Response(text="Missing X-Razorpay-Signature header", status=400)

        is_valid = RazorpayService.verify_webhook_signature(payload, sig_header)
        if not is_valid:
            logger.warning("[PaymentAPI] Razorpay webhook signature verification failed.")
            return web.Response(text="Invalid signature", status=400)

        import json
        try:
            event_data = json.loads(payload.decode("utf-8"))
        except Exception:
            return web.Response(text="Invalid JSON", status=400)

        event_type = event_data.get("event")
        payload_entity = event_data.get("payload", {})
        payment_entity = payload_entity.get("payment", {}).get("entity", {})

        if event_type in ("payment.captured", "order.paid"):
            notes = payment_entity.get("notes", {})
            user_id_str = notes.get("user_id")
            plan = notes.get("plan", "monthly")
            payment_id = payment_entity.get("id")
            order_id = payment_entity.get("order_id")
            amount = payment_entity.get("amount")

            if user_id_str and payment_id:
                try:
                    user_id = int(user_id_str)
                    await RazorpayService.grant_verified_entitlement(
                        user_id=user_id,
                        plan_id=plan,
                        razorpay_payment_id=payment_id,
                        razorpay_order_id=order_id or "",
                        db=self.db,
                        amount_paise=amount,
                    )
                    logger.info(f"[PaymentAPI] Webhook granted entitlement for payment {payment_id} to user {user_id}")
                except Exception as e:
                    logger.error(f"[PaymentAPI] Error processing webhook entitlement: {e}")

        return web.json_response({"received": True, "status": "processed"}, status=200)
