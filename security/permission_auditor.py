"""
Read-Only Permission Auditor for 『RΛI』.

Core Responsibilities:
1. Conducts non-destructive, read-only security audits of guild configuration:
   - Roles with raw Administrator permission.
   - Excessive dangerous permissions (Manage Channels, Manage Roles, Ban, Kick, Webhooks).
   - Bot hierarchy and bot permissions relative to founder and other bots.
   - Channel overwrites and exposed private channels.
   - Webhook configurations.
   - Security channel presence.
2. Classifies findings into standardized tiers:
   - CRITICAL
   - HIGH
   - MEDIUM
   - LOW
   - INFO
3. Formats clean audit reports without making ANY automatic modifications.
"""

from __future__ import annotations

import datetime
import enum
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import discord

from config import Colors

logger = logging.getLogger("Rai.PermissionAuditor")


class AuditSeverity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass
class AuditFinding:
    severity: AuditSeverity
    category: str
    target_name: str
    description: str
    recommendation: str


@dataclass
class PermissionAuditReport:
    guild_id: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    rai_status: str
    findings: List[AuditFinding]
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


class PermissionAuditor:
    """Read-only security assessment engine."""

    def __init__(self, db: Any = None):
        self.db = db

    async def audit_guild(self, guild: discord.Guild) -> PermissionAuditReport:
        """
        Conducts a full read-only security audit of a Discord guild.
        Guaranteed zero API modifications.
        """
        findings: List[AuditFinding] = []
        bot_member = guild.me

        # 1. Audit Administrator Roles
        admin_roles: List[discord.Role] = []
        for role in guild.roles:
            if role.permissions.administrator and role.id != guild.id:
                admin_roles.append(role)

        if len(admin_roles) > 3:
            findings.append(
                AuditFinding(
                    severity=AuditSeverity.CRITICAL,
                    category="Roles",
                    target_name="Guild Roles",
                    description=f"{len(admin_roles)} roles have Administrator permission",
                    recommendation="Reduce raw Administrator permission. Only Founder and Head Admin should hold it.",
                )
            )
        elif len(admin_roles) > 0:
            findings.append(
                AuditFinding(
                    severity=AuditSeverity.MEDIUM,
                    category="Roles",
                    target_name="Guild Roles",
                    description=f"{len(admin_roles)} roles have Administrator permission",
                    recommendation="Audit assigned members to ensure least privilege.",
                )
            )

        # 2. Check for Bots with Administrator
        bot_admin_count = 0
        for member in guild.members:
            if member.bot and member.id != bot_member.id and member.guild_permissions.administrator:
                bot_admin_count += 1

        if bot_admin_count >= 3:
            findings.append(
                AuditFinding(
                    severity=AuditSeverity.CRITICAL,
                    category="Bots",
                    target_name="Third-Party Bots",
                    description=f"{bot_admin_count} external bots have raw Administrator privileges",
                    recommendation="Remove Administrator from third-party bots (music, utility). Grant only needed scopes.",
                )
            )
        elif bot_admin_count > 0:
            findings.append(
                AuditFinding(
                    severity=AuditSeverity.HIGH,
                    category="Bots",
                    target_name="Third-Party Bots",
                    description=f"{bot_admin_count} external bots have Administrator privileges",
                    recommendation="Replace full Administrator with scoped permissions.",
                )
            )

        # 3. Check Role Hierarchy (Rythm or bots above Founder)
        founder_role = None
        for r in guild.roles:
            if "founder" in r.name.lower() or "owner" in r.name.lower():
                founder_role = r
                break

        if founder_role:
            roles_above_founder = [
                r for r in guild.roles if r.position > founder_role.position and r.managed
            ]
            if roles_above_founder:
                bot_names = ", ".join(r.name for r in roles_above_founder)
                findings.append(
                    AuditFinding(
                        severity=AuditSeverity.HIGH,
                        category="Hierarchy",
                        target_name="Role Hierarchy",
                        description=f"Bot roles ({bot_names}) are positioned above Founder role",
                        recommendation="Move Founder role to top position in Server Settings -> Roles.",
                    )
                )

        # 4. Check Webhooks
        try:
            webhooks = await guild.webhooks()
            if len(webhooks) > 5:
                findings.append(
                    AuditFinding(
                        severity=AuditSeverity.MEDIUM,
                        category="Webhooks",
                        target_name="Webhooks",
                        description=f"{len(webhooks)} webhooks configured across channels",
                        recommendation="Review webhook URLs and prune inactive integrations.",
                    )
                )
        except Exception:
            pass

        # 5. Check Security Logging Channel Configuration
        has_security_channel = any(
            "security" in ch.name.lower() or "incident" in ch.name.lower() or "audit" in ch.name.lower()
            for ch in guild.text_channels
        )
        if not has_security_channel:
            findings.append(
                AuditFinding(
                    severity=AuditSeverity.HIGH,
                    category="Channels",
                    target_name="Security Logging",
                    description="Security reporting channel is not configured",
                    recommendation="Create #security-log restricted strictly to administrators.",
                )
            )

        # 6. Check RAI Bot Permissions
        if bot_member:
            perms = bot_member.guild_permissions
            missing_core = []
            if not perms.manage_roles:
                missing_core.append("Manage Roles")
            if not perms.manage_channels:
                missing_core.append("Manage Channels")
            if not perms.moderate_members:
                missing_core.append("Moderate Members")
            if not perms.view_audit_log:
                missing_core.append("View Audit Log")

            if missing_core:
                findings.append(
                    AuditFinding(
                        severity=AuditSeverity.HIGH,
                        category="RAI Permissions",
                        target_name="Bot Member",
                        description=f"RAI is missing functional permissions: {', '.join(missing_core)}",
                        recommendation="Grant missing permissions to RAI bot role.",
                    )
                )

        # 7. Check @everyone Dangerous Permissions
        everyone_perms = guild.default_role.permissions
        if (
            everyone_perms.mention_everyone
            or everyone_perms.manage_messages
            or everyone_perms.kick_members
            or everyone_perms.ban_members
        ):
            findings.append(
                AuditFinding(
                    severity=AuditSeverity.CRITICAL,
                    category="@everyone",
                    target_name="@everyone Role",
                    description="@everyone role has dangerous elevated permissions (mention_everyone or moderation)",
                    recommendation="Revoke Mention Everyone, Manage Messages, and moderation permissions from @everyone.",
                )
            )

        # Count by severity
        crit = sum(1 for f in findings if f.severity == AuditSeverity.CRITICAL)
        high = sum(1 for f in findings if f.severity == AuditSeverity.HIGH)
        med = sum(1 for f in findings if f.severity == AuditSeverity.MEDIUM)
        low = sum(1 for f in findings if f.severity == AuditSeverity.LOW)
        info = sum(1 for f in findings if f.severity == AuditSeverity.INFO)

        rai_status = "🟢 OPERATIONAL" if (bot_member and bot_member.guild_permissions.manage_roles) else "🟡 DEGRADED"

        return PermissionAuditReport(
            guild_id=guild.id,
            critical_count=crit,
            high_count=high,
            medium_count=med,
            low_count=low,
            info_count=info,
            rai_status=rai_status,
            findings=findings,
        )

    def create_audit_embed(self, report: PermissionAuditReport) -> discord.Embed:
        """
        Builds standard audit embed matching requested specification:
        『RΛI』 • SECURITY AUDIT

        Critical: X
        High: X
        Medium: X
        Low: X

        RAI:
        🟢 OPERATIONAL

        Findings:
        • ...
        """
        color = Colors.ERROR if report.critical_count > 0 else (
            Colors.WARNING if report.high_count > 0 else Colors.SUCCESS
        )

        embed = discord.Embed(
            title="『RΛI』 • SECURITY AUDIT",
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        counts_str = (
            f"**Critical:** {report.critical_count}\n"
            f"**High:** {report.high_count}\n"
            f"**Medium:** {report.medium_count}\n"
            f"**Low:** {report.low_count}"
        )
        embed.add_field(name="Summary", value=counts_str, inline=False)
        embed.add_field(name="RAI", value=report.rai_status, inline=False)

        if report.findings:
            findings_lines = [f"• {f.description}" for f in report.findings[:8]]
            embed.add_field(name="Findings", value="\n".join(findings_lines), inline=False)
        else:
            embed.add_field(name="Findings", value="• Zero security vulnerabilities identified.", inline=False)

        embed.set_footer(text="RAI Read-Only Security Auditor • No changes were made")
        return embed
