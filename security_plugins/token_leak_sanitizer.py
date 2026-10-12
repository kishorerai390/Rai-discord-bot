"""
Token & Credential Leak Sanitizer Plugin.
Detects accidentally leaked Discord tokens, API keys, or webhooks in public channels.
"""

from __future__ import annotations

import re
import logging
from typing import Optional
import discord

from core.plugin_engine import BaseSecurityPlugin

logger = logging.getLogger("Sentinel.Plugin.TokenLeakSanitizer")

DISCORD_TOKEN_REGEX = re.compile(r"[MNO][a-zA-Z\d_-]{23,25}\.[a-zA-Z\d_-]{6}\.[a-zA-Z\d_-]{27,38}")
API_KEY_REGEX = re.compile(r"(?:sk-[a-zA-Z0-9]{32,}|ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{50,})")


class TokenLeakSanitizerPlugin(BaseSecurityPlugin):
    name = "TokenLeakSanitizer"
    version = "1.0.0"
    author = "Rai Security Operations"
    description = "Immediate redaction of Discord tokens and developer API keys posted into server channels."

    async def on_message(self, message: discord.Message) -> Optional[bool]:
        if not message.guild or message.author.bot:
            return True

        content = message.content or ""
        has_token = bool(DISCORD_TOKEN_REGEX.search(content))
        has_api_key = bool(API_KEY_REGEX.search(content))

        if has_token or has_api_key:
            try:
                await message.delete()
            except Exception:
                pass

            leak_type = "Discord Bot Token" if has_token else "API Secret Key"
            try:
                await message.channel.send(
                    f"🛡️ **Security Notice:** A message by {message.author.mention} was deleted because it contained a leaked **{leak_type}**. Please regenerate your credentials immediately!",
                    delete_after=12.0,
                )
            except Exception:
                pass

            try:
                from utils.owner_reporter import log_security_incident
                await log_security_incident(
                    self.bot,
                    message.guild.id,
                    event="Credential Leak Intercepted",
                    user=message.author,
                    action_taken="Message purged & author alerted",
                    details={
                        "Plugin": self.name,
                        "Credential Type": leak_type,
                        "Channel": f"#{message.channel.name}" if hasattr(message.channel, "name") else str(message.channel.id),
                    },
                )
            except Exception:
                pass

            return False

        return True
