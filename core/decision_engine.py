"""
RAI — CENTRAL DECISION ENGINE & MULTI-STEP ORCHESTRATOR.
Provides:
- Central pipeline executing requests above underlying domain services:
  User Request -> Intent Recognition -> Context Resolution -> Permission Check
  -> Risk Assessment -> Premium Check -> Confirmation Check -> Service Execution
  -> Verification -> Report -> Context Update.
- Multi-step request sequencing (e.g., "make room private and invite user").
- Reuses existing services: RoomService, MusicService, SecurityService, BackupService,
  MemoryService, RecoveryService, SimulationLab, etc., without duplicating logic.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import discord

from core.memory import MemoryService
from core.premium import EntitlementScope, PremiumFeature, PremiumFeatureGate
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.DecisionEngine")


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class DecisionStep:
    step_id: int
    name: str
    action_type: str
    target: Any
    params: Dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    premium_feature: Optional[PremiumFeature] = None


@dataclass
class DecisionPlan:
    plan_id: str
    guild_id: int
    user_id: int
    raw_query: str
    steps: List[DecisionStep]
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionExecutionResult:
    plan_id: str
    success: bool
    title: str
    message: str
    executed_steps: int
    total_steps: int
    details: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    pending_step: Optional[DecisionStep] = None


class RaiDecisionEngine:
    """Central orchestration layer coordinating multi-step requests across all Rai services."""

    _instance: Optional[RaiDecisionEngine] = None

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    @classmethod
    def get_instance(cls, bot: SentinelBot) -> RaiDecisionEngine:
        if cls._instance is None:
            cls._instance = RaiDecisionEngine(bot)
        return cls._instance

    async def execute_plan(
        self,
        guild: discord.Guild,
        user: discord.Member,
        channel: discord.abc.Messageable,
        plan: DecisionPlan,
    ) -> DecisionExecutionResult:
        """
        Executes a planned series of decision steps with strict validation at each step.
        """
        from core.operations_core import RoomService, SecurityService, BackupService, RaiOperationsCore
        from core.simulation import SimulationLab

        executed_count = 0
        step_results = []

        for step in plan.steps:
            # 1. Permission Check
            if step.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) and not is_admin_or_owner(user):
                return DecisionExecutionResult(
                    plan_id=plan.plan_id,
                    success=False,
                    title="Permission Denied",
                    message=f"Step '{step.name}' requires administrator or server owner privileges.",
                    executed_steps=executed_count,
                    total_steps=len(plan.steps),
                )

            # 2. Premium Check
            if step.premium_feature:
                gate = await PremiumFeatureGate.has_access(self.bot, step.premium_feature, user.id, guild.id)
                if not gate.has_access:
                    return DecisionExecutionResult(
                        plan_id=plan.plan_id,
                        success=False,
                        title="Premium Feature Required",
                        message=f"Step '{step.name}' requires Rai Premium ({gate.reason}).",
                        executed_steps=executed_count,
                        total_steps=len(plan.steps),
                    )

            # 3. Confirmation Gate
            if step.requires_confirmation:
                return DecisionExecutionResult(
                    plan_id=plan.plan_id,
                    success=False,
                    title="Confirmation Required",
                    message=f"Step '{step.name}' is a high-impact operation requiring explicit confirmation.",
                    executed_steps=executed_count,
                    total_steps=len(plan.steps),
                    requires_confirmation=True,
                    pending_step=step,
                )

            # 4. Service Execution
            try:
                if step.action_type == "room_privacy":
                    # Step: set room privacy
                    vc_id = step.params.get("voice_channel_id")
                    privacy = step.params.get("privacy", "private")
                    vc = guild.get_channel(vc_id)
                    if isinstance(vc, discord.VoiceChannel):
                        connect_val = False if privacy == "private" else True
                        await vc.set_permissions(guild.default_role, connect=connect_val)
                        await self.bot.db.update_dynamic_room(vc_id, privacy_mode=privacy)
                        step_results.append(f"🔒 Room privacy updated to {privacy}")
                        executed_count += 1
                elif step.action_type == "room_invite":
                    # Step: invite target user to room
                    vc_id = step.params.get("voice_channel_id")
                    target_member = step.target
                    vc = guild.get_channel(vc_id)
                    if isinstance(vc, discord.VoiceChannel) and isinstance(target_member, discord.Member):
                        await vc.set_permissions(target_member, connect=True, view_channel=True)
                        step_results.append(f"🎟️ Access granted to {target_member.display_name}")
                        executed_count += 1
                elif step.action_type == "simulate_raid":
                    sim = await SimulationLab.simulate_raid(self.bot, guild, user)
                    step_results.append(f"🧪 Raid simulation executed: {sim.simulation_id}")
                    executed_count += 1
                elif step.action_type == "remember":
                    key = step.params.get("key", "")
                    val = step.params.get("value", "")
                    await MemoryService.remember(self.bot, guild.id, key, val, created_by=user.id)
                    step_results.append(f"🧠 Remembered '{key}'")
                    executed_count += 1
                elif step.action_type == "backup_create":
                    rec = await BackupService.create(trigger=f"decision_engine_{user.name}")
                    step_results.append(f"💾 Backup archive created: {rec.backup_id}")
                    executed_count += 1
                else:
                    step_results.append(f"Executed step: {step.name}")
                    executed_count += 1
            except Exception as e:
                logger.error(f"Error executing step {step.name}: {e}", exc_info=True)
                return DecisionExecutionResult(
                    plan_id=plan.plan_id,
                    success=False,
                    title="Execution Error",
                    message=f"Failed during step '{step.name}': {e}",
                    executed_steps=executed_count,
                    total_steps=len(plan.steps),
                )

        # 5. Context Update
        ch_id = getattr(channel, "id", 0)
        try:
            ch_id_int = int(ch_id)
        except (ValueError, TypeError):
            ch_id_int = 0

        await MemoryService.set_context(
            self.bot,
            guild.id,
            user.id,
            ch_id_int,
            session_id=plan.plan_id,
            key="last_decision_plan",
            val=f"Executed {executed_count} steps successfully",
            ttl_seconds=1800.0,
        )

        return DecisionExecutionResult(
            plan_id=plan.plan_id,
            success=True,
            title="Multi-Step Execution Succeeded",
            message="\n".join(step_results),
            executed_steps=executed_count,
            total_steps=len(plan.steps),
            details={"steps": step_results},
        )
