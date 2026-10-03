"""
Sentry Error Tracking and Sanitization Layer for 『RΛI』.
Intercepts exceptions, worker faults, and API crashes while stripping
bot tokens, database URLs, authorization headers, and API keys.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("Rai.Observability.Sentry")

# Patterns for redaction
TOKEN_REGEX = re.compile(r"([a-zA-Z0-9_\-]{24,28}\.[a-zA-Z0-9_\-]{6}\.[a-zA-Z0-9_\-]{27,38})")
DB_URL_REGEX = re.compile(r"://([^:]+):([^@]+)@")
API_KEY_REGEX = re.compile(r"(AIza[0-9A-Za-z-_]{35}|sk-[a-zA-Z0-9]{48})")


def sanitize_text(text: str) -> str:
    """Removes sensitive credentials, bot tokens, and passwords from string payloads."""
    if not text:
        return text
    text = TOKEN_REGEX.sub("[REDACTED_DISCORD_TOKEN]", text)
    text = DB_URL_REGEX.sub("://[USER]:[REDACTED_PW]@", text)
    text = API_KEY_REGEX.sub("[REDACTED_API_KEY]", text)
    return text


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redacts sensitive fields and values from metadata dictionaries."""
    sanitized: Dict[str, Any] = {}
    for k, v in data.items():
        k_lower = str(k).lower()
        if any(secret in k_lower for secret in ("token", "password", "secret", "authorization", "key", "credential")):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, str):
            sanitized[k] = sanitize_text(v)
        elif isinstance(v, dict):
            sanitized[k] = sanitize_dict(v)
        else:
            sanitized[k] = v
    return sanitized


class SentryTracker:
    """
    Manages Sentry SDK error tracking with automated sanitization.
    """

    _initialized = False

    @classmethod
    def initialize(cls) -> bool:
        if cls._initialized:
            return True

        dsn = os.getenv("SENTRY_DSN")
        enabled = os.getenv("SENTRY_ENABLED", "true").lower() in ("true", "1", "yes") and bool(dsn)

        if not enabled:
            logger.info("Sentry error tracking is disabled or SENTRY_DSN not configured.")
            return False

        try:
            import sentry_sdk

            def before_send(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                """Global event scrubber executed before any event leaves the bot."""
                try:
                    # Sanitize message and exceptions
                    if "logentry" in event and "message" in event["logentry"]:
                        event["logentry"]["message"] = sanitize_text(event["logentry"]["message"])

                    if "exception" in event and "values" in event["exception"]:
                        for exc in event["exception"]["values"]:
                            if "value" in exc:
                                exc["value"] = sanitize_text(exc["value"])

                    if "extra" in event:
                        event["extra"] = sanitize_dict(event["extra"])

                    # Scrub request headers if present
                    if "request" in event and "headers" in event["request"]:
                        event["request"]["headers"] = sanitize_dict(event["request"]["headers"])
                except Exception as e:
                    logger.debug(f"Sentry before_send scrubber note: {e}")
                return event

            sentry_sdk.init(
                dsn=dsn,
                traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                profiles_sample_rate=0.0,
                before_send=before_send,
                release=f"rai-bot@{os.getenv('APP_VERSION', '1.0.0')}",
                environment=os.getenv("APP_ENV", "production"),
            )
            cls._initialized = True
            logger.info("Sentry error tracking initialized with payload sanitization.")
            return True
        except Exception as e:
            logger.warning(f"Could not initialize Sentry: {e}")
            return False

    @classmethod
    def capture_exception(
        cls,
        error: Exception,
        component: str = "core",
        severity: str = "error",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Captures an exception to Sentry with component tags and sanitized extra data."""
        if not cls._initialized:
            return

        try:
            import sentry_sdk
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("component", component)
                scope.set_level(severity)
                if extra:
                    scope.set_context("diagnostics", sanitize_dict(extra))
                sentry_sdk.capture_exception(error)
        except Exception as e:
            logger.debug(f"Failed to transmit exception to Sentry: {e}")
