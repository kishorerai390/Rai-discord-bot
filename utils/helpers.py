"""
Interactive UI Views, Audit Log Resolvers, and Formatting Helpers.
"""

from __future__ import annotations

import asyncio
import datetime
import re
from typing import Callable, List, Optional, Tuple
import discord


# ==========================================
# INTERACTIVE UI VIEWS
# ==========================================

class ConfirmView(discord.ui.View):
    """Interactive confirmation view with Confirm & Cancel buttons."""

    def __init__(self, author_id: int, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "You are not authorized to use these buttons.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class PaginationView(discord.ui.View):
    """Pagination view for multi-page embed lists."""

    def __init__(self, pages: List[discord.Embed], author_id: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author_id = author_id
        self.current_page = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command runner can navigate pages.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)


# ==========================================
# AUDIT LOG VERIFICATION SAFEGUARD
# ==========================================

async def find_audit_executor(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    target_id: Optional[int] = None,
    max_retries: int = 3,
    delay_seconds: float = 0.6,
    max_age_seconds: float = 12.0,
) -> Tuple[Optional[discord.User | discord.Member], Optional[discord.AuditLogEntry]]:
    """
    Safely locate the executor responsible for an audit-log event.
    Applies bounded retries to handle Discord's asynchronous audit-log propagation.
    Ensures fail-safe behavior: returns None if uncertain.
    """
    if not guild.me.guild_permissions.view_audit_log:
        return None, None

    now = datetime.datetime.now(datetime.timezone.utc)

    for attempt in range(max_retries):
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                # Verify age
                age = (now - entry.created_at).total_seconds()
                if age < 0 or age > max_age_seconds:
                    continue

                # Verify target if target_id provided
                if target_id is not None:
                    if entry.target and hasattr(entry.target, "id") and entry.target.id == target_id:
                        return entry.user, entry
                else:
                    return entry.user, entry

        except (discord.Forbidden, discord.HTTPException):
            break

        if attempt < max_retries - 1:
            await asyncio.sleep(delay_seconds)

    return None, None


# ==========================================
# FORMATTING & TIME HELPERS
# ==========================================

def parse_duration(duration_str: str) -> Optional[int]:
    """
    Parses a duration string into seconds (e.g., '10s', '5m', '2h', '1d', '7d').
    Returns total seconds or None if invalid.
    """
    if not duration_str:
        return None

    match = re.match(r"^(\d+)([smhd])$", duration_str.strip().lower())
    if not match:
        return None

    val = int(match.group(1))
    unit = match.group(2)

    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return val * multipliers[unit]


def format_duration(seconds: float) -> str:
    """Formats seconds into readable string (e.g. '2m 30s')."""
    total = int(round(seconds))
    if total < 60:
        return f"{total}s"
    minutes, sec = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s" if sec else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"
