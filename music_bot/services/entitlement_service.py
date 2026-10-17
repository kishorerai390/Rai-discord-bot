"""
Authoritative Premium Entitlement Service for MusicMaid.
Serves as the single backend source of truth for user subscription status,
tier validation, expiry checks, and genuine feature gatekeeping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from music_bot import config

logger = logging.getLogger("MusicMaid.Entitlement")


@dataclass
class UserEntitlement:
    user_id: int
    is_premium: bool
    plan: str
    status: str
    current_period_end: Optional[str] = None
    cancel_at_period_end: bool = False
    provider: str = "none"
    perks: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": str(self.user_id),
            "is_premium": self.is_premium,
            "plan": self.plan,
            "status": self.status,
            "current_period_end": self.current_period_end,
            "cancel_at_period_end": self.cancel_at_period_end,
            "provider": self.provider,
            "perks": self.perks,
        }


class EntitlementService:
    """Backend Entitlement Guardian for MusicMaid."""

    PREMIUM_PERKS = {
        "boosted_volume": {
            "name": "150% Studio Volume Booster",
            "desc": "Boost voice channel volume past 100% up to 150% with zero clipping.",
            "unlocked": True,
        },
        "twenty_four_seven": {
            "name": "24/7 Voice Channel Stay Mode",
            "desc": "Keep MusicMaid in your voice channel 24/7 without auto-disconnecting.",
            "unlocked": True,
        },
        "lossless_audio": {
            "name": "320kbps Lossless Opus Pipeline",
            "desc": "Audiophile studio resolution with maximum Discord bitrates.",
            "unlocked": True,
        },
        "maid_voice_dj": {
            "name": "AI Anime Maid Voice DJ",
            "desc": "Unlock all 5 announcer personalities (Maid, Tsundere, Hype, Chill, Cyberpunk).",
            "unlocked": True,
        },
        "studio_dsp": {
            "name": "Hardware-Accelerated DSP Studio",
            "desc": "8D Spatial Audio, Vaporwave Lo-Fi, Nightcore, and Bass Boost equalizer.",
            "unlocked": True,
        },
        "cross_platform_import": {
            "name": "Cross-Platform Playlist Importer",
            "desc": "1-click import for Spotify, YouTube, Apple Music, and SoundCloud playlists.",
            "unlocked": True,
        },
        "friend_blend": {
            "name": "MusicMaid Friend Blend",
            "desc": "Synthesize dual-personality neon mixes with friend compatibility scoring.",
            "unlocked": True,
        },
        "persistent_recovery": {
            "name": "Zero-Downtime Session Recovery",
            "desc": "Instant checkpoint resume if voice or host server restarts.",
            "unlocked": True,
        },
    }

    @classmethod
    async def get_user_entitlement(cls, user_id: int, db: Any) -> UserEntitlement:
        """
        Verify whether user has an active, valid Premium subscription.
        Checks both database subscriptions table and license grants.
        """
        if not user_id:
            return UserEntitlement(
                user_id=0,
                is_premium=False,
                plan="free",
                status="none",
                perks={k: False for k in cls.PREMIUM_PERKS},
            )

        # Bot owner / Founder has permanent VIP license with all perks
        if config.is_bot_owner(user_id):
            return UserEntitlement(
                user_id=user_id,
                is_premium=True,
                plan="owner",
                status="active",
                current_period_end=None,
                cancel_at_period_end=False,
                provider="bot_owner_grant",
                perks={k: True for k in cls.PREMIUM_PERKS},
            )

        now = datetime.now(timezone.utc)
        sub = None

        if hasattr(db, "get_user_subscription"):
            try:
                sub = await db.get_user_subscription(user_id)
            except Exception as e:
                logger.debug(f"[Entitlement] Subscription query error: {e}")

        # Check if subscription record is active and not expired
        if sub and sub.get("status") in ("active", "trialing"):
            period_end = sub.get("current_period_end")
            is_expired = False
            if period_end:
                try:
                    dt_end = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
                    if dt_end < now:
                        is_expired = True
                except Exception:
                    pass

            if is_expired:
                return UserEntitlement(
                    user_id=user_id,
                    is_premium=False,
                    plan=sub.get("plan", "free"),
                    status="expired",
                    current_period_end=period_end,
                    cancel_at_period_end=bool(sub.get("cancel_at_period_end", 0)),
                    provider=sub.get("provider", "stripe"),
                    perks={k: False for k in cls.PREMIUM_PERKS},
                )

            return UserEntitlement(
                user_id=user_id,
                is_premium=True,
                plan=sub.get("plan", "monthly"),
                status=sub.get("status", "active"),
                current_period_end=period_end,
                cancel_at_period_end=bool(sub.get("cancel_at_period_end", 0)),
                provider=sub.get("provider", "stripe"),
                perks={k: True for k in cls.PREMIUM_PERKS},
            )

        # Fallback check on manual guild/user license in music_premium
        if hasattr(db, "get_premium_info"):
            try:
                info = await db.get_premium_info(user_id)
                if info and info.get("is_premium"):
                    return UserEntitlement(
                        user_id=user_id,
                        is_premium=True,
                        plan="lifetime",
                        status="active",
                        provider="license_key",
                        perks={k: True for k in cls.PREMIUM_PERKS},
                    )
            except Exception:
                pass

        # Free tier
        return UserEntitlement(
            user_id=user_id,
            is_premium=False,
            plan="free",
            status="none",
            current_period_end=None,
            cancel_at_period_end=False,
            provider="none",
            perks={k: False for k in cls.PREMIUM_PERKS},
        )

    @classmethod
    async def can_access_feature(cls, user_id: int, feature: str, db: Any) -> bool:
        """Server-side permission guard for protected features."""
        entitlement = await cls.get_user_entitlement(user_id, db)
        return bool(entitlement.is_premium and entitlement.perks.get(feature, False))
