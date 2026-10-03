"""
Unit and Integration Tests for 『RΛI』 Futuristic Cyberpunk Discord Server Branding System.
Tests:
- Server category, channel, and role plan generation (dry-run safety)
- Existing resource preservation (no accidental deletions or duplication)
- Embed branding consistency (『RΛI』 • <CATEGORY>, RΛI://CORE footer)
- Security severity levels (🟢 LOW to ☢️ EMERGENCY)
- Music now-playing embed layout
- Security dashboard status matrix
"""

import unittest
from unittest.mock import AsyncMock, MagicMock
import discord

from utils.branding import (
    ServerBrandingManager,
    CATEGORIES_SPEC,
    EMERGENCY_CHANNELS_SPEC,
    VOICE_CHANNELS_SPEC,
    ROLES_SPEC,
)
from utils.embeds import (
    create_embed,
    success_embed,
    error_embed,
    warning_embed,
    security_embed,
    info_embed,
    security_alert_embed,
    music_now_playing_embed,
    security_dashboard_embed,
    normalize_severity,
    DEFAULT_BRAND,
    DEFAULT_FOOTER,
)


class TestServerBranding(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 1457382179981099090
        self.guild.name = "Test Cyberpunk Server"
        self.guild.default_role = MagicMock(spec=discord.Role)

        # Mock categories, text channels, voice channels, and roles
        self.guild.categories = []
        self.guild.text_channels = []
        self.guild.voice_channels = []
        self.guild.roles = []

        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.id = 1554732669072445532

    def test_embed_branding_titles_and_footer(self):
        """Verifies embeds adhere to 『RΛI』 • <CATEGORY> and RΛI://CORE footer."""
        s_embed = success_embed("OPERATION COMPLETE", "Perimeter lockdown lifted.")
        self.assertIn("『RΛI』 • OPERATION COMPLETE", s_embed.title)
        self.assertIn("> ✅", s_embed.description)
        self.assertEqual(s_embed.footer.text, DEFAULT_FOOTER)

        e_embed = error_embed("DATABASE TIMEOUT", "Query could not be executed.")
        self.assertIn("『RΛI』 • DATABASE TIMEOUT", e_embed.title)
        self.assertIn("> ❌", e_embed.description)
        self.assertEqual(e_embed.footer.text, DEFAULT_FOOTER)

        w_embed = warning_embed("PERMISSION OVERRIDE", "Requires Administrator authorization.")
        self.assertIn("『RΛI』 • PERMISSION OVERRIDE", w_embed.title)
        self.assertIn("> ⚠️", w_embed.description)

        sec_embed = security_embed("FIREWALL ENGAGED", "Shield baseline activated.")
        self.assertIn("『RΛI』 • FIREWALL ENGAGED", sec_embed.title)
        self.assertIn("> 🛡️", sec_embed.description)

    def test_security_severity_normalization(self):
        """Verifies standard severity levels: 🟢 LOW, 🟡 MEDIUM, 🟠 HIGH, 🔴 CRITICAL, ☢️ EMERGENCY."""
        self.assertEqual(normalize_severity("LOW"), "🟢 LOW")
        self.assertEqual(normalize_severity("MEDIUM"), "🟡 MEDIUM")
        self.assertEqual(normalize_severity("HIGH"), "🟠 HIGH")
        self.assertEqual(normalize_severity("CRITICAL"), "🔴 CRITICAL")
        self.assertEqual(normalize_severity("EMERGENCY"), "☢️ EMERGENCY")

    def test_security_alert_embed_structure(self):
        """Verifies security alert embed fields: Event, Severity, Incident ID, Guild, Actor, Action."""
        embed = security_alert_embed(
            event_type="Join Spike Detected",
            severity="CRITICAL",
            guild_name="Neo-Tokyo Citadel",
            user_str="RaidBot_01#1234",
            action_taken="Quarantined to isolation gate",
            incident_id="SEC-2026-X99",
            details="18 accounts joined in 4.2 seconds.",
        )
        self.assertIn("『RΛI』 • SECURITY ALERT", embed.title)
        field_dict = {f.name: f.value for f in embed.fields}
        self.assertIn("🚨 Event Type", field_dict)
        self.assertIn("⚡ Severity", field_dict)
        self.assertIn("🔴 CRITICAL", field_dict["⚡ Severity"])
        self.assertIn("🆔 Incident ID", field_dict)
        self.assertIn("SEC-2026-X99", field_dict["🆔 Incident ID"])
        self.assertIn("🛡️ Action Taken", field_dict)
        self.assertEqual(embed.footer.text, DEFAULT_FOOTER)

    def test_music_now_playing_embed(self):
        """Verifies music embed formatting: Track, Artist, Duration, Requested by, Position, Status."""
        embed = music_now_playing_embed(
            track_title="Cyberpunk 2077 - Rebel Path",
            artist="P.T. Adamczyk",
            duration_str="03:42",
            requested_by="@Netrunner",
            queue_position="#1",
            player_status="Playing",
        )
        self.assertIn("『RΛI』 • NOW PLAYING", embed.title)
        self.assertIn("Rebel Path", embed.description)
        field_dict = {f.name: f.value for f in embed.fields}
        self.assertIn("⏱️ Duration", field_dict)
        self.assertIn("👤 Requested by", field_dict)
        self.assertIn("📜 Position", field_dict)
        self.assertIn("🎚️ Player Status", field_dict)

    def test_security_dashboard_embed_matrix(self):
        """Verifies Section 11 security dashboard ASCII matrix."""
        embed = security_dashboard_embed(
            "Main Guild",
            {
                "Protection": "ONLINE",
                "Anti-Raid": "ACTIVE",
                "Anti-Nuke": "ACTIVE",
                "Anti-Spam": "ACTIVE",
                "AutoMod": "ACTIVE",
                "Monitoring": "ONLINE",
                "Health": "HEALTHY",
            },
        )
        self.assertIn("『RΛI』 // SECURITY CENTER", embed.title)
        self.assertIn("🛡️ Protection      ONLINE", embed.description)
        self.assertIn("⚔️ Anti-Raid       ACTIVE", embed.description)
        self.assertIn("☢️ Anti-Nuke       ACTIVE", embed.description)
        self.assertIn("🔐 Anti-Spam       ACTIVE", embed.description)
        self.assertIn("🤖 AutoMod         ACTIVE", embed.description)
        self.assertIn("📡 Monitoring      ONLINE", embed.description)
        self.assertIn("🩺 Health          HEALTHY", embed.description)

    def test_dry_run_plan_generation_empty_guild(self):
        """Verifies dry-run plan on empty guild plans all categories, channels, and roles without touching guild."""
        plan = ServerBrandingManager.generate_plan(self.guild, include_voice=True)

        # Must plan 4 primary categories
        self.assertEqual(len(plan.categories_to_create), 4)
        self.assertIn("🛡️・RΛI SECURITY", plan.categories_to_create)
        self.assertIn("🎵・RΛI MUSIC", plan.categories_to_create)
        self.assertIn("⚙️・RΛI SYSTEM", plan.categories_to_create)
        self.assertIn("👑・RΛI ADMIN", plan.categories_to_create)

        # Must include all category channels + emergency channels + voice channels
        total_expected_channels = (
            sum(len(cat["channels"]) for cat in CATEGORIES_SPEC.values())
            + len(EMERGENCY_CHANNELS_SPEC)
            + len(VOICE_CHANNELS_SPEC)
        )
        self.assertEqual(len(plan.channels_to_create), total_expected_channels)

        # Must include all roles across bot, security, music, staff
        total_expected_roles = sum(len(roles) for roles in ROLES_SPEC.values())
        self.assertEqual(len(plan.roles_to_create), total_expected_roles)

        # Guarantees permissions notice
        self.assertTrue(any("Existing Permissions Preserved" in note for note in plan.permission_notes))

    def test_dry_run_plan_preserves_existing_channels_and_avoids_duplicates(self):
        """Verifies existing channels are recognized and NOT duplicated."""
        # Pre-populate existing category and channel
        cat = MagicMock(spec=discord.CategoryChannel)
        cat.name = "🛡️・RΛI SECURITY"
        self.guild.categories = [cat]

        ch = MagicMock(spec=discord.TextChannel)
        ch.name = "🚨・threat-detection"
        self.guild.text_channels = [ch]

        plan = ServerBrandingManager.generate_plan(self.guild, include_voice=False)

        # Category already exists, must not be in categories_to_create
        self.assertNotIn("🛡️・RΛI SECURITY", plan.categories_to_create)

        # Existing channel must not be in channels_to_create
        self.assertFalse(any(c.name == "🚨・threat-detection" for c in plan.channels_to_create))
        self.assertIn("🚨・threat-detection", plan.untouched_channels)

    async def test_apply_plan_executes_safely(self):
        """Verifies apply_plan creates categories and channels without deleting anything."""
        plan = ServerBrandingManager.generate_plan(self.guild, include_voice=False)

        self.guild.create_category = AsyncMock(return_value=MagicMock(spec=discord.CategoryChannel))
        self.guild.create_text_channel = AsyncMock(return_value=MagicMock(spec=discord.TextChannel))
        self.guild.create_role = AsyncMock(return_value=MagicMock(spec=discord.Role))

        results = await ServerBrandingManager.apply_plan(self.guild, plan, self.bot_member)

        self.assertEqual(results["categories_created"], 4)
        self.assertGreater(results["channels_created"], 0)
        self.assertGreater(results["roles_created"], 0)
        self.assertEqual(len(results["errors"]), 0)


if __name__ == "__main__":
    unittest.main()
