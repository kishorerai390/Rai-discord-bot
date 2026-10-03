"""
Dynamic Voice Channel Cleanup Engine & Background Worker for 『RΛI』.

Core Responsibilities:
1. Enforces 60-second inactivity auto-deletion on empty temporary Dynamic VCs.
2. Reacts to real voice state transitions (leave, join, move) with immediate database persistence.
3. Dedicated restart-safe DynamicVCCleanupWorker running every 5-10 seconds.
4. Pre-deletion verification: confirms 0 occupants, temporary VC type, not protected, and no rejoins.
5. Per-room async locking to prevent race conditions during simultaneous disconnects or restarts.
6. Clean music session teardown before channel deletion.
7. Structured telemetry logging with DVC tags.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import discord

from config import Colors, DYNAMIC_VC_EMPTY_TIMEOUT_SECONDS
from database.models import DynamicRoom
from utils.dynamic_vc_control import DynamicVCControlManager
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed
from utils.owner_reporter import OwnerReporter

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.DynamicVCCleanup")


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class CleanupStatus:
    ACTIVE = "ACTIVE"
    EMPTY_WAITING = "EMPTY_WAITING"
    CLEANING = "CLEANING"
    DELETED = "DELETED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class DynamicVCCleanupService:
    """
    Central orchestration service for temporary dynamic voice room lifecycle,
    inactivity countdowns, and safe atomic channel deletion.
    """

    # Per-room asyncio locks to prevent concurrent delete/update races
    _room_locks: Dict[int, asyncio.Lock] = {}
    _locks_guard = asyncio.Lock()

    # Telemetry metrics
    last_scan_time: Optional[datetime.datetime] = None
    last_successful_cleanup: Optional[datetime.datetime] = None
    last_cleanup_failure: Optional[datetime.datetime] = None
    cleanups_completed_count: int = 0
    cleanups_failed_count: int = 0

    @classmethod
    def get_empty_timeout_seconds(cls) -> int:
        """Returns the configured empty room timeout in seconds."""
        try:
            return int(os.getenv("DYNAMIC_VC_EMPTY_TIMEOUT_SECONDS", str(DYNAMIC_VC_EMPTY_TIMEOUT_SECONDS)))
        except (ValueError, TypeError):
            return 60

    @classmethod
    def get_room_lock(cls, room_id: int) -> asyncio.Lock:
        """Gets or creates an asyncio.Lock for a specific room ID."""
        if room_id not in cls._room_locks:
            cls._room_locks[room_id] = asyncio.Lock()
        return cls._room_locks[room_id]

    # =========================================================================
    # VOICE STATE HANDLERS
    # =========================================================================

    @classmethod
    async def handle_member_leave(
        cls,
        bot: SentinelBot,
        member: discord.Member,
        channel: discord.VoiceChannel,
    ) -> None:
        """
        Called when a member departs a voice channel.
        If the channel is a dynamic temporary room and now completely empty,
        persists EMPTY_WAITING state and schedules the 60-second cleanup.
        """
        if not isinstance(channel, discord.VoiceChannel):
            return

        room = await bot.db.get_dynamic_room(channel.id)
        if not room:
            # Not a dynamic room
            return

        lock = cls.get_room_lock(channel.id)
        async with lock:
            guild = member.guild
            # Recalculate members currently present in the channel
            # In discord.py, channel.members may still include member if cached
            remaining = [m for m in channel.members if m.id != member.id and not m.bot]
            all_remaining = [m for m in channel.members if m.id != member.id]

            if len(all_remaining) > 0:
                # Room still has occupants (owner leaving while others stay is permitted)
                if room.cleanup_status == CleanupStatus.EMPTY_WAITING or room.status == "empty_countdown":
                    logger.info(
                        f"DVC_CLEANUP_CANCELLED_OCCUPANTS room #{channel.name} ({channel.id}) "
                        f"has {len(all_remaining)} occupants remaining. Restoring ACTIVE."
                    )
                    await bot.db.update_dynamic_room(
                        channel.id,
                        cleanup_status=CleanupStatus.ACTIVE,
                        empty_since=None,
                        cleanup_due_at=None,
                        status="active",
                        last_empty_at=None,
                    )
                    await DynamicVCControlManager.update_room_panel(bot, guild, channel.id)
                return

            # Zero occupants remaining -> initiate 60s countdown!
            now = utcnow()
            timeout_sec = cls.get_empty_timeout_seconds()
            empty_since_str = now.isoformat()
            due_at_dt = now + datetime.timedelta(seconds=timeout_sec)
            due_at_str = due_at_dt.isoformat()

            logger.info(
                f"DVC_EMPTY_DETECTED guild_id={guild.id} channel_id={channel.id} "
                f"empty_since={empty_since_str} cleanup_due_at={due_at_str} timeout={timeout_sec}s"
            )

            await bot.db.update_dynamic_room(
                channel.id,
                cleanup_status=CleanupStatus.EMPTY_WAITING,
                empty_since=empty_since_str,
                cleanup_due_at=due_at_str,
                status="empty_countdown",
                last_empty_at=empty_since_str,
                last_voice_activity=empty_since_str,
            )
            await DynamicVCControlManager.update_room_panel(bot, guild, channel.id)

    @classmethod
    async def handle_member_join(
        cls,
        bot: SentinelBot,
        member: discord.Member,
        channel: discord.VoiceChannel,
    ) -> None:
        """
        Called when a member joins a voice channel.
        If the channel was in an empty grace period countdown, immediately cancels
        the pending cleanup and restores ACTIVE status.
        """
        if not isinstance(channel, discord.VoiceChannel):
            return

        room = await bot.db.get_dynamic_room(channel.id)
        if not room:
            return

        lock = cls.get_room_lock(channel.id)
        async with lock:
            if room.cleanup_status == CleanupStatus.EMPTY_WAITING or room.status == "empty_countdown":
                logger.info(
                    f"DVC_CLEANUP_CANCELLED_REJOIN member {member.display_name} ({member.id}) "
                    f"rejoined room #{channel.name} ({channel.id}). Restoring ACTIVE."
                )
                await bot.db.update_dynamic_room(
                    channel.id,
                    cleanup_status=CleanupStatus.ACTIVE,
                    empty_since=None,
                    cleanup_due_at=None,
                    status="active",
                    last_empty_at=None,
                    last_voice_activity=utcnow_iso(),
                )
                await DynamicVCControlManager.update_room_panel(bot, member.guild, channel.id)

    # =========================================================================
    # ATOMIC ROOM CLEANUP EXECUTION
    # =========================================================================

    @classmethod
    async def execute_room_cleanup(
        cls,
        bot: SentinelBot,
        room_id: int,
        guild: Optional[discord.Guild] = None,
        reason: str = "60s empty grace period expired",
        force: bool = False,
    ) -> Tuple[bool, str]:
        """
        Performs the complete verification and deletion lifecycle for an empty dynamic room.
        Guarantees strict safety verification before deleting any Discord channel.
        """
        lock = cls.get_room_lock(room_id)
        async with lock:
            # 1. Load room record
            room = await bot.db.get_dynamic_room(room_id)
            if not room:
                return True, "Room record not found in database"

            guild = guild or bot.get_guild(room.guild_id)
            if not guild:
                # Guild no longer accessible; clean up stale database record
                await bot.db.delete_dynamic_room(room_id)
                return True, "Guild unavailable, cleaned up database"

            # 2. Fetch Discord channel
            vc = guild.get_channel(room.voice_channel_id)
            if not vc or not isinstance(vc, discord.VoiceChannel):
                # Channel already deleted manually or gone on Discord
                logger.info(f"DVC_CLEANUP_ORPHAN_FOUND channel {room_id} not found on Discord. Cleaning panel & DB.")
                await DynamicVCControlManager.delete_room_panel(bot, guild, room_id)
                cls.last_successful_cleanup = utcnow()
                cls.cleanups_completed_count += 1
                return True, "Channel was already deleted on Discord"

            # 3. Check permanent / trigger protection
            cfg = await bot.db.get_temp_voice_config(guild.id)
            if cfg and cfg.hub_channel_id and vc.id == cfg.hub_channel_id:
                logger.warning(f"Refusing cleanup: channel {vc.id} is the configured Hub trigger channel!")
                return False, "Channel is trigger hub"

            vc_name_upper = vc.name.upper()
            if "CREATE YOUR ROOM" in vc_name_upper or "CREATE PRIVATE ROOM" in vc_name_upper:
                logger.warning(f"Refusing cleanup: channel {vc.name} ({vc.id}) is a system trigger channel!")
                return False, "Channel is a trigger channel"

            # 4. Check protected_until
            if not force and room.protected_until:
                try:
                    prot_dt = datetime.datetime.fromisoformat(room.protected_until)
                    if utcnow() < prot_dt:
                        logger.info(f"Room {vc.id} is protected until {room.protected_until}. Skipping cleanup.")
                        return False, "Room is currently protected"
                except Exception:
                    pass

            # 5. Check occupant count
            all_occupants = list(vc.members)
            if len(all_occupants) > 0 and not force:
                logger.info(
                    f"DVC_CLEANUP_CANCELLED_REJOIN room #{vc.name} ({vc.id}) has "
                    f"{len(all_occupants)} occupants. Cancelling deletion."
                )
                await bot.db.update_dynamic_room(
                    room_id,
                    cleanup_status=CleanupStatus.ACTIVE,
                    empty_since=None,
                    cleanup_due_at=None,
                    status="active",
                    last_empty_at=None,
                )
                await DynamicVCControlManager.update_room_panel(bot, guild, room_id)
                return False, "Channel is not empty"

            # 6. Verify cleanup_due_at or last_empty_at has arrived (unless force=True)
            if not force:
                due_reached = False
                if room.cleanup_due_at:
                    try:
                        due_reached = utcnow() >= datetime.datetime.fromisoformat(room.cleanup_due_at)
                    except Exception:
                        due_reached = True
                elif room.last_empty_at:
                    try:
                        due_reached = (utcnow() - datetime.datetime.fromisoformat(room.last_empty_at)).total_seconds() >= cls.get_empty_timeout_seconds()
                    except Exception:
                        due_reached = True
                else:
                    due_reached = True

                if not due_reached:
                    return False, "Cleanup not yet due"

            # 7. Disconnect and stop any active music session in this channel
            if guild.voice_client and guild.voice_client.channel and guild.voice_client.channel.id == vc.id:
                try:
                    logger.info(f"DVC_CLEANUP_MUSIC_HALT disconnecting bot music client from #{vc.name}")
                    await guild.voice_client.disconnect(force=True)
                except Exception as e:
                    logger.warning(f"Error disconnecting voice client from #{vc.name}: {e}")

            music_cog = bot.cogs.get("Music")
            if music_cog and hasattr(music_cog, "players") and guild.id in music_cog.players:
                player = music_cog.players[guild.id]
                if getattr(player, "channel_id", None) == vc.id:
                    try:
                        player.queue.clear()
                        player.current = None
                    except Exception:
                        pass

            # 8. Mark CLEANING in DB
            await bot.db.update_dynamic_room(room_id, cleanup_status=CleanupStatus.CLEANING)

            # 9. Delete the Discord Voice Channel
            logger.info(f"DVC_CLEANUP_DELETE_REQUESTED #{vc.name} ({vc.id}) in guild {guild.name}")
            try:
                await vc.delete(reason=f"Rai Dynamic VC: {reason}")
                logger.info(f"DVC_CLEANUP_SUCCESS #{vc.name} ({vc.id}) deleted.")
            except discord.NotFound:
                logger.info(f"DVC_CLEANUP_SUCCESS #{vc.id} was already removed.")
            except discord.Forbidden as e:
                cls.last_cleanup_failure = utcnow()
                cls.cleanups_failed_count += 1
                logger.error(f"DVC_CLEANUP_FAILED Forbidden deleting #{vc.name} ({vc.id}): {e}")
                await bot.db.update_dynamic_room(
                    room_id,
                    cleanup_status=CleanupStatus.ERROR,
                    cleanup_attempts=(room.cleanup_attempts or 0) + 1,
                )
                return False, f"Missing permission to delete channel: {e}"
            except Exception as e:
                cls.last_cleanup_failure = utcnow()
                cls.cleanups_failed_count += 1
                logger.error(f"DVC_CLEANUP_FAILED Error deleting #{vc.name} ({vc.id}): {e}")
                await bot.db.update_dynamic_room(
                    room_id,
                    cleanup_status=CleanupStatus.ERROR,
                    cleanup_attempts=(room.cleanup_attempts or 0) + 1,
                )
                return False, f"Error deleting channel: {e}"

            # 10. Clean up room panel message and database record
            await DynamicVCControlManager.delete_room_panel(bot, guild, room_id)

            cls.last_successful_cleanup = utcnow()
            cls.cleanups_completed_count += 1

            # Dispatch notification
            OwnerReporter.send_room_report(
                bot,
                guild.id,
                event="Dynamic Voice Room Cleaned Up",
                action_taken=f"Automatically deleted empty temporary VC **#{vc.name}** ({reason})",
                details={
                    "Voice Channel ID": f"`{vc.id}`",
                    "Owner ID": f"`{room.owner_id}`",
                    "Total Completed": f"`{cls.cleanups_completed_count}`",
                },
            )
            return True, "Channel deleted and record purged successfully"

    # =========================================================================
    # RESTART RECOVERY
    # =========================================================================

    @classmethod
    async def reconcile_on_startup(cls, bot: SentinelBot) -> int:
        """
        Recovers dynamic voice rooms upon bot startup.
        - Deletes orphaned records whose channels no longer exist on Discord.
        - Marks occupied rooms ACTIVE.
        - Preserves pending EMPTY_WAITING rooms if due in future; cleans up overdue rooms immediately.
        """
        logger.info("Running Dynamic Voice Room restart reconciliation...")
        reconciled = 0
        try:
            rooms = await bot.db.get_all_dynamic_rooms()
            now = utcnow()

            for room in rooms:
                guild = bot.get_guild(room.guild_id)
                if not guild:
                    continue

                vc = guild.get_channel(room.voice_channel_id)
                if not isinstance(vc, discord.VoiceChannel):
                    # Channel already gone on Discord -> clean up panel and DB
                    logger.info(f"DVC_CLEANUP_RECOVERED_AFTER_RESTART channel {room.voice_channel_id} gone. Pruning.")
                    await DynamicVCControlManager.delete_room_panel(bot, guild, room.voice_channel_id)
                    reconciled += 1
                    continue

                occupant_count = len(vc.members)
                if occupant_count > 0:
                    # Occupants present -> ensure room is ACTIVE
                    if room.cleanup_status != CleanupStatus.ACTIVE or room.status != "active":
                        await bot.db.update_dynamic_room(
                            room.voice_channel_id,
                            cleanup_status=CleanupStatus.ACTIVE,
                            empty_since=None,
                            cleanup_due_at=None,
                            status="active",
                            last_empty_at=None,
                        )
                    await DynamicVCControlManager.update_room_panel(bot, guild, room.voice_channel_id)
                else:
                    # Empty channel
                    due_dt: Optional[datetime.datetime] = None
                    if room.cleanup_due_at:
                        try:
                            due_dt = datetime.datetime.fromisoformat(room.cleanup_due_at)
                        except Exception:
                            due_dt = None

                    if due_dt and due_dt > now:
                        # Due time is in the future: preserve EMPTY_WAITING state
                        rem = (due_dt - now).total_seconds()
                        logger.info(
                            f"DVC_CLEANUP_RECOVERED_AFTER_RESTART room #{vc.name} ({vc.id}) "
                            f"still waiting for cleanup in {rem:.1f}s. Preserving countdown."
                        )
                        if room.cleanup_status != CleanupStatus.EMPTY_WAITING:
                            await bot.db.update_dynamic_room(
                                room.voice_channel_id,
                                cleanup_status=CleanupStatus.EMPTY_WAITING,
                                status="empty_countdown",
                            )
                        await DynamicVCControlManager.update_room_panel(bot, guild, room.voice_channel_id)
                    else:
                        # Due time is already past or was never set: execute cleanup immediately!
                        logger.info(
                            f"DVC_CLEANUP_RECOVERED_AFTER_RESTART room #{vc.name} ({vc.id}) "
                            f"cleanup overdue. Deleting immediately."
                        )
                        success, _ = await cls.execute_room_cleanup(
                            bot,
                            room.voice_channel_id,
                            reason="Overdue cleanup recovered on bot startup",
                        )
                        if success:
                            reconciled += 1

            logger.info(f"Dynamic Voice Room restart reconciliation complete. {reconciled} items reconciled.")
        except Exception as e:
            logger.error(f"Error during Dynamic Voice Room startup recovery: {e}", exc_info=True)

        return reconciled

    # =========================================================================
    # DIAGNOSTICS & MANUAL CLEANUP
    # =========================================================================

    @classmethod
    async def get_system_status(cls, bot: SentinelBot, guild_id: Optional[int] = None) -> Dict[str, Any]:
        """Collects complete operational status and inventory of dynamic rooms."""
        rooms = await bot.db.get_all_dynamic_rooms(guild_id)
        now = utcnow()

        active_count = 0
        empty_waiting_count = 0
        overdue_count = 0
        orphaned_count = 0
        protected_count = 0
        pending_rooms: List[Dict[str, Any]] = []

        for r in rooms:
            guild = bot.get_guild(r.guild_id)
            vc = guild.get_channel(r.voice_channel_id) if guild else None

            is_orphaned = vc is None or not isinstance(vc, discord.VoiceChannel)
            if is_orphaned:
                orphaned_count += 1
                continue

            members_count = len(vc.members)
            is_protected = False
            if r.protected_until:
                try:
                    is_protected = datetime.datetime.fromisoformat(r.protected_until) > now
                except Exception:
                    pass

            if is_protected:
                protected_count += 1

            if members_count > 0:
                active_count += 1
            else:
                due_dt = None
                if r.cleanup_due_at:
                    try:
                        due_dt = datetime.datetime.fromisoformat(r.cleanup_due_at)
                    except Exception:
                        pass

                is_overdue = due_dt is not None and due_dt <= now
                if is_overdue:
                    overdue_count += 1
                else:
                    empty_waiting_count += 1

                pending_rooms.append({
                    "channel_name": vc.name,
                    "channel_id": vc.id,
                    "owner_id": r.owner_id,
                    "members": members_count,
                    "empty_since": r.empty_since or r.last_empty_at or "Unknown",
                    "cleanup_due_at": r.cleanup_due_at or "Immediate",
                    "cleanup_status": r.cleanup_status or "EMPTY_WAITING",
                    "is_overdue": is_overdue,
                    "is_protected": is_protected,
                })

        overall_health = "HEALTHY"
        if cls.cleanups_failed_count > 0 and cls.cleanups_completed_count == 0:
            overall_health = "FAILED"
        elif overdue_count > 5 or orphaned_count > 5:
            overall_health = "DEGRADED"

        return {
            "health": overall_health,
            "total_rooms": len(rooms),
            "active_rooms": active_count,
            "empty_waiting": empty_waiting_count,
            "overdue": overdue_count,
            "orphaned": orphaned_count,
            "protected": protected_count,
            "last_scan": cls.last_scan_time.strftime("%Y-%m-%d %H:%M:%S UTC") if cls.last_scan_time else "Never",
            "last_success": cls.last_successful_cleanup.strftime("%Y-%m-%d %H:%M:%S UTC") if cls.last_successful_cleanup else "None",
            "last_failure": cls.last_cleanup_failure.strftime("%Y-%m-%d %H:%M:%S UTC") if cls.last_cleanup_failure else "None",
            "total_completed": cls.cleanups_completed_count,
            "total_failed": cls.cleanups_failed_count,
            "pending_rooms": pending_rooms,
        }

    @classmethod
    async def run_manual_cleanup(
        cls,
        bot: SentinelBot,
        guild_id: Optional[int] = None,
        guild: Optional[discord.Guild] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Scans all dynamic rooms and purges empty, overdue, or orphaned channels.
        Used by /tempvoice cleanup and natural language commands.
        """
        target_guild_id = guild.id if guild else guild_id
        rooms = await bot.db.get_all_dynamic_rooms(target_guild_id)
        now = utcnow()
        purged = 0
        skipped = 0
        errors = 0

        for r in rooms:
            target_guild = guild if (guild and guild.id == r.guild_id) else bot.get_guild(r.guild_id)
            if not target_guild:
                continue

            vc = target_guild.get_channel(r.voice_channel_id)
            if not isinstance(vc, discord.VoiceChannel):
                # Orphaned
                await DynamicVCControlManager.delete_room_panel(bot, target_guild, r.voice_channel_id)
                purged += 1
                continue

            # Check if empty or forced
            if len(vc.members) == 0 or force:
                success, msg = await cls.execute_room_cleanup(
                    bot,
                    r.voice_channel_id,
                    guild=target_guild,
                    reason="Manual administrator cleanup request",
                    force=force,
                )
                if success:
                    purged += 1
                else:
                    errors += 1
            else:
                skipped += 1

        return {
            "total_scanned": len(rooms),
            "purged": purged,
            "skipped": skipped,
            "errors": errors,
        }
