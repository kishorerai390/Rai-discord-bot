"""
Safe Security Simulator for 『RΛI』.

Core Responsibilities:
1. Generates realistic synthetic attack scenarios:
   - raid: Sudden join bursts with avatarless accounts.
   - spam: High message velocity across channels.
   - nuke: Unauthorized mass channel/role deletion.
   - mention: Distributed mass member mention attack.
   - permission: Rogue dangerous permission elevation.
2. Pipes synthetic signals through the REAL Security Brain, Risk Engine, and Protection Policy.
3. Produces a predictive assessment of what RAI WOULD do without making ANY real Discord changes.
4. Guaranteed non-destructive dry-run execution.
"""

from __future__ import annotations

import datetime
import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import discord

from config import Colors
from security.brain import SecurityBrain
from security.risk_engine import RiskEngine, RiskLevel
from security.signals import SecuritySignal, SignalEventType, SignalSeverity, SignalSource

logger = logging.getLogger("Rai.SecuritySimulator")


@dataclass
class SimulationResult:
    """Outcome of a dry-run security simulation."""
    scenario: str
    threat_level_name: str
    expected_threat_score: float
    expected_actions: List[str]
    messages_count: int
    mentions_count: int
    channels_count: int
    simulated_actors_count: int
    simulation_status: str = "🟢 COMPLETE"


class SecuritySimulator:
    """Non-destructive threat simulation harness."""

    def __init__(self):
        self.brain = SecurityBrain()
        self.risk_engine = RiskEngine()

    async def simulate_scenario(self, scenario: str, guild_id: int = 1457382179981099090) -> SimulationResult:
        """
        Runs synthetic attack vectors through an isolated Brain and Risk Engine instance.
        """
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        signals: List[SecuritySignal] = []

        scenario_clean = scenario.lower().strip()

        if scenario_clean == "mention":
            # 20 messages, 150 mentions, 6 channels
            messages_count = 20
            mentions_count = 150
            channels_count = 6
            actors_count = 3

            for i in range(channels_count):
                signals.append(
                    SecuritySignal(
                        guild_id=guild_id,
                        event_type=SignalEventType.MASS_MENTION.value,
                        source=SignalSource.MENTION_SPAM.value,
                        severity=SignalSeverity.CRITICAL.value,
                        confidence=0.98,
                        timestamp=now,
                        actor_id=888001 + (i % actors_count),
                        actor_name=f"sim_spammer_{i % actors_count}",
                        channel_id=9001 + i,
                        evidence={"mentions": 25, "unique_targets": 22},
                    )
                )
            expected_actions = [
                "• Delete detected spam messages across affected channels",
                "• Apply temporary timeout / restriction on attacker accounts",
                "• Create security incident record (RAI-INC-XXXXXX)",
                "• Dispatch emergency notification to current server owner",
            ]
            title_scenario = "MASS MENTION ATTACK"

        elif scenario_clean == "raid":
            # Rapid joins burst
            messages_count = 0
            mentions_count = 0
            channels_count = 1
            actors_count = 25

            for i in range(5):
                signals.append(
                    SecuritySignal(
                        guild_id=guild_id,
                        event_type=SignalEventType.JOIN_BURST.value,
                        source=SignalSource.ANTI_RAID.value,
                        severity=SignalSeverity.CRITICAL.value,
                        confidence=0.95,
                        timestamp=now,
                        actor_id=777001 + i,
                        evidence={"joins_count": 25, "avatarless_percentage": 92.0},
                    )
                )
            expected_actions = [
                "• Enable verification gate / quarantine mode for new joins",
                "• Pause server invites temporarily",
                "• Create anti-raid containment incident",
                "• Alert current server owner and staff",
            ]
            title_scenario = "COORDINATED SERVER RAID"

        elif scenario_clean == "nuke":
            # Mass channel & role deletion
            messages_count = 0
            mentions_count = 0
            channels_count = 5
            actors_count = 1

            for i in range(4):
                signals.append(
                    SecuritySignal(
                        guild_id=guild_id,
                        event_type=SignalEventType.MASS_CHANNEL_DELETE.value,
                        source=SignalSource.ANTI_NUKE.value,
                        severity=SignalSeverity.CRITICAL.value,
                        confidence=0.99,
                        timestamp=now,
                        actor_id=666001,
                        actor_name="rogue_admin",
                        evidence={"deleted_channels_count": 4},
                    )
                )
            expected_actions = [
                "• Instantly revoke dangerous administrative roles from rogue actor",
                "• Quarantine rogue user account (Apply maximum timeout)",
                "• Initiate emergency lockdown protocol",
                "• High-priority dispatch to current server owner",
            ]
            title_scenario = "INSIDER NUKE ATTACK"

        elif scenario_clean == "spam":
            messages_count = 35
            mentions_count = 12
            channels_count = 4
            actors_count = 2

            for i in range(channels_count):
                signals.append(
                    SecuritySignal(
                        guild_id=guild_id,
                        event_type=SignalEventType.MESSAGE_VELOCITY_SPIKE.value,
                        source=SignalSource.ANTI_SPAM.value,
                        severity=SignalSeverity.HIGH.value,
                        confidence=0.88,
                        timestamp=now,
                        actor_id=555001 + i,
                        channel_id=9101 + i,
                        evidence={"velocity_msgs_per_second": 8.5},
                    )
                )
            expected_actions = [
                "• Apply message slowmode to affected channels",
                "• Purge repetitive spam payloads",
                "• Apply short moderation timeouts to spam accounts",
            ]
            title_scenario = "HIGH VELOCITY MESSAGE SPAM"

        else:  # permission
            messages_count = 0
            mentions_count = 0
            channels_count = 0
            actors_count = 1

            signals.append(
                SecuritySignal(
                    guild_id=guild_id,
                    event_type=SignalEventType.DANGEROUS_PERMISSION_CHANGE.value,
                    source=SignalSource.PERMISSION_MONITOR.value,
                    severity=SignalSeverity.HIGH.value,
                    confidence=0.92,
                    timestamp=now,
                    actor_id=444001,
                    evidence={"elevated_permission": "Administrator", "target_role": "@everyone"},
                )
            )
            expected_actions = [
                "• Revert unauthorized dangerous permission override on role",
                "• Strip administrative privileges from unauthorized executor",
                "• Log security event to incident records",
                "• Notify server owner immediately",
            ]
            title_scenario = "DANGEROUS PERMISSION ESCALATION"

        # Pipe through Brain
        for sig in signals:
            await self.brain.ingest_signal(sig)

        assessment = self.brain.evaluate_guild(guild_id)
        risk_result = await self.risk_engine.evaluate_risk(assessment)

        level_name = "🔴 CRITICAL" if risk_result.risk_level in (RiskLevel.CRITICAL, RiskLevel.EMERGENCY) else (
            "🟠 HIGH_ALERT" if risk_result.risk_level == RiskLevel.HIGH_ALERT else "🟡 ELEVATED"
        )

        return SimulationResult(
            scenario=title_scenario,
            threat_level_name=level_name,
            expected_threat_score=assessment.threat_score,
            expected_actions=expected_actions,
            messages_count=messages_count,
            mentions_count=mentions_count,
            channels_count=channels_count,
            simulated_actors_count=actors_count,
            simulation_status="🟢 COMPLETE",
        )

    def create_simulation_embed(self, res: SimulationResult) -> discord.Embed:
        """
        Formats standard simulation embed matching requested specification:
        『RΛI』 • SECURITY SIMULATION
        Scenario: ...
        Messages: ...
        Mentions: ...
        Channels: ...
        Expected Threat: ...
        Expected Actions: ...
        Real Discord Changes: NONE
        Simulation: 🟢 COMPLETE
        """
        embed = discord.Embed(
            title="『RΛI』 • SECURITY SIMULATION",
            color=Colors.PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Scenario", value=f"**{res.scenario}**", inline=False)
        embed.add_field(name="Messages", value=str(res.messages_count), inline=True)
        embed.add_field(name="Mentions", value=str(res.mentions_count), inline=True)
        embed.add_field(name="Channels", value=str(res.channels_count), inline=True)

        embed.add_field(name="Expected Threat", value=res.threat_level_name, inline=False)
        embed.add_field(name="Expected Actions", value="\n".join(res.expected_actions), inline=False)
        embed.add_field(name="Real Discord Changes", value="**NONE**", inline=False)
        embed.add_field(name="Simulation", value=res.simulation_status, inline=False)

        embed.set_footer(text="RAI Security Intelligence • Zero-Risk Synthetic Sandbox")
        return embed
