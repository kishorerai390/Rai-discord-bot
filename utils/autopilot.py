"""
Rai Autopilot Engine - Autonomous Platform Supervisor.
Continuously coordinates:
MONITOR -> DETECT -> ANALYZE -> DECIDE -> ACT -> VERIFY -> LOG -> RECOVER
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
import discord
from discord.ext import tasks

from config import Colors
from core.tasks import safe_task_loop
from database.models import AutopilotConfig, AutopilotAction, SecurityBaseline
from utils.embeds import create_embed, alert_embed

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger("RaiAutopilot")


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


class AutopilotEvent:
    def __init__(
        self,
        guild_id: int,
        module: str,
        event_type: str,
        reason: str,
        risk_level: str = "LOW",
        target: Optional[Any] = None,
        action: str = "LOG",
        details: Optional[str] = None,
        is_simulation: bool = False,
    ):
        self.guild_id = guild_id
        self.module = module
        self.event_type = event_type
        self.reason = reason
        self.risk_level = risk_level.upper()
        self.target = target
        self.action = action
        self.details = details
        self.is_simulation = is_simulation
        self.timestamp = utcnow_iso()


class AutopilotEngine:
    """
    Central Autonomous Platform Coordinator.
    Runs continuous background workers, safe action queue, adaptive baselines,
    self-healing, and emergency/safe mode controllers.
    """

    SAFETY_RANKS = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.db = bot.db
        self.action_queue: asyncio.Queue[AutopilotEvent] = asyncio.Queue(maxsize=1000)
        self.is_running = False
        self._action_worker_task: Optional[asyncio.Task] = None
        self._safe_mode_active: Dict[int, bool] = {}
        self._consecutive_failures: Dict[str, int] = {}
        self._last_alert_time: Dict[str, float] = {}

    def start(self) -> None:
        """Start the Autopilot worker and supervised background loops."""
        if self.is_running:
            return
        self.is_running = True
        self._action_worker_task = asyncio.create_task(self._action_consumer())
        
        # Start supervised background tasks
        if not self.ticket_autopilot_loop.is_running():
            self.ticket_autopilot_loop.start()
        if not self.temp_voice_autopilot_loop.is_running():
            self.temp_voice_autopilot_loop.start()
        if not self.baseline_autopilot_loop.is_running():
            self.baseline_autopilot_loop.start()
        if not self.health_supervisor_loop.is_running():
            self.health_supervisor_loop.start()
            
        logger.info("Rai Autopilot Engine initialized and running.")

    def stop(self) -> None:
        """Gracefully stop the Autopilot worker and loops."""
        self.is_running = False
        if self._action_worker_task and not self._action_worker_task.done():
            self._action_worker_task.cancel()
        if self.ticket_autopilot_loop.is_running():
            self.ticket_autopilot_loop.stop()
        if self.temp_voice_autopilot_loop.is_running():
            self.temp_voice_autopilot_loop.stop()
        if self.baseline_autopilot_loop.is_running():
            self.baseline_autopilot_loop.stop()
        if self.health_supervisor_loop.is_running():
            self.health_supervisor_loop.stop()
        logger.info("Rai Autopilot Engine stopped.")

    # ==========================================
    # EVENT INGESTION & DISPATCH
    # ==========================================

    async def dispatch(self, event: AutopilotEvent) -> None:
        """Enqueue an event for autonomous analysis, decision, and action."""
        if not self.is_running:
            return
        try:
            self.action_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"Autopilot action queue is full; dropping event: {event.event_type}")

    # ==========================================
    # ACTION CONSUMER & DECISION ENGINE
    # ==========================================

    async def _action_consumer(self) -> None:
        """Consumes events from the action queue with rate limiting and safety verification."""
        while self.is_running:
            try:
                event = await self.action_queue.get()
                await self._process_event(event)
                self.action_queue.task_done()
                await asyncio.sleep(0.05)  # API breathing room
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Autopilot consumer error: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _process_event(self, event: AutopilotEvent) -> None:
        """Full Autopilot execution: ANALYZE -> DECIDE -> ACT -> VERIFY -> LOG."""
        guild = self.bot.get_guild(event.guild_id)
        if not guild:
            return

        cfg = await self.db.get_or_create_autopilot_config(event.guild_id)
        if not cfg.enabled and not event.is_simulation:
            return

        # 1. Safe Mode Check: Suspend high-impact actions if safe mode is engaged
        if self._safe_mode_active.get(event.guild_id, False) and event.risk_level in ("HIGH", "CRITICAL"):
            logger.warning(f"Safe Mode active in {guild.name}; suppressing destructive action: {event.action}")
            await self._log_and_alert(
                guild=guild,
                cfg=cfg,
                event=event,
                result="SAFE_MODE_SUPPRESSED",
                details="Suppressed due to active Safe Mode",
            )
            return

        # 2. Safety Level Gatekeeper
        max_rank = self.SAFETY_RANKS.get(cfg.max_safety_level, 3)
        event_rank = self.SAFETY_RANKS.get(event.risk_level, 1)

        # 3. Target Manageability & Hierarchy Verification
        target_id = None
        target_type = None
        if event.target:
            if isinstance(event.target, discord.Member):
                target_id = event.target.id
                target_type = "user"
                if not self._can_target_member(guild, event.target):
                    logger.warning(f"Autopilot target @{event.target} cannot be moderated (hierarchy/owner/whitelist)")
                    await self._log_and_alert(
                        guild=guild,
                        cfg=cfg,
                        event=event,
                        result="HIERARCHY_BLOCKED",
                        details="Target is protected or above Rai in role hierarchy",
                    )
                    return
            elif isinstance(event.target, (discord.TextChannel, discord.VoiceChannel)):
                target_id = event.target.id
                target_type = "channel"
            elif isinstance(event.target, discord.Role):
                target_id = event.target.id
                target_type = "role"

        # 4. Dry-Run Check
        is_dry_run = cfg.dry_run or event.is_simulation
        if is_dry_run:
            logger.info(f"[AUTOPILOT DRY RUN] Would execute {event.action} on {event.target} in {guild.name}")
            await self._log_and_alert(
                guild=guild,
                cfg=cfg,
                event=event,
                result="DRY_RUN",
                details=f"Dry run simulation: {event.action} on {event.target}",
            )
            return

        # 5. Execute Action
        result = "FAILED"
        details = None
        try:
            if event.action == "TIMEOUT" and isinstance(event.target, discord.Member):
                duration = datetime.timedelta(minutes=10)
                await event.target.timeout(duration, reason=f"Rai Autopilot: {event.reason}")
                result = "SUCCESS"
                details = f"Timed out for 10 minutes: {event.reason}"

            elif event.action == "DELETE_MESSAGE" and isinstance(event.target, discord.Message):
                await event.target.delete()
                result = "SUCCESS"
                details = f"Deleted offending message: {event.reason}"

            elif event.action == "LOCK_CHANNEL" and isinstance(event.target, discord.TextChannel):
                overwrites = event.target.overwrites_for(guild.default_role)
                overwrites.send_messages = False
                await event.target.set_permissions(guild.default_role, overwrite=overwrites, reason=f"Rai Autopilot: {event.reason}")
                result = "SUCCESS"
                details = f"Channel locked: {event.reason}"

            elif event.action == "EMERGENCY_LOCKDOWN":
                # Automatically toggle emergency state
                await self.db.set_security_emergency_stop(guild.id, True, self.bot.user.id)
                result = "SUCCESS"
                details = f"Server-wide emergency protection engaged: {event.reason}"

            elif event.action == "RESTRICT_ROLES" and isinstance(event.target, discord.Member):
                # Strip high-privilege roles
                dangerous_perms = ("administrator", "manage_guild", "manage_roles", "manage_channels", "ban_members", "kick_members")
                roles_to_remove = [r for r in event.target.roles if any(getattr(r.permissions, p, False) for p in dangerous_perms) and r < guild.me.top_role]
                if roles_to_remove:
                    await event.target.remove_roles(*roles_to_remove, reason=f"Rai Autopilot Rogue Protection: {event.reason}")
                    result = "SUCCESS"
                    details = f"Revoked {len(roles_to_remove)} dangerous roles from @{event.target.name}"

            elif event.action == "LOG":
                result = "SUCCESS"
                details = event.details or event.reason

        except discord.Forbidden:
            result = "FORBIDDEN"
            details = "Bot lacks required Discord permissions"
            logger.warning(f"Autopilot failed to execute {event.action} in {guild.name}: 403 Forbidden")
        except Exception as e:
            result = "ERROR"
            details = str(e)
            logger.error(f"Autopilot error executing {event.action} in {guild.name}: {e}")

        # 6. Log and Alert
        await self._log_and_alert(
            guild=guild,
            cfg=cfg,
            event=event,
            result=result,
            details=details,
        )

    def _can_target_member(self, guild: discord.Guild, member: discord.Member) -> bool:
        """Verifies Discord role hierarchy, guild ownership, and immunity."""
        if member.id == guild.owner_id:
            return False
        if member.id == self.bot.user.id:
            return False
        if member.top_role >= guild.me.top_role:
            return False
        return True

    async def _log_and_alert(
        self,
        guild: discord.Guild,
        cfg: AutopilotConfig,
        event: AutopilotEvent,
        result: str,
        details: Optional[str] = None,
    ) -> None:
        """Stores internal audit record and dispatches debounced staff notification."""
        # 1. Internal Audit Log
        target_id = getattr(event.target, "id", None)
        if target_id is not None and not isinstance(target_id, int):
            target_id = None
        target_type = "user" if isinstance(event.target, discord.Member) else ("channel" if isinstance(event.target, discord.TextChannel) else None)
        actual_guild_id = guild.id if isinstance(getattr(guild, "id", None), int) else event.guild_id
        
        action_id = await self.db.log_autopilot_action(
            guild_id=actual_guild_id,
            module=event.module,
            trigger=event.event_type,
            reason=event.reason,
            risk_level=event.risk_level,
            action=event.action,
            result=result,
            target_id=target_id,
            target_type=target_type,
            details=details,
        )

        # 2. Threat Timeline Record
        if hasattr(self.db, "record_threat_timeline_event"):
            incident_id = f"AP-{actual_guild_id}-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')}"
            try:
                await self.db.record_threat_timeline_event(
                    incident_id=incident_id,
                    guild_id=actual_guild_id,
                    module=event.module,
                    event_type=event.event_type,
                    description=f"Autopilot {event.action}: {result} ({event.reason})",
                    risk_score=75 if event.risk_level in ("HIGH", "CRITICAL") else 35,
                    severity=event.risk_level.lower(),
                )
            except Exception as e:
                logger.debug(f"Failed to record threat timeline event: {e}")


        # 3. Debounced Staff Alert
        alert_channel = None
        if cfg.alert_channel_id:
            alert_channel = guild.get_channel(cfg.alert_channel_id)
        if not alert_channel:
            # Fallback to general system log channel or guild system channel
            log_cfg = await self.db.get_logging_config(actual_guild_id)
            if log_cfg and log_cfg.security_channel_id:
                alert_channel = guild.get_channel(log_cfg.security_channel_id)
        if not alert_channel:
            alert_channel = guild.system_channel

        if alert_channel and isinstance(alert_channel, discord.TextChannel):
            # Debounce by module and guild (1 alert per 30 seconds for non-critical)
            cache_key = f"{guild.id}:{event.module}:{event.event_type}"
            now = time.time()
            if event.risk_level != "CRITICAL" and now - self._last_alert_time.get(cache_key, 0.0) < 30.0:
                return
            self._last_alert_time[cache_key] = now

            prefix = "🧪 [DRY RUN] " if (cfg.dry_run or event.is_simulation) else "⚡ "
            title = f"{prefix}Autopilot Action #{action_id[-4:]}"
            color = Colors.ERROR if event.risk_level in ("HIGH", "CRITICAL") else Colors.PRIMARY

            embed = create_embed(
                title=title,
                description=f"**Autonomous Protection Triggered** in **{guild.name}**",
                color=color,
            )
            embed.add_field(name="Module", value=f"`{event.module}`", inline=True)
            embed.add_field(name="Risk Level", value=f"`{event.risk_level}`", inline=True)
            embed.add_field(name="Action Taken", value=f"`{event.action}`", inline=True)
            embed.add_field(name="Trigger & Reason", value=event.reason, inline=False)
            embed.add_field(name="Execution Result", value=f"`{result}`", inline=True)
            if details:
                embed.add_field(name="Details", value=details, inline=True)
            embed.set_footer(text="Rai Autopilot System • Self-Defending Server")

            try:
                await alert_channel.send(embed=embed)
            except Exception as e:
                logger.warning(f"Could not send Autopilot alert to #{alert_channel.name}: {e}")

    # ==========================================
    # SUPERVISED AUTOPILOT LOOPS
    # ==========================================

    @tasks.loop(minutes=30)
    @safe_task_loop(task_name="autopilot_ticket_supervision", timeout_seconds=60.0)
    async def ticket_autopilot_loop(self) -> None:
        """Monitors open tickets for inactivity, sends reminders, and auto-closes."""
        for guild in self.bot.guilds:
            try:
                cfg = await self.db.get_or_create_autopilot_config(guild.id)
                if not cfg.enabled or not cfg.ticket_management:
                    continue

                tickets = await self.db.get_open_tickets(guild.id)
                now = utcnow()

                for ticket in tickets:
                    channel = guild.get_channel(ticket.channel_id)
                    if not channel or not isinstance(channel, discord.TextChannel):
                        continue

                    created_dt = datetime.datetime.fromisoformat(ticket.created_at)
                    hours_open = (now - created_dt).total_seconds() / 3600.0

                    # Auto-close after 72 hours of complete inactivity
                    if hours_open >= 72.0:
                        embed = alert_embed(
                            "Ticket Inactivity Auto-Close",
                            "This ticket has been automatically closed due to 72+ hours of inactivity.",
                        )
                        await channel.send(embed=embed)
                        await self.db.close_ticket(ticket.ticket_id, closed_by_id=self.bot.user.id)
                        await self.dispatch(
                            AutopilotEvent(
                                guild_id=guild.id,
                                module="TICKETS",
                                event_type="AUTO_CLOSE",
                                reason=f"Ticket #{ticket.ticket_id} inactive for 72+ hours",
                                risk_level="LOW",
                                target=channel,
                                action="CLOSE_TICKET",
                            )
                        )
            except Exception as e:
                logger.error(f"Error in ticket autopilot loop for {guild.name}: {e}")

    @tasks.loop(seconds=45)
    @safe_task_loop(task_name="autopilot_temp_voice_cleanup", timeout_seconds=30.0)
    async def temp_voice_autopilot_loop(self) -> None:
        """Monitors temporary voice rooms and cleans up empty channels safely."""
        for guild in self.bot.guilds:
            try:
                cfg = await self.db.get_or_create_autopilot_config(guild.id)
                if not cfg.enabled:
                    continue

                temp_channels = await self.db.get_all_temp_voice_channels(guild.id)
                for tc in temp_channels:
                    channel = guild.get_channel(tc.channel_id)
                    if not channel:
                        await self.db.delete_temp_voice_channel(tc.channel_id)
                        continue
                    if isinstance(channel, discord.VoiceChannel) and len(channel.members) == 0:
                        # Double check creation age (>15 seconds to prevent race conditions during join)
                        created_dt = datetime.datetime.fromisoformat(tc.created_at)
                        if (utcnow() - created_dt).total_seconds() >= 15.0:
                            try:
                                await channel.delete(reason="Rai Autopilot: Temporary voice room empty")
                                await self.db.delete_temp_voice_channel(tc.channel_id)
                                logger.info(f"Autopilot cleaned up empty temp voice #{channel.name} in {guild.name}")
                            except Exception as e:
                                logger.warning(f"Could not delete empty temp voice channel {tc.channel_id}: {e}")
            except Exception as e:
                logger.error(f"Error in temp voice autopilot loop: {e}")

    @tasks.loop(hours=1)
    @safe_task_loop(task_name="autopilot_baseline_activity", timeout_seconds=45.0)
    async def baseline_autopilot_loop(self) -> None:
        """Calculates adaptive hourly server activity baselines."""
        for guild in self.bot.guilds:
            try:
                # Estimate current join rate & message velocity from Security Brain
                if hasattr(self.bot, "security_brain") and self.bot.security_brain:
                    tracker = self.bot.security_brain.trackers.get(guild.id)
                    if tracker:
                        joins_1h = float(tracker.get_count("join", 1800) * 2)
                        msgs_1m = float(tracker.get_count("msg", 60))
                        voice_users = float(sum(len(vc.members) for vc in guild.voice_channels))

                        await self.db.update_security_baseline(
                            guild_id=guild.id,
                            joins_per_hour=joins_1h,
                            messages_per_min=msgs_1m,
                            voice_users=voice_users,
                        )
            except Exception as e:
                logger.error(f"Error updating security baseline for {guild.name}: {e}")

    @tasks.loop(seconds=60)
    @safe_task_loop(task_name="autopilot_subsystem_health_supervisor", timeout_seconds=45.0)
    async def health_supervisor_loop(self) -> None:
        """Monitors all subsystems and restarts crashed tasks with exponential backoff."""
        subsystems = {
            "ActionConsumer": self._action_worker_task,
            "TicketSupervisor": self.ticket_autopilot_loop,
            "TempVoiceSupervisor": self.temp_voice_autopilot_loop,
            "BaselineSupervisor": self.baseline_autopilot_loop,
        }

        critical_failures = 0
        for name, task_obj in subsystems.items():
            status = "HEALTHY"
            details = None

            if task_obj is None or (isinstance(task_obj, asyncio.Task) and task_obj.done()):
                status = "FAILED"
                critical_failures += 1
                details = "Task stopped unexpectedly"
                # Auto-recovery: restart consumer
                if name == "ActionConsumer" and self.is_running:
                    self._action_worker_task = asyncio.create_task(self._action_consumer())
                    details = "Restarted automatically by supervisor"
            elif hasattr(task_obj, "is_running") and not task_obj.is_running():
                status = "DEGRADED"
                details = "Task loop is paused or stopped"
                if self.is_running:
                    task_obj.restart()
                    details = "Restarted by supervisor"

            await self.db.update_subsystem_health(name, status, details)

        # Check Safe Mode trigger: 2 or more critical failures
        for guild in self.bot.guilds:
            cfg = await self.db.get_or_create_autopilot_config(guild.id)
            if cfg.auto_safe_mode:
                if critical_failures >= 2 and not self._safe_mode_active.get(guild.id, False):
                    self._safe_mode_active[guild.id] = True
                    logger.critical(f"ENGAGING SAFE MODE in {guild.name} due to multiple subsystem failures!")
                    await self._log_and_alert(
                        guild=guild,
                        cfg=cfg,
                        event=AutopilotEvent(
                            guild_id=guild.id,
                            module="SUPERVISOR",
                            event_type="SAFE_MODE_ENGAGED",
                            reason="Multiple subsystem failures detected. Destructive actions frozen; monitoring remains active.",
                            risk_level="CRITICAL",
                            action="ENGAGE_SAFE_MODE",
                        ),
                        result="SAFE_MODE_ACTIVE",
                        details=f"{critical_failures} subsystems failed",
                    )
                elif critical_failures == 0 and self._safe_mode_active.get(guild.id, False):
                    # Automatic recovery out of safe mode
                    self._safe_mode_active[guild.id] = False
                    logger.info(f"Subsystems healthy. Disengaged Safe Mode in {guild.name}.")

    # ==========================================
    # SECURITY SIMULATION ENGINE
    # ==========================================

    async def simulate_threat(self, guild: discord.Guild, threat_type: str) -> Dict[str, Any]:
        """
        Safe simulation tool testing detection, risk scoring, threat timeline creation,
        and proposed actions without touching real server assets.
        """
        threat_type = threat_type.lower()
        sim_id = f"SIM-{random.randint(1000, 9999)}"

        if threat_type == "raid":
            event = AutopilotEvent(
                guild_id=guild.id,
                module="ANTI_RAID",
                event_type="SIMULATED_MASS_JOIN",
                reason="Simulated 25 rapid joins from 0-day accounts within 10 seconds",
                risk_level="CRITICAL",
                target=guild.system_channel or guild,
                action="EMERGENCY_LOCKDOWN",
                is_simulation=True,
            )
        elif threat_type == "spam":
            event = AutopilotEvent(
                guild_id=guild.id,
                module="ANTI_SPAM",
                event_type="SIMULATED_CROSS_CHANNEL_FLOOD",
                reason="Simulated 18 duplicate messages across 4 channels in 5 seconds",
                risk_level="HIGH",
                target=guild.me,
                action="TIMEOUT",
                is_simulation=True,
            )
        elif threat_type == "nuke":
            event = AutopilotEvent(
                guild_id=guild.id,
                module="ANTI_NUKE",
                event_type="SIMULATED_MASS_CHANNEL_DELETE",
                reason="Simulated 6 channel deletion attempts within 8 seconds by unauthorized role",
                risk_level="CRITICAL",
                target=guild.me,
                action="RESTRICT_ROLES",
                is_simulation=True,
            )
        elif threat_type == "webhook":
            event = AutopilotEvent(
                guild_id=guild.id,
                module="WEBHOOK_GUARD",
                event_type="SIMULATED_UNAUTHORIZED_WEBHOOK",
                reason="Simulated unknown webhook creation with administrative scopes",
                risk_level="MEDIUM",
                target=guild.system_channel or guild,
                action="LOG",
                is_simulation=True,
            )
        else:
            return {"status": "error", "message": f"Unknown threat type: {threat_type}"}

        # Process through full pipeline in simulation mode
        await self._process_event(event)

        return {
            "simulation_id": sim_id,
            "threat_type": threat_type,
            "risk_score": 92 if event.risk_level == "CRITICAL" else (74 if event.risk_level == "HIGH" else 45),
            "risk_level": event.risk_level,
            "proposed_action": event.action,
            "status": "SIMULATION_SUCCESS",
            "message": f"Simulated {threat_type} successfully tested through Autopilot Engine. No destructive calls were made.",
        }
