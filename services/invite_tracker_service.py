"""
THOR APEX — Advanced Invite Tracker Service.
Provides high-performance, resilient invite tracking, vanity detection,
account age fraud detection, and reward reconciliation.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Dict, Optional, Tuple, List, TYPE_CHECKING
import discord

from config import Colors
from database.models import InviteTrackerConfig, MemberInvite, InviterStats, InviteReward

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("ThorApex.InviteTracker")


class InviteTrackerService:
    """Singleton service managing invite caches, joins, leaves, and rewards."""

    _instance: Optional[InviteTrackerService] = None

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # guild_id -> {invite_code: uses}
        self._invite_cache: Dict[int, Dict[str, int]] = {}
        # guild_id -> {invite_code: inviter_id}
        self._inviter_cache: Dict[int, Dict[str, Optional[int]]] = {}
        # guild_id -> vanity_uses
        self._vanity_cache: Dict[int, int] = {}
        # guild_id -> {deleted_code: last_known_uses}
        self._deleted_invites: Dict[int, Dict[str, int]] = {}
        # guild_id -> asyncio.Lock
        self._guild_locks: Dict[int, asyncio.Lock] = {}

    @classmethod
    def get_instance(cls, bot: Optional[SentinelBot] = None) -> InviteTrackerService:
        if cls._instance is None:
            if bot is None:
                raise RuntimeError("InviteTrackerService requires bot instance for initialization.")
            cls._instance = cls(bot)
        elif bot is not None:
            cls._instance.bot = bot
        return cls._instance

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._guild_locks:
            self._guild_locks[guild_id] = asyncio.Lock()
        return self._guild_locks[guild_id]

    async def sync_guild(self, guild: discord.Guild) -> bool:
        """Fetch and cache all current guild invites and vanity URL uses."""
        lock = self._get_lock(guild.id)
        async with lock:
            if not guild.me.guild_permissions.manage_guild:
                logger.warning(
                    f"[INVITE_SYNC_SKIPPED] Bot lacks 'Manage Server' permission in guild {guild.name} ({guild.id})"
                )
                return False

            invites_map: Dict[str, int] = {}
            inviters_map: Dict[str, Optional[int]] = {}

            try:
                guild_invites = await guild.invites()
                for inv in guild_invites:
                    invites_map[inv.code] = inv.uses or 0
                    inviters_map[inv.code] = inv.inviter.id if inv.inviter else None
            except Exception as e:
                logger.error(f"[INVITE_SYNC_ERROR] Could not fetch invites for {guild.name}: {e}")
                return False

            self._invite_cache[guild.id] = invites_map
            self._inviter_cache[guild.id] = inviters_map

            # Vanity URL cache
            if "VANITY_URL" in guild.features:
                try:
                    vanity = await guild.vanity_invite()
                    self._vanity_cache[guild.id] = vanity.uses or 0
                except Exception as ve:
                    logger.debug(f"Vanity invite fetch note for {guild.name}: {ve}")
                    self._vanity_cache[guild.id] = 0
            else:
                self._vanity_cache[guild.id] = 0

            logger.info(
                f"[INVITE_SYNC_SUCCESS] Cached {len(invites_map)} invites for {guild.name} ({guild.id})"
            )
            return True

    def on_invite_create(self, invite: discord.Invite) -> None:
        """Register newly created invite link into memory cache."""
        if not invite.guild:
            return
        gid = invite.guild.id
        if gid not in self._invite_cache:
            self._invite_cache[gid] = {}
        if gid not in self._inviter_cache:
            self._inviter_cache[gid] = {}

        self._invite_cache[gid][invite.code] = invite.uses or 0
        self._inviter_cache[gid][invite.code] = invite.inviter.id if invite.inviter else None
        logger.debug(f"[INVITE_CREATE] Cached code {invite.code} in guild {gid}")

    def on_invite_delete(self, invite: discord.Invite) -> None:
        """Cache deleted invite info for single-use join detection."""
        if not invite.guild:
            return
        gid = invite.guild.id
        uses = 0
        if gid in self._invite_cache and invite.code in self._invite_cache[gid]:
            uses = self._invite_cache[gid].pop(invite.code)

        if gid not in self._deleted_invites:
            self._deleted_invites[gid] = {}
        self._deleted_invites[gid][invite.code] = uses
        logger.debug(f"[INVITE_DELETE] Stored deleted code {invite.code} (last uses: {uses}) in guild {gid}")

    async def process_member_join(
        self, member: discord.Member
    ) -> Tuple[Optional[int], Optional[str], str]:
        """
        Handles member join event with atomic cache comparison, fraud checks,
        and database attribution.
        Returns: (inviter_id, invite_code, classification)
        """
        guild = member.guild
        lock = self._get_lock(guild.id)

        async with lock:
            config = await self.bot.db.get_invite_tracker_config(guild.id)
            if not config.enabled:
                return None, None, "disabled"

            # Check bot permissions
            if not guild.me.guild_permissions.manage_guild:
                logger.warning(
                    f"[INVITE_TRACK_PERM] Bot lacks 'Manage Server' in {guild.name}. Cannot attribute join."
                )
                rec_id = await self.bot.db.record_member_invite(
                    guild_id=guild.id,
                    member_id=member.id,
                    inviter_id=None,
                    invite_code=None,
                    classification="unknown",
                    account_age_days=self._calc_account_age_days(member),
                    notes="Missing Manage Server permission",
                )
                return None, None, "unknown"

            cached_invites = self._invite_cache.get(guild.id, {})
            cached_inviters = self._inviter_cache.get(guild.id, {})
            cached_vanity = self._vanity_cache.get(guild.id, 0)

            matched_code: Optional[str] = None
            inviter_id: Optional[int] = None
            classification = "regular"

            # 1. Fetch live invites from Discord
            try:
                live_invites = await guild.invites()
            except Exception as e:
                logger.error(f"[INVITE_FETCH_FAILED] Could not fetch live invites: {e}")
                live_invites = []

            live_map = {inv.code: (inv.uses or 0) for inv in live_invites}
            live_inviters = {inv.code: (inv.inviter.id if inv.inviter else None) for inv in live_invites}

            # 2. Compare uses
            increased_codes = [
                code for code, uses in live_map.items()
                if uses > cached_invites.get(code, 0)
            ]

            if len(increased_codes) == 1:
                matched_code = increased_codes[0]
                inviter_id = live_inviters.get(matched_code) or cached_inviters.get(matched_code)
            elif len(increased_codes) > 1:
                # Concurrent join or ambiguous burst
                matched_code = increased_codes[0]
                inviter_id = live_inviters.get(matched_code)
                classification = "ambiguous"
            else:
                # No regular invite incremented. Check Vanity URL
                if "VANITY_URL" in guild.features and config.track_vanity:
                    try:
                        live_vanity = await guild.vanity_invite()
                        if (live_vanity.uses or 0) > cached_vanity:
                            matched_code = live_vanity.code
                            classification = "vanity"
                            self._vanity_cache[guild.id] = live_vanity.uses or 0
                    except Exception:
                        pass

                # Check single-use invites deleted on use
                if not matched_code:
                    missing_codes = [
                        code for code in cached_invites.keys()
                        if code not in live_map
                    ]
                    if len(missing_codes) == 1:
                        matched_code = missing_codes[0]
                        inviter_id = cached_inviters.get(matched_code)
                    elif len(missing_codes) > 1:
                        matched_code = missing_codes[0]
                        inviter_id = cached_inviters.get(matched_code)
                        classification = "ambiguous"

            # Update cache to current live map
            self._invite_cache[guild.id] = live_map
            self._inviter_cache[guild.id] = live_inviters

            # 3. Fraud / Fake Detection & Re-join Check
            account_age_days = self._calc_account_age_days(member)
            if classification == "regular" and account_age_days < config.min_account_age_days:
                classification = "fake"

            # Check if user previously joined
            existing_invite = await self.bot.db.get_member_invite(guild.id, member.id)
            if existing_invite is not None and classification == "regular":
                classification = "rejoin"

            # 4. Persist in database
            notes = f"Attributed via {classification}"
            await self.bot.db.record_member_invite(
                guild_id=guild.id,
                member_id=member.id,
                inviter_id=inviter_id,
                invite_code=matched_code,
                classification=classification,
                account_age_days=account_age_days,
                notes=notes,
            )

            # 5. Increment Inviter Stats
            if inviter_id:
                if classification == "regular":
                    await self.bot.db.increment_inviter_stats(
                        guild.id, inviter_id, regular_delta=1
                    )
                elif classification == "fake":
                    await self.bot.db.increment_inviter_stats(
                        guild.id, inviter_id, fake_delta=1
                    )

            # 6. Check Rewards
            if config.rewards_enabled and inviter_id:
                await self.reconcile_member_rewards(guild, inviter_id)

            # 7. Dispatch Welcome & Log Messages
            await self._dispatch_join_notifications(
                guild=guild,
                member=member,
                inviter_id=inviter_id,
                invite_code=matched_code,
                classification=classification,
                account_age_days=account_age_days,
                config=config,
            )

            return inviter_id, matched_code, classification

    async def process_member_remove(self, member: discord.Member) -> Optional[int]:
        """
        Handles member departure, updates inviter left counts,
        and optionally reconciles rewards.
        Returns: inviter_id if tracked, else None.
        """
        guild = member.guild
        config = await self.bot.db.get_invite_tracker_config(guild.id)
        if not config.enabled:
            return None

        invite = await self.bot.db.mark_member_left(guild.id, member.id)
        if not invite or not invite.inviter_id:
            return None

        inviter_id = invite.inviter_id
        if config.deduct_on_leave and invite.classification == "regular":
            await self.bot.db.increment_inviter_stats(guild.id, inviter_id, left_delta=1)

        # Reconcile rewards if enabled
        if config.rewards_enabled:
            await self.reconcile_member_rewards(guild, inviter_id)

        # Send departure log
        if config.log_channel_id:
            log_ch = guild.get_channel(config.log_channel_id)
            if log_ch and hasattr(log_ch, "send"):
                stats = await self.bot.db.get_inviter_stats(guild.id, inviter_id)
                inviter_user = self.bot.get_user(inviter_id)
                inviter_name = f"{inviter_user.name}" if inviter_user else f"User {inviter_id}"

                embed = discord.Embed(
                    title="📤 Member Left — Invite Tracker",
                    description=f"**{member.name}** (`{member.id}`) left the server.",
                    color=Colors.WARNING,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                embed.add_field(name="👤 Original Inviter", value=f"<@{inviter_id}> (`{inviter_name}`)", inline=True)
                embed.add_field(
                    name="📊 Updated Inviter Stats",
                    value=f"✅ Regular: **{stats.regular_invites}** | ❌ Left: **{stats.left_invites}** | ⚡ Net: **{stats.effective_invites}**",
                    inline=False,
                )
                embed.set_footer(text="THOR APEX • Advanced Invite System")
                try:
                    await log_ch.send(embed=embed)
                except Exception as e:
                    logger.debug(f"Could not send leave log: {e}")

        return inviter_id

    async def reconcile_member_rewards(self, guild: discord.Guild, user_id: int) -> None:
        """Assign or verify invite milestone roles for an inviter."""
        rewards = await self.bot.db.get_invite_rewards(guild.id)
        if not rewards:
            return

        member = guild.get_member(user_id)
        if not member:
            return

        stats = await self.bot.db.get_inviter_stats(guild.id, user_id)
        net_invites = stats.effective_invites

        for r in rewards:
            role = guild.get_role(r.role_id)
            if not role or role >= guild.me.top_role:
                continue

            if net_invites >= r.required_invites:
                if role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f"THOR APEX: Reached {r.required_invites} invites milestone")
                        logger.info(f"[REWARD_GRANTED] Assigned {role.name} to {member.name} ({net_invites} invites)")
                    except Exception as e:
                        logger.warning(f"Failed to add reward role {role.id} to {user_id}: {e}")
            else:
                # Remove if fallen below milestone
                if role in member.roles:
                    try:
                        await member.remove_roles(role, reason="THOR APEX: Dropped below required invite milestone")
                        logger.info(f"[REWARD_REVOKED] Removed {role.name} from {member.name} ({net_invites} invites)")
                    except Exception as e:
                        logger.warning(f"Failed to remove reward role {role.id} from {user_id}: {e}")

    async def _dispatch_join_notifications(
        self,
        guild: discord.Guild,
        member: discord.Member,
        inviter_id: Optional[int],
        invite_code: Optional[str],
        classification: str,
        account_age_days: float,
        config: InviteTrackerConfig,
    ) -> None:
        """Sends welcome embed / template message and detailed security log."""
        inviter_user = self.bot.get_user(inviter_id) if inviter_id else None
        inviter_mention = f"<@{inviter_id}>" if inviter_id else "Unknown / Vanity"
        inviter_tag = inviter_user.name if inviter_user else "Unknown"

        inv_count = 0
        if inviter_id:
            stats = await self.bot.db.get_inviter_stats(guild.id, inviter_id)
            inv_count = stats.effective_invites

        # 1. Welcome Message
        if config.send_welcome and config.welcome_channel_id:
            welcome_ch = guild.get_channel(config.welcome_channel_id)
            if welcome_ch and hasattr(welcome_ch, "send"):
                raw_msg = config.welcome_message or "Welcome {user} to {server}! Invited by {inviter}."
                formatted = (
                    raw_msg.replace("{user}", member.mention)
                    .replace("{username}", member.name)
                    .replace("{server}", guild.name)
                    .replace("{inviter}", inviter_mention)
                    .replace("{inviter_tag}", inviter_tag)
                    .replace("{invite_code}", invite_code or "N/A")
                    .replace("{inviter_invites}", str(inv_count))
                )
                try:
                    await welcome_ch.send(formatted)
                except Exception as e:
                    logger.debug(f"Could not send welcome message: {e}")

        # 2. Detailed Log Channel
        if config.log_channel_id:
            log_ch = guild.get_channel(config.log_channel_id)
            if log_ch and hasattr(log_ch, "send"):
                embed_color = Colors.SUCCESS
                badge = "✅ Verified Join"
                if classification == "fake":
                    embed_color = Colors.ALERT
                    badge = "⚠️ Suspicious / Young Account"
                elif classification == "rejoin":
                    embed_color = Colors.INFO
                    badge = "🔄 Re-joined Server"
                elif classification in ("vanity", "unknown"):
                    embed_color = Colors.PRIMARY
                    badge = "🌐 Vanity / Direct Join"

                embed = discord.Embed(
                    title=f"📥 Member Joined ╏ {badge}",
                    description=f"Welcome {member.mention} (`{member.name}` • `{member.id}`)",
                    color=embed_color,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                if member.display_avatar:
                    embed.set_thumbnail(url=member.display_avatar.url)

                embed.add_field(name="👤 Inviter", value=f"{inviter_mention}\n`{inviter_tag}`", inline=True)
                embed.add_field(name="🔗 Code", value=f"`{invite_code or 'Unknown'}`", inline=True)
                embed.add_field(name="🛡️ Classification", value=f"`{classification.upper()}`", inline=True)
                embed.add_field(
                    name="⏳ Account Age",
                    value=f"`{round(account_age_days, 1)} days` {'⚠️ (< threshold)' if classification == 'fake' else ''}",
                    inline=True,
                )
                embed.add_field(name="📈 Total Invites", value=f"**{inv_count}** valid", inline=True)
                embed.set_footer(text="THOR APEX • Apex Invite Architecture")

                try:
                    await log_ch.send(embed=embed)
                except Exception as e:
                    logger.debug(f"Could not send invite log embed: {e}")

    @staticmethod
    def _calc_account_age_days(member: discord.Member) -> float:
        now = datetime.datetime.now(datetime.timezone.utc)
        return max(0.0, (now - member.created_at).total_seconds() / 86400.0)
