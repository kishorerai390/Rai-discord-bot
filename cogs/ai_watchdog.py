"""
Rai Premium AI Security Sentinel Cog.
24/7 Autonomous Watchdog & Real-Time Threat Guardian.
Features:
- 24/7 Autonomous Audit Watchdog (Scans roles, permissions, channels every 60s).
- Zero-Day Phishing & Malicious Link Interceptor (on_message).
- Slash commands: /security_ai status, /security_ai scan, /security_ai setkey.
- Founder DM Escalation with 1-Click Interactive Countermeasures.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Colors
from core.tasks import safe_task_loop
from utils.ai_security_brain import AISecurityBrain
from utils.ai_incident_responder import OwnerIncidentActionView, IncidentAnalysisResult, IncidentAlertTracker
from utils.permissions import is_admin_or_owner, is_founder_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


class AIWatchdogCog(commands.Cog, name="AI Watchdog"):
    """Autonomous 24/7 Premium AI Security Sentinel."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.brain = AISecurityBrain(bot)
        self._last_audit_findings: list[str] = []
        self._last_audit_score: int = 100
        self._last_audit_time: Optional[datetime.datetime] = None

    async def cog_load(self) -> None:
        self.watchdog_loop.start()
        logger.info("Rai Premium AI Security Sentinel initialized and watchdog loop started.")

    async def cog_unload(self) -> None:
        self.watchdog_loop.cancel()

    # ==========================================
    # 24/7 AUTONOMOUS WATCHDOG SUPERVISOR (60s)
    # ==========================================

    @tasks.loop(seconds=60.0)
    @safe_task_loop(task_name="ai_watchdog_audit", timeout_seconds=45.0)
    async def watchdog_loop(self) -> None:
        """Autonomous 60-second server audit and anomaly detector."""
        await self.bot.wait_until_ready()
        try:
            for guild in self.bot.guilds:
                # Do NOT dispatch unsolicited security audit reports to servers unless owner reports are configured
                if hasattr(self.bot, "db") and self.bot.db:
                    try:
                        orc = await self.bot.db.get_owner_reports_config(guild.id)
                        if not orc or not (orc.category_id or orc.security_report_id):
                            continue
                    except Exception:
                        continue

                score, findings = self.brain.calculate_server_security_score(guild)
                self._last_audit_score = score
                self._last_audit_findings = findings
                self._last_audit_time = datetime.datetime.now(datetime.timezone.utc)

                # If critical vulnerabilities are discovered
                criticals = [f for f in findings if "CRITICAL" in f or "HIGH" in f]
                if criticals and score < 75:
                    logger.warning(f"[AI Watchdog] Anomalies discovered in {guild.name}: {criticals}")
                    try:
                        from utils.owner_reporter import OwnerReporter
                        OwnerReporter.send_security_report(
                            bot=self.bot,
                            guild_id=guild.id,
                            event="AI Security Audit Anomaly",
                            reason=f"Server integrity score dropped to {score}/100 with {len(criticals)} critical findings.",
                            action_taken="Security posture analyzed. Administrator review advised.",
                            severity="HIGH",
                            details={
                                "Integrity Score": f"{score}/100",
                                "AI Engine": self.brain.active_engine_name,
                                "Key Findings": "\n".join(f"• {c}" for c in criticals[:4]),
                            },
                        )
                    except Exception as rep_err:
                        logger.warning(f"[AI Watchdog] Could not dispatch report: {rep_err}")
        except Exception as e:
            logger.error(f"[AI Watchdog] Error in watchdog audit loop: {e}", exc_info=True)

    # ==========================================
    # REAL-TIME ZERO-DAY PHISHING & MALWARE GUARDIAN
    # ==========================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Screen all incoming chat messages for zero-day phishing, scam domains, and token loggers."""
        if message.author.bot or not message.guild:
            return

        threat = self.brain.scan_message(message.content)
        if threat:
            # 1. Immediately delete the malicious message
            try:
                await message.delete()
            except Exception:
                pass

            # 2. Timeout the malicious sender for 24 hours
            try:
                if isinstance(message.author, discord.Member):
                    await message.author.timeout(
                        datetime.timedelta(hours=24),
                        reason=f"Rai AI Threat Interception: Phishing/Malware link ({threat.category})",
                    )
            except Exception as e:
                logger.warning(f"Could not timeout phishing sender: {e}")

            # 3. Log to security channel
            try:
                sec_cfg = await self.bot.db.get_security_config(message.guild.id)
                log_ch_id = getattr(sec_cfg, "log_channel_id", None) or 1554891455003107338
                log_ch = message.guild.get_channel(log_ch_id)
                if log_ch and isinstance(log_ch, discord.TextChannel):
                    log_embed = threat.to_embed(title="🚨 AI Sentinel: Phishing Attack Intercepted")
                    log_embed.description = f"**User:** {message.author.mention} (`{message.author.id}`)\n**Channel:** {message.channel.mention}"
                    await log_ch.send(embed=log_embed)
            except Exception:
                pass

            # Dispatch to 🚨・security-report
            try:
                from utils.owner_reporter import OwnerReporter
                OwnerReporter.send_security_report(
                    self.bot,
                    message.guild.id,
                    event="Phishing Attack Intercepted",
                    user=message.author,
                    reason=f"Phishing/Malware link ({threat.category})",
                    action_taken="Deleted message and timed out user for 24h",
                    severity=threat.threat_level,
                    details={"Channel": message.channel.mention, "Preview": message.content[:100]},
                )
            except Exception:
                pass

            # 4. Dispatch Alert to Founder DM with 1-click countermeasures (only if founder DMs enabled)
            try:
                founder_dm_enabled = await self.bot.db.get_founder_activity_dm(message.guild.id)
            except Exception:
                founder_dm_enabled = False

            if founder_dm_enabled:
                founder_id = None
                try:
                    founder_id = await self.bot.db.get_founder_dm_recipient(message.guild.id)
                except Exception:
                    founder_id = None
                if not founder_id:
                    founder_id = message.guild.owner_id

                founder = self.bot.get_user(founder_id) if founder_id else None
                if not founder and founder_id:
                    try:
                        founder = await self.bot.fetch_user(founder_id)
                    except Exception:
                        founder = None

                if founder and not getattr(founder, "bot", False):
                    analysis = IncidentAnalysisResult(
                        threat_level=threat.threat_level,
                        assessment=threat.assessment,
                        recommendation=threat.recommendation,
                        actions=threat.suggested_actions,
                    )
                    dm_embed = threat.to_embed(title="🚨 AI Threat Intercepted: Malicious Link")
                    dm_embed.description = (
                        f"**Attacker:** {message.author.mention} (`{message.author.id}`)\n"
                        f"**Channel:** {message.channel.mention}\n"
                        f"**Message Preview:** `{message.content[:100]}`\n\n"
                        f"**Action Taken:** Message deleted and user timed out for 24h."
                    )

                    pending_count = IncidentAlertTracker.get_pending_count(founder.id) + 1
                    view = OwnerIncidentActionView(
                        bot=self.bot,
                        guild_id=message.guild.id,
                        target_id=message.author.id,
                        target_name=message.author.name,
                        actor_id=message.author.id,
                        event_type="phishing_attack",
                        owner_id=founder.id,
                        analysis=analysis,
                        pending_count=pending_count,
                    )
                    try:
                        sent_msg = await founder.send(embed=dm_embed, view=view)
                        IncidentAlertTracker.add_alert(founder.id, sent_msg)
                    except Exception:
                        pass

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    security_ai_group = app_commands.Group(
        name="security_ai",
        description="Premium AI Security Sentinel & 24/7 Watchdog",
        default_permissions=discord.Permissions(administrator=True),
    )

    @security_ai_group.command(name="status", description="Check live AI Security Sentinel status and shield integrity")
    async def status_cmd(self, interaction: discord.Interaction) -> None:
        """Display AI Guardian health, engine mode, and server security score."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ This command must be run in a server.", ephemeral=True)
            return

        score, findings = self.brain.calculate_server_security_score(guild)
        engine_mode = self.brain.active_engine_name
        is_cloud = self.brain.is_cloud_ai_active

        embed = discord.Embed(
            title="🛡️ Rai AI Security Sentinel — Live Status",
            color=Colors.PRIMARY if score >= 80 else Colors.WARNING,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="🧠 AI Engine", value=f"**{engine_mode}**\nMode: `{'Cloud Neural' if is_cloud else 'Autonomous Embedded'}`", inline=True)
        embed.add_field(name="🛡️ Shield Score", value=f"**{score}/100**\nStatus: `{'🟢 OPTIMAL' if score >= 85 else '🟡 ELEVATED' if score >= 70 else '🔴 AT RISK'}`", inline=True)
        embed.add_field(name="⏱️ Watchdog Interval", value="**60 Seconds** (Continuous)", inline=True)

        embed.add_field(
            name="📡 Active AI Shield Matrices",
            value=(
                "• **Anti-Nuke Matrix:** Active (Velocity tracking on channels & roles)\n"
                "• **Zero-Day Phishing Interceptor:** Active (Real-time message deep scan)\n"
                "• **Raid & Sybil Filter:** Active (Join rate & account age anomaly detection)\n"
                "• **Privilege Escalation Guard:** Active (Administrative role quarantine)\n"
                "• **Founder DM Console:** Active (Instant 1-click remediation & auto-delete)"
            ),
            inline=False,
        )

        embed.add_field(
            name="📋 Latest Watchdog Audit Findings",
            value="\n".join(f"• {f}" for f in findings[:4]) if findings else "• All security parameters nominal.",
            inline=False,
        )

        embed.set_footer(text="Rai AI Enterprise Security • 24/7 Autonomous Watchdog")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @security_ai_group.command(name="scan", description="Run an instant on-demand AI security audit of the server")
    async def scan_cmd(self, interaction: discord.Interaction) -> None:
        """Triggers a full on-demand security audit."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Server not found.", ephemeral=True)
            return

        score, findings = self.brain.calculate_server_security_score(guild)

        embed = discord.Embed(
            title="🔍 AI Security Sentinel: On-Demand Audit Report",
            color=Colors.SUCCESS if score >= 80 else Colors.WARNING,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.description = f"Full server security audit completed for **{guild.name}**."
        embed.add_field(name="Security Score", value=f"**{score} / 100**", inline=True)
        embed.add_field(name="Total Roles Scanned", value=f"`{len(guild.roles)}`", inline=True)
        embed.add_field(name="Total Channels Scanned", value=f"`{len(guild.channels)}`", inline=True)

        embed.add_field(
            name="📝 Detailed Intelligence Findings",
            value="\n".join(f"• {f}" for f in findings) if findings else "• No vulnerabilities detected.",
            inline=False,
        )
        embed.set_footer(text=f"Audited by {self.brain.active_engine_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @security_ai_group.command(name="setkey", description="Configure or update the Google Gemini API Key for Cloud Neural AI")
    @app_commands.describe(api_key="Your Google Gemini API Key")
    async def setkey_cmd(self, interaction: discord.Interaction, api_key: str) -> None:
        """Securely configure Gemini API key."""
        if not is_founder_or_owner(interaction.user):
            await interaction.response.send_message("❌ This command is restricted to the Server Founder.", ephemeral=True)
            return

        self.brain.set_gemini_key(api_key.strip())

        # Update .env file securely
        env_path = r"f:\Bot\.env"
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "GEMINI_API_KEY=" in content:
                import re
                content = re.sub(r"GEMINI_API_KEY=.*", f"GEMINI_API_KEY={api_key.strip()}", content)
            else:
                content += f"\nGEMINI_API_KEY={api_key.strip()}\n"
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logger.warning(f"Could not persist GEMINI_API_KEY to .env: {e}")

        await interaction.response.send_message(
            f"✅ **Cloud Neural AI Activated!**\nEngine updated to **{self.brain.active_engine_name}**.",
            ephemeral=True,
        )


async def setup(bot: SentinelBot) -> None:
    await bot.add_cog(AIWatchdogCog(bot))
