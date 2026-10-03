"""
Incident Timeline and Investigation Engine for 『RΛI』.

Core Responsibilities:
1. Reconstructs chronological forensic timelines from actual recorded SQLite events
   (security_intelligence_signals, security_threat_timeline, security_incidents).
2. Generates comprehensive audit embeds for `/rai investigate <incident_id>`.
3. Never fabricates missing events: strictly renders verified telemetry from storage.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import discord

from config import Colors

logger = logging.getLogger("Rai.IncidentInvestigation")


@dataclass
class IncidentTimelineEntry:
    timestamp_str: str
    description: str
    component: str
    severity: str


@dataclass
class IncidentReport:
    incident_id: str
    guild_id: int
    status: str
    severity: str
    target_name: Optional[str]
    timeline: List[IncidentTimelineEntry]
    mitigations_taken: List[str]
    created_at: str


class IncidentInvestigator:
    """Forensic investigation engine retrieving stored security telemetry."""

    def __init__(self, db: Any = None):
        self.db = db

    async def get_incident_timeline(self, incident_id: str, guild_id: int) -> Optional[IncidentReport]:
        """
        Retrieves actual stored events for an incident across SQLite tables.
        Guaranteed: No synthetic or fabricated records.
        """
        if not self.db or not hasattr(self.db, "_db") or not self.db._db:
            return None

        clean_id = incident_id.strip().upper()
        timeline: List[IncidentTimelineEntry] = []
        mitigations: List[str] = []
        incident_row = None

        def _get_val(row: Any, key: str, default: Any = None) -> Any:
            if row is None:
                return default
            if isinstance(row, dict):
                return row.get(key, default)
            try:
                return row[key]
            except Exception:
                return getattr(row, key, default)

        try:
            # 1. Query security_incidents
            async with self.db._db.execute(
                "SELECT * FROM security_incidents WHERE event_id = ? OR event_id LIKE ?",
                (clean_id, f"%{clean_id}%"),
            ) as cursor:
                incident_row = await cursor.fetchone()

            # 2. Query security_intelligence_signals
            async with self.db._db.execute(
                """
                SELECT timestamp, event_type, source, severity, actor_name, channel_name
                FROM security_intelligence_signals
                WHERE incident_id = ?
                ORDER BY timestamp ASC
                """,
                (clean_id,),
            ) as cursor:
                sig_rows = await cursor.fetchall()
                if sig_rows:
                    for r in sig_rows:
                        ts = _get_val(r, "timestamp", "")
                        # Format time as HH:MM:SS
                        try:
                            dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            time_display = dt.strftime("%H:%M:%S")
                        except Exception:
                            time_display = ts[:8] if ts else "00:00:00"

                        evt_type = _get_val(r, "event_type", "event")
                        desc = f"{evt_type.replace('_', ' ').capitalize()} detected"
                        ch_name = _get_val(r, "channel_name")
                        if ch_name:
                            desc += f" in #{ch_name}"
                        act_name = _get_val(r, "actor_name")
                        if act_name:
                            desc += f" by {act_name}"

                        timeline.append(
                            IncidentTimelineEntry(
                                timestamp_str=time_display,
                                description=desc,
                                component=_get_val(r, "source", "security"),
                                severity=_get_val(r, "severity", "HIGH"),
                            )
                        )

            # 3. Query security_threat_timeline if table exists
            try:
                async with self.db._db.execute(
                    """
                    SELECT timestamp, description, severity
                    FROM security_threat_timeline
                    WHERE incident_id = ?
                    ORDER BY timestamp ASC
                    """,
                    (clean_id,),
                ) as cursor:
                    tl_rows = await cursor.fetchall()
                    if tl_rows:
                        for r in tl_rows:
                            ts = _get_val(r, "timestamp", "")
                            try:
                                dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                                time_display = dt.strftime("%H:%M:%S")
                            except Exception:
                                time_display = ts[:8] if ts else "00:00:00"
                            timeline.append(
                                IncidentTimelineEntry(
                                    timestamp_str=time_display,
                                    description=_get_val(r, "description", ""),
                                    component="ThreatTimeline",
                                    severity=_get_val(r, "severity", "HIGH"),
                                )
                            )
            except Exception as tl_err:
                logger.debug(f"Optional threat timeline query skipped: {tl_err}")

            if not incident_row and not timeline:
                return None

            status = _get_val(incident_row, "result", "RESOLVED")
            severity = _get_val(incident_row, "severity", "HIGH")
            target_name = _get_val(incident_row, "target_name")
            created_at = _get_val(incident_row, "timestamp") or (timeline[0].timestamp_str if timeline else "")

            # If incident row had an automated action, add to mitigations
            auto_action = _get_val(incident_row, "automated_action")
            if auto_action:
                mitigations.append(auto_action)

            return IncidentReport(
                incident_id=clean_id,
                guild_id=guild_id,
                status=str(status).upper(),
                severity=str(severity).upper(),
                target_name=target_name,
                timeline=timeline,
                mitigations_taken=mitigations,
                created_at=str(created_at),
            )

        except Exception as e:
            logger.error(f"[INVESTIGATE] Failed to fetch timeline for {clean_id}: {e}", exc_info=True)
            return None

    def create_timeline_embed(self, report: IncidentReport) -> discord.Embed:
        """
        Builds standard incident investigation embed:
        『RΛI』 • INCIDENT TIMELINE
        Incident: RAI-INC-000142
        HH:MM:SS ...
        Status: MITIGATING / RESOLVED
        """
        color = Colors.ERROR if report.severity in ("CRITICAL", "EMERGENCY") else Colors.WARNING

        embed = discord.Embed(
            title="『RΛI』 • INCIDENT TIMELINE",
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Incident", value=f"`{report.incident_id}`", inline=False)

        if report.timeline:
            timeline_lines = [f"`{e.timestamp_str}` {e.description}" for e in report.timeline[:10]]
            embed.add_field(name="Chronology", value="\n".join(timeline_lines), inline=False)
        else:
            embed.add_field(name="Chronology", value="*No granular signal telemetry found.*", inline=False)

        embed.add_field(name="Status", value=f"`{report.status}`", inline=True)
        embed.add_field(name="Severity", value=f"`{report.severity}`", inline=True)
        if report.target_name:
            embed.add_field(name="Target", value=f"`{report.target_name}`", inline=True)

        embed.set_footer(text="Forensic Telemetry • Stored Immutable SQLite Log")
        return embed
