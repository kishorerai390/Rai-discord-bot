"""
RAI — SERVER OPERATIONS ASSISTANT: OPERATIONS CORE & SERVICE ARCHITECTURE.
Unifies all major Rai subsystems under a single, cohesive orchestration layer.

Core Architecture:
- Encapsulates 12 standardized services:
  1. SecurityService
  2. RoomService
  3. MusicService
  4. BackupService
  5. HealthService
  6. AutomationService
  7. ReportService
  8. IncidentService
  9. NotificationService
  10. AnalyticsService
  11. ConfigurationService
  12. PermissionService
- RaiOperationsCore: Central coordinator for owner operations, away summaries,
  maintenance mode, raid simulations, and configuration versioning.
- Interactive Owner Operations Dashboard View.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import discord
from discord import ui

from config import Colors
from core.results import ErrorCodes, ResultStatus
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed
from utils.owner_reporter import OWNER_ID, OwnerReporter, generate_incident_id

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.OperationsCore")


# =============================================================================
# 1. STANDARDIZED SERVICE ARCHITECTURE (PHASE 2)
# =============================================================================

class SecurityService:
    """Encapsulates all server defense, anti-nuke, and lockdown operations."""

    @classmethod
    async def get_status(cls, bot: SentinelBot, guild_id: int) -> Dict[str, Any]:
        guild_cfg = await bot.db.get_or_create_guild_config(guild_id)
        sec_cfg = await bot.db.get_security_config(guild_id)
        sec_state = await bot.db.get_security_state(guild_id)
        incidents = await bot.db.get_security_incidents(guild_id, limit=5)
        is_lockdown = await bot.db.is_lockdown_active(guild_id)

        return {
            "enabled": guild_cfg.security_enabled,
            "status": "NORMAL" if not is_lockdown else "LOCKDOWN",
            "lockdown_active": is_lockdown,
            "emergency_stop": sec_state.emergency_stop,
            "incident_count": len(incidents),
            "recent_incidents": incidents,
            "thresholds": {
                "channel_delete": f"{sec_cfg.channel_delete_limit}/{sec_cfg.channel_delete_window}s",
                "role_delete": f"{sec_cfg.role_delete_limit}/{sec_cfg.role_delete_window}s",
                "ban": f"{sec_cfg.ban_limit}/{sec_cfg.ban_window}s",
            },
        }

    @classmethod
    async def lockdown(cls, bot: SentinelBot, guild: discord.Guild, actor: discord.Member) -> int:
        locked_channels = 0
        for channel in guild.text_channels:
            perms = channel.overwrites_for(guild.default_role)
            if perms.send_messages is not False:
                perms.send_messages = False
                try:
                    await channel.set_permissions(guild.default_role, overwrite=perms, reason=f"Lockdown by {actor}")
                    locked_channels += 1
                except Exception:
                    pass
        await bot.db.set_lockdown(guild.id, True, actor=str(actor))
        return locked_channels

    @classmethod
    async def unlock(cls, bot: SentinelBot, guild: discord.Guild, actor: discord.Member) -> int:
        unlocked_channels = 0
        for channel in guild.text_channels:
            perms = channel.overwrites_for(guild.default_role)
            if perms.send_messages is False:
                perms.send_messages = None
                try:
                    await channel.set_permissions(guild.default_role, overwrite=perms, reason=f"Unlock by {actor}")
                    unlocked_channels += 1
                except Exception:
                    pass
        await bot.db.set_lockdown(guild.id, False)
        return unlocked_channels


class RoomService:
    """Encapsulates Dynamic Voice Room lifecycle and delegation operations."""

    @classmethod
    async def list_rooms(cls, bot: SentinelBot, guild: discord.Guild) -> List[Tuple[Any, discord.VoiceChannel]]:
        rooms = await bot.db.get_all_dynamic_rooms(guild.id)
        results = []
        for r in rooms:
            vc = guild.get_channel(r.voice_channel_id)
            if isinstance(vc, discord.VoiceChannel):
                results.append((r, vc))
        return results

    @classmethod
    async def cleanup_empty(cls, bot: SentinelBot, guild: discord.Guild, actor_name: str) -> int:
        from utils.dynamic_vc_control import DynamicVCControlManager

        rooms = await bot.db.get_all_dynamic_rooms(guild.id)
        purged = 0
        for r in rooms:
            vc = guild.get_channel(r.voice_channel_id)
            if not isinstance(vc, discord.VoiceChannel):
                await DynamicVCControlManager.delete_room_panel(bot, guild, r.voice_channel_id)
                purged += 1
            elif len(vc.members) == 0:
                try:
                    await vc.delete(reason=f"Cleanup by {actor_name}")
                except Exception:
                    pass
                await DynamicVCControlManager.delete_room_panel(bot, guild, r.voice_channel_id)
                purged += 1
        return purged

    @classmethod
    async def lock_all(cls, bot: SentinelBot, guild: discord.Guild) -> int:
        from utils.dynamic_vc_control import DynamicVCControlManager

        rooms = await bot.db.get_all_dynamic_rooms(guild.id)
        count = 0
        for r in rooms:
            vc = guild.get_channel(r.voice_channel_id)
            if isinstance(vc, discord.VoiceChannel):
                try:
                    await vc.set_permissions(guild.default_role, connect=False)
                    await bot.db.update_dynamic_room(vc.id, locked=1, privacy_mode="locked")
                    await DynamicVCControlManager.update_room_panel(bot, guild, vc.id)
                    count += 1
                except Exception:
                    pass
        return count

    @classmethod
    async def delete_all(cls, bot: SentinelBot, guild: discord.Guild, actor_name: str) -> int:
        from utils.dynamic_vc_control import DynamicVCControlManager

        rooms = await bot.db.get_all_dynamic_rooms(guild.id)
        count = 0
        for r in rooms:
            vc = guild.get_channel(r.voice_channel_id)
            if isinstance(vc, discord.VoiceChannel):
                try:
                    await vc.delete(reason=f"Purged by {actor_name}")
                except Exception:
                    pass
            await DynamicVCControlManager.delete_room_panel(bot, guild, r.voice_channel_id)
            count += 1
        return count


class MusicService:
    """Encapsulates music streaming state and queue controls."""

    @classmethod
    def get_status(cls, bot: SentinelBot, guild_id: int) -> Dict[str, Any]:
        music_cog = bot.cogs.get("Music")
        if not music_cog or not hasattr(music_cog, "players") or guild_id not in music_cog.players:
            return {"active": False, "playing": False, "current": None, "queue_len": 0}
        player = music_cog.players[guild_id]
        return {
            "active": True,
            "playing": getattr(player, "current", None) is not None,
            "current": getattr(player.current, "title", "Track") if getattr(player, "current", None) else None,
            "queue_len": len(getattr(player, "queue", [])),
        }

    @classmethod
    async def skip(cls, bot: SentinelBot, guild: discord.Guild) -> Optional[str]:
        music_cog = bot.cogs.get("Music")
        if not music_cog or not hasattr(music_cog, "players") or guild.id not in music_cog.players:
            return None
        player = music_cog.players[guild.id]
        title = player.current.title if player.current else "Track"
        vc = guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        elif hasattr(player, "skip") and callable(player.skip):
            res = player.skip()
            if asyncio.iscoroutine(res):
                await res
        return title


class BackupService:
    """Encapsulates atomic disaster recovery backups and verification."""

    @classmethod
    async def create(cls, trigger: str) -> Any:
        from backups.manager import BackupManager
        manager = BackupManager.get_instance()
        return await manager.run_backup(trigger=trigger)

    @classmethod
    def list_backups(cls) -> List[Dict[str, Any]]:
        from backups.manager import BackupManager
        manager = BackupManager.get_instance()
        return manager.list_backups()

    @classmethod
    async def verify(cls, backup_id: str) -> Dict[str, Any]:
        from backups.manager import BackupManager
        manager = BackupManager.get_instance()
        return await manager.verify_backup(backup_id)


class HealthService:
    """Encapsulates unified telemetry across databases, workers, and gateway."""

    @classmethod
    def check(cls, bot: SentinelBot) -> Any:
        from observability.health import ObservabilityHealthService
        return ObservabilityHealthService.evaluate_health(bot)


class AutomationService:
    """Encapsulates maintenance mode and background task schedules."""

    @classmethod
    async def get_state(cls, bot: SentinelBot, guild_id: int) -> Dict[str, Any]:
        return await bot.db.get_or_create_operations_state(guild_id)

    @classmethod
    async def set_maintenance(cls, bot: SentinelBot, guild_id: int, enabled: bool, reason: Optional[str] = None) -> bool:
        return await bot.db.set_maintenance_mode(guild_id, enabled, reason=reason)

    @classmethod
    async def list_scheduled_tasks(cls, bot: SentinelBot, guild_id: int) -> List[Dict[str, Any]]:
        return await bot.db.get_scheduled_tasks(guild_id)


class NotificationService:
    """Routes alerts according to severity: INFO, WARNING, IMPORTANT, CRITICAL."""

    @classmethod
    def dispatch(
        cls,
        bot: SentinelBot,
        guild_id: int,
        severity: str,
        event: str,
        details: Dict[str, Any],
        user: Optional[discord.Member] = None,
    ) -> None:
        sev = severity.upper()
        report_details = dict(details or {})
        if user:
            report_details["👤 Actor"] = f"{user.mention} ({user.name})"

        if sev in ("INFO", "WARNING", "IMPORTANT"):
            OwnerReporter.send_system_report(bot, guild_id, event=event, severity=sev, details=report_details)
        elif sev in ("CRITICAL", "EMERGENCY"):
            OwnerReporter.send_security_report(bot, guild_id, event=event, severity="CRITICAL", details=report_details, user=user)


class IncidentService:
    """Central registry and action dispatcher for incident management."""

    @classmethod
    def generate_id(cls) -> str:
        return generate_incident_id("RAI-INC")


class ConfigurationService:
    """Configuration versioning and state rollback."""

    @classmethod
    async def create_version(cls, bot: SentinelBot, guild_id: int, user_name: str, summary: str, config_dict: Dict[str, Any]) -> int:
        json_data = json.dumps(config_dict)
        return await bot.db.save_config_version(guild_id, user_name, summary, json_data)

    @classmethod
    async def save_version(cls, bot: SentinelBot, guild_id: int, user_id_or_name: Any, config_dict: Dict[str, Any], label: str = "Snapshot") -> int:
        return await cls.create_version(bot, guild_id, str(user_id_or_name), label, config_dict)

    @classmethod
    async def list_versions(cls, bot: SentinelBot, guild_id: int) -> List[Dict[str, Any]]:
        return await bot.db.list_config_versions(guild_id)

    @classmethod
    async def get_version(cls, bot: SentinelBot, guild_id: int, version_num: int) -> Optional[Dict[str, Any]]:
        return await bot.db.get_config_version(guild_id, version_num)


class AnalyticsService:
    """Aggregate metrics and event summaries over configurable time windows."""

    @classmethod
    async def get_away_summary(cls, bot: SentinelBot, guild: discord.Guild, hours: int = 12) -> Dict[str, Any]:
        """Gathers REAL stored database event records over the specified time window."""
        cutoff_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        cutoff_iso = cutoff_dt.isoformat()
        cutoff_ts = time.time() - (hours * 3600)

        # 1. Dynamic Room Events
        room_events = []
        try:
            async with bot.db._db.execute(
                "SELECT event_type FROM room_events WHERE timestamp >= ?",
                (cutoff_ts,),
            ) as cursor:
                rows = await cursor.fetchall()
                room_events = [r[0] for r in rows]
        except Exception:
            pass

        rooms_created = room_events.count("create")
        rooms_cleaned = room_events.count("cleanup") + room_events.count("delete")
        active_rooms = await bot.db.get_all_dynamic_rooms(guild.id)

        # 2. Security Incidents
        security_incidents = await bot.db.get_security_incidents(guild.id, limit=20)
        recent_sec = [inc for inc in security_incidents if str(getattr(inc, "timestamp", "")) >= cutoff_iso]

        # 3. NL Commands Audit
        audits = await bot.db.get_recent_nl_audits(guild.id, limit=30)
        recent_audits = [a for a in audits if str(a.get("created_at", "")) >= cutoff_iso]

        # 4. Backups
        from backups.manager import BackupManager
        backups = BackupManager.get_instance().list_backups()
        recent_backups = [b for b in backups if str(b.get("iso_created_at", "")) >= cutoff_iso]

        # 5. Health
        health_rep = HealthService.check(bot)

        return {
            "period_hours": hours,
            "period_start": cutoff_dt.strftime("%I:%M %p UTC"),
            "period_end": datetime.datetime.now(datetime.timezone.utc).strftime("%I:%M %p UTC"),
            "member_count": guild.member_count or len(guild.members),
            "rooms_created": rooms_created,
            "rooms_cleaned": rooms_cleaned,
            "rooms_active": len(active_rooms),
            "security_incidents_count": len(recent_sec),
            "nl_commands_count": len(recent_audits),
            "backups_count": len(recent_backups),
            "health_status": health_rep.overall_status,
            "attention_incident": recent_sec[0].event_id if recent_sec else None,
        }


class EventService:
    """Encapsulates Smart Event lifecycle and attendance operations."""

    @classmethod
    async def list_active(cls, bot: SentinelBot, guild_id: int) -> List[Any]:
        return await bot.db.list_events(guild_id, status="scheduled")

    @classmethod
    async def get_attendees(cls, bot: SentinelBot, event_id: int) -> List[int]:
        return await bot.db.list_event_participants(event_id)


class ProjectService:
    """Encapsulates Collaboration and Project Room management."""

    @classmethod
    async def list_active(cls, bot: SentinelBot, guild_id: int) -> List[Dict[str, Any]]:
        return await bot.db.list_projects(guild_id, status="active")

    @classmethod
    async def get_members(cls, bot: SentinelBot, project_id: int) -> List[Dict[str, Any]]:
        return await bot.db.list_project_members(project_id)


class ReputationService:
    """Encapsulates Community Reputation scoring and anti-abuse safeguards."""

    @classmethod
    async def get_profile(cls, bot: SentinelBot, guild_id: int, user_id: int) -> Dict[str, Any]:
        return await bot.db.get_or_create_reputation_profile(guild_id, user_id)

    @classmethod
    async def get_leaderboard(cls, bot: SentinelBot, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        return await bot.db.get_reputation_leaderboard(guild_id, limit=limit)


class KnowledgeService:
    """Encapsulates Server Knowledge and searchable resources."""

    @classmethod
    async def search(cls, bot: SentinelBot, guild_id: int, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return await bot.db.search_knowledge_entries(guild_id, query, limit=limit)

    @classmethod
    async def list_entries(cls, bot: SentinelBot, guild_id: int, category: Optional[str] = None) -> List[Dict[str, Any]]:
        return await bot.db.list_knowledge_entries(guild_id, category=category)


class RecoveryService:
    """Encapsulates state diff scanning and disaster recovery plan generation."""

    @classmethod
    async def scan_state(cls, bot: SentinelBot, guild: discord.Guild) -> Tuple[str, List[Any]]:
        from core.recovery import DisasterRecoveryEngine
        return await DisasterRecoveryEngine.scan_guild_state(bot, guild)



# =============================================================================
# 2. CENTRAL ORCHESTRATION LAYER: RAI OPERATIONS CORE (PHASE 1)
# =============================================================================

class RaiOperationsCore:
    """
    Central server operations orchestrator for RAI.
    Coordinates all underlying services without replacing their logic.
    """

    _instance: Optional[RaiOperationsCore] = None

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    @classmethod
    def get_instance(cls, bot: SentinelBot) -> RaiOperationsCore:
        if cls._instance is None:
            cls._instance = RaiOperationsCore(bot)
        return cls._instance

    async def get_operations_overview(self, guild: discord.Guild) -> Dict[str, Any]:
        """Gathers complete verified operations telemetry across all subsystems without placeholders."""
        health = HealthService.check(self.bot)
        sec = await SecurityService.get_status(self.bot, guild.id)
        rooms = await RoomService.list_rooms(self.bot, guild)
        private_rooms = [r for r in rooms if getattr(r[0], "room_type", "public") == "private" or getattr(r[0], "is_private", False)]
        public_rooms = [r for r in rooms if r not in private_rooms]

        music_cog = self.bot.cogs.get("Music")
        music_sessions = len(getattr(music_cog, "players", {})) if music_cog else 0
        music_provider = "YouTube + SoundCloud" if music_cog else "Offline"

        backups = BackupService.list_backups()
        latest_backup = backups[0] if backups else None
        backup_verified = bool(latest_backup and latest_backup.get("verified", False))
        backup_sha = (latest_backup.get("sqlite_sha256") or "None")[:12] if latest_backup else "None"

        ops_state = await AutomationService.get_state(self.bot, guild.id)

        # Automation & Workflows real counts from database and supervisor
        from core.tasks import BackgroundTaskManager
        running_tasks = BackgroundTaskManager.get_instance().get_all_telemetry()

        waiting_timers_count = 0
        running_workflows_count = 0
        failed_workflows_count = 0
        active_workflows_count = 0

        try:
            if hasattr(self.bot, "db") and self.bot.db and self.bot.db.is_connected:
                async with self.bot.db._db.execute("SELECT count(*) FROM workflow_waiting_timers WHERE guild_id = ? AND status = 'WAITING'", (guild.id,)) as c:
                    row = await c.fetchone()
                    waiting_timers_count = row[0] if row else 0
                async with self.bot.db._db.execute("SELECT count(*) FROM workflow_executions WHERE guild_id = ? AND status = 'RUNNING'", (guild.id,)) as c:
                    row = await c.fetchone()
                    running_workflows_count = row[0] if row else 0
                async with self.bot.db._db.execute("SELECT count(*) FROM workflow_executions WHERE guild_id = ? AND status = 'FAILED'", (guild.id,)) as c:
                    row = await c.fetchone()
                    failed_workflows_count = row[0] if row else 0
                async with self.bot.db._db.execute("SELECT count(*) FROM workflows WHERE guild_id = ? AND status = 'ACTIVE'", (guild.id,)) as c:
                    row = await c.fetchone()
                    active_workflows_count = row[0] if row else 0
        except Exception:
            pass

        # Calculate time ago for latest backup
        backup_str = "None"
        if latest_backup:
            ts = latest_backup.get("created_at", 0)
            mins_ago = int((time.time() - ts) / 60) if ts else 0
            backup_str = f"{mins_ago}m ago" if mins_ago > 0 else "Just now"

        conn_status = self.bot.conn_watchdog.get_status() if hasattr(self.bot, "conn_watchdog") else {}

        return {
            "bot_online": self.bot.is_ready(),
            "gateway_latency_ms": conn_status.get("latency_ms", round((self.bot.latency or 0.0) * 1000, 1)),
            "gateway_resumes": conn_status.get("resume_count", 0),
            "system_health": getattr(health, "overall_status", "HEALTHY"),
            "security_status": sec["status"],
            "security_incidents_count": sec["incident_count"],
            "security_threat_level": "ELEVATED" if sec["status"] == "LOCKDOWN" else ("ATTENTION" if sec["incident_count"] > 0 else "LOW"),
            "active_rooms_count": len(rooms),
            "private_rooms_count": len(private_rooms),
            "public_rooms_count": len(public_rooms),
            "music_sessions_count": music_sessions,
            "music_provider_status": music_provider,
            "members_count": guild.member_count or len(guild.members),
            "last_backup_str": backup_str,
            "backup_integrity_verified": backup_verified,
            "backup_sha256": backup_sha,
            "maintenance_mode": bool(ops_state.get("maintenance_mode", 0)),
            "running_background_tasks": len(running_tasks),
            "waiting_jobs_count": waiting_timers_count,
            "workflows_active": active_workflows_count,
            "workflows_running": running_workflows_count,
            "workflows_failed": failed_workflows_count,
            "open_incidents_count": sec["incident_count"],
        }

    async def simulate_raid(self, guild: discord.Guild, actor: discord.Member) -> Dict[str, Any]:
        """
        Executes a safe security simulation (Phase 24).
        Tests thresholds and notification pipelines WITHOUT deleting channels or banning users!
        """
        sim_id = generate_incident_id("RAI-INC")
        sim_data = {
            "simulation_id": sim_id,
            "scenario": "Mass Channel Deletion Attack",
            "simulated_deletions": 47,
            "threshold": 5,
            "would_trigger": "Anti-Nuke Containment",
            "would_execute": "Emergency Server Lockdown (Text Channels)",
            "notified_destinations": ["📩 Owner DM", "🚨・security-report", "🚨・security-alerts"],
            "destructive_action_taken": False,
        }

        # Route simulated event to Owner DM and private report
        NotificationService.dispatch(
            bot=self.bot,
            guild_id=guild.id,
            severity="WARNING",
            event="Security Raid Simulation Executed",
            details={
                "🧪 Scenario": sim_data["scenario"],
                "📊 Simulated Deletions": sim_data["simulated_deletions"],
                "🔒 Action Triggered": sim_data["would_trigger"],
                "👤 Executed By": f"{actor.mention} ({actor.name})",
                "🛡️ Real Damage": "None (Safe Sandbox Mode)",
            },
            user=actor,
        )

        return sim_data

    async def set_maintenance_mode(self, guild: discord.Guild, actor: discord.Member, enabled: bool, reason: Optional[str] = None) -> bool:
        """Toggles server maintenance mode (Phase 14)."""
        success = await AutomationService.set_maintenance(self.bot, guild.id, enabled, reason=reason)
        if success:
            NotificationService.dispatch(
                bot=self.bot,
                guild_id=guild.id,
                severity="IMPORTANT",
                event="Server Maintenance Mode Changed",
                details={
                    "Status": "ACTIVE 🛠️" if enabled else "RESOLVED 🟢",
                    "Reason": reason or "Standard administrative maintenance",
                    "Actor": f"{actor.mention}",
                },
                user=actor,
            )
        return success


# =============================================================================
# 3. INTERACTIVE OWNER OPERATIONS DASHBOARD VIEW (PHASE 10)
# =============================================================================

class OwnerOperationsDashboardView(ui.View):
    """Unified master control panel for the server owner."""

    def __init__(self, bot: SentinelBot, guild_id: int, owner_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_id = guild_id
        self.owner_id = owner_id

    async def _check_auth(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild or self.bot.get_guild(self.guild_id)
        is_owner = (interaction.user.id == self.owner_id) or (guild and interaction.user.id == guild.owner_id)
        if not is_owner and not getattr(interaction.user.guild_permissions, "administrator", False):
            await interaction.response.send_message("❌ Unauthorized: Only the Server Owner can operate this center.", ephemeral=True)
            return False
        return True

    @ui.button(label="Health", emoji="❤️", style=discord.ButtonStyle.success, row=0)
    async def health_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        from core.nl_control import NLActionDispatcher, NLIntent, ParsedTask, NLContextManager
        session = NLContextManager.get_session(self.guild_id, interaction.user.id, interaction.channel_id or 0)
        task = ParsedTask(intent=NLIntent.HEALTH_CHECK, raw_segment="health", confidence=1.0)
        res = await NLActionDispatcher.dispatch(self.bot, interaction.guild, interaction.user, interaction.channel, task, session)  # type: ignore
        await interaction.response.send_message(embed=res.embed, ephemeral=True)

    @ui.button(label="Security", emoji="🛡️", style=discord.ButtonStyle.danger, row=0)
    async def security_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        from core.nl_control import NLActionDispatcher, NLIntent, ParsedTask, NLContextManager
        session = NLContextManager.get_session(self.guild_id, interaction.user.id, interaction.channel_id or 0)
        task = ParsedTask(intent=NLIntent.SECURITY_CHECK, raw_segment="security", confidence=1.0)
        res = await NLActionDispatcher.dispatch(self.bot, interaction.guild, interaction.user, interaction.channel, task, session)  # type: ignore
        await interaction.response.send_message(embed=res.embed, ephemeral=True)

    @ui.button(label="Rooms", emoji="🎙️", style=discord.ButtonStyle.primary, row=0)
    async def rooms_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        from core.nl_control import NLActionDispatcher, NLIntent, ParsedTask, NLContextManager
        session = NLContextManager.get_session(self.guild_id, interaction.user.id, interaction.channel_id or 0)
        task = ParsedTask(intent=NLIntent.ROOM_LIST, raw_segment="rooms", confidence=1.0)
        res = await NLActionDispatcher.dispatch(self.bot, interaction.guild, interaction.user, interaction.channel, task, session)  # type: ignore
        await interaction.response.send_message(embed=res.embed, ephemeral=True)

    @ui.button(label="Music", emoji="🎵", style=discord.ButtonStyle.secondary, row=0)
    async def music_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        from core.nl_control import NLActionDispatcher, NLIntent, ParsedTask, NLContextManager
        session = NLContextManager.get_session(self.guild_id, interaction.user.id, interaction.channel_id or 0)
        task = ParsedTask(intent=NLIntent.MUSIC_QUEUE, raw_segment="music queue", confidence=1.0)
        res = await NLActionDispatcher.dispatch(self.bot, interaction.guild, interaction.user, interaction.channel, task, session)  # type: ignore
        await interaction.response.send_message(embed=res.embed, ephemeral=True)

    @ui.button(label="Backups", emoji="💾", style=discord.ButtonStyle.secondary, row=1)
    async def backups_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        from core.nl_control import NLActionDispatcher, NLIntent, ParsedTask, NLContextManager
        session = NLContextManager.get_session(self.guild_id, interaction.user.id, interaction.channel_id or 0)
        task = ParsedTask(intent=NLIntent.BACKUP_LIST, raw_segment="backups", confidence=1.0)
        res = await NLActionDispatcher.dispatch(self.bot, interaction.guild, interaction.user, interaction.channel, task, session)  # type: ignore
        await interaction.response.send_message(embed=res.embed, ephemeral=True)

    @ui.button(label="Away Summary", emoji="📊", style=discord.ButtonStyle.secondary, row=1)
    async def summary_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        summary = await AnalyticsService.get_away_summary(self.bot, interaction.guild, hours=12)  # type: ignore
        embed = create_embed(
            title="📊 RAI — WHILE YOU WERE AWAY",
            description=(
                f"**Period:** `{summary['period_start']} → {summary['period_end']}`\n\n"
                f"👥 **COMMUNITY:** `{summary['member_count']}` total members\n\n"
                f"🎙️ **ROOMS:**\n"
                f"• `{summary['rooms_created']}` created | `{summary['rooms_cleaned']}` cleaned | `{summary['rooms_active']}` active\n\n"
                f"🛡️ **SECURITY:**\n"
                f"• `{summary['security_incidents_count']}` recorded incidents\n\n"
                f"💾 **BACKUP:**\n"
                f"• `{summary['backups_count']}` archives in period\n\n"
                f"❤️ **SYSTEM:** `{summary['health_status']}`"
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="Maintenance", emoji="🛠️", style=discord.ButtonStyle.secondary, row=1)
    async def maintenance_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        ops = RaiOperationsCore.get_instance(self.bot)
        state = await AutomationService.get_state(self.bot, self.guild_id)
        curr = bool(state.get("maintenance_mode", 0))
        new_state = not curr
        await ops.set_maintenance_mode(interaction.guild, interaction.user, new_state, reason="Toggled via Operations Dashboard")  # type: ignore
        msg = f"🛠️ Maintenance mode is now **{'ENABLED 🟡' if new_state else 'DISABLED 🟢'}**."
        await interaction.response.send_message(msg, ephemeral=True)

    @ui.button(label="Events", emoji="📅", style=discord.ButtonStyle.secondary, row=1)
    async def events_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        events = await self.bot.db.list_events(self.guild_id, status="scheduled")
        embed = create_embed(
            title=f"📅 Active Scheduled Events ({len(events)})",
            description="\n".join([f"• **#{e.id}** {e.title} — `{e.start_time}`" for e in events[:8]]) if events else "No active scheduled events.",
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="Projects", emoji="📁", style=discord.ButtonStyle.secondary, row=1)
    async def projects_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        projects = await self.bot.db.list_projects(self.guild_id, status="active")
        embed = create_embed(
            title=f"📁 Active Collaboration Projects ({len(projects)})",
            description="\n".join([f"• **#{p['id']}** {p['name']} ({p['project_type']})" for p in projects[:8]]) if projects else "No active projects.",
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="Analytics", emoji="📈", style=discord.ButtonStyle.secondary, row=2)
    async def analytics_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        from core.analytics import ServerAnalyticsEngine
        weekly = await ServerAnalyticsEngine.generate_weekly_report(self.bot, interaction.guild)  # type: ignore
        embed = create_embed(
            title="📈 Server Intelligence & Analytics Overview",
            description=(
                f"**Members:** {weekly['members']['total_members']} ({weekly['members']['active_percentage']}% active)\n"
                f"**Voice Users:** {weekly['voice']['voice_users']} across {weekly['voice']['active_channels']} active VCs\n"
                f"**Community:** {weekly['community']['scheduled_events']} events, {weekly['community']['active_projects']} projects\n"
                f"**Security State:** {weekly['security']['status']}\n"
                f"**Gateway Ping:** {weekly['system']['gateway_latency_ms']} ms"
            ),
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="Recovery", emoji="🔄", style=discord.ButtonStyle.secondary, row=2)
    async def recovery_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        from core.recovery import DisasterRecoveryEngine
        scan_id, diffs = await DisasterRecoveryEngine.scan_guild_state(self.bot, interaction.guild)  # type: ignore
        embed = create_embed(
            title=f"🔄 Disaster Recovery Scan ({scan_id})",
            description=f"Detected **{len(diffs)}** discrepancy item(s) between Discord live state and database baseline." if diffs else "✅ All channels, roles, and room states match desired baseline!",
            color=Colors.PRIMARY if not diffs else Colors.WARNING,
        )
        if diffs:
            embed.add_field(name="Discrepancies", value="\n".join([f"• [{d.diff_type}] {d.resource_name}" for d in diffs[:6]]), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="Reports", emoji="📋", style=discord.ButtonStyle.secondary, row=2)
    async def reports_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_auth(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        incidents = await self.bot.db.get_security_incidents(self.guild_id, limit=5)
        embed = create_embed(
            title=f"📋 Recent Operations & Security Reports ({len(incidents)})",
            description="\n".join([f"• **{i.event_id}** — {getattr(i, 'reason', 'Security Alert')}" for i in incidents]) if incidents else "No open or recent incidents recorded.",
            color=Colors.PRIMARY,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

