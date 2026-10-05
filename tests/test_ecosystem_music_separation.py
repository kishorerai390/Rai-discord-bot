"""
Comprehensive Test Suite for Rai Ecosystem: Main Bot + Independent Music Bot Separation.
Verifies Section 47-50 & 63 acceptance checklist:
- Main Rai and Music Bot use separate Discord applications and separate tokens.
- Main Rai does NOT register music commands.
- Music Bot owns all music commands and aliases.
- Independent database state (data/music.db) and session isolation per guild.
- Concurrency serialization via per-guild locks.
- MusicGateway contract and hot-swappable replacement provider.
- Failure isolation: stopping or breaking Music Bot does not break Main Rai.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from core.bot import COGS_LIST, SentinelBot
from music_bot.commands.music_cog import MusicCog
from music_bot.config import MUSIC_BOT_ID, MUSIC_BOT_TOKEN, is_music_token_valid
from music_bot.database.db import MusicDatabase
from music_bot.database.models import MusicGuildSettings, QueuedTrack
from music_bot.services.diagnostics_service import MusicDiagnosticsService
from music_bot.services.player_service import MusicPlayerService, format_duration
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState, SessionManager
from services.music_gateway import (
    GatewayResult,
    MusicBotStatus,
    MusicGateway,
    MusicGatewayProvider,
    MusicStatusInfo,
    RaiMusicBotProvider,
    ReplacementMusicBotProvider,
)
from services.rai_doctor import DiagnosticStatus, RaiDoctor


class TestMusicEcosystemSeparation(unittest.IsolatedAsyncioTestCase):
    """Rigorous verification of the independent two-bot architecture."""

    async def asyncSetUp(self):
        self.test_dir = Path("scratch/test_music_db")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.test_db_path = self.test_dir / "test_music.db"
        if self.test_db_path.exists():
            self.test_db_path.unlink()

        self.music_db = MusicDatabase(db_path=self.test_db_path)
        await self.music_db.connect()

        self.guild_id_a = 1111111111
        self.guild_id_b = 2222222222
        self.user_id = 9999999999

    async def asyncTearDown(self):
        await self.music_db.close()
        if self.test_db_path.exists():
            self.test_db_path.unlink()
        # Reset MusicGateway provider
        MusicGateway.set_provider(RaiMusicBotProvider())

    # =========================================================================
    # 1. SEPARATE APPLICATIONS & TOKENS
    # =========================================================================

    def test_main_rai_and_music_bot_use_separate_tokens_and_identities(self):
        """Main Rai and Music Bot MUST have distinct tokens and bot applications."""
        main_token = os.getenv("MAIN_RAI_BOT_TOKEN") or os.getenv("DISCORD_TOKEN")
        music_token = os.getenv("MUSIC_BOT_TOKEN")

        self.assertTrue(bool(main_token), "Main Rai bot token must be configured.")
        self.assertTrue(bool(music_token), "Music bot token must be configured.")
        self.assertNotEqual(
            main_token, music_token, "CRITICAL: Main Rai and Music Bot must NOT use the same token!"
        )
        self.assertTrue(is_music_token_valid(), "Music Bot token must have a valid Discord format.")
        self.assertEqual(MUSIC_BOT_ID, 1556676516274905218)

    # =========================================================================
    # 2. COMMAND REGISTRATION SEPARATION
    # =========================================================================

    def test_main_rai_does_not_register_music_commands(self):
        """Main Rai COGS_LIST must not contain music or lyrics cogs."""
        self.assertNotIn("cogs.music", COGS_LIST, "cogs.music must NOT be in Main Rai COGS_LIST.")
        self.assertNotIn("cogs.lyrics", COGS_LIST, "cogs.lyrics must NOT be in Main Rai COGS_LIST.")

    def test_music_bot_owns_all_music_commands_and_aliases(self):
        """MusicCog in music_bot must own all /music commands and top-level aliases."""
        mock_bot = MagicMock()
        cog = MusicCog(mock_bot)

        # Verify /music command group exists
        self.assertTrue(hasattr(cog, "music_group"))
        group = cog.music_group
        group_cmd_names = [cmd.name for cmd in group.commands]

        expected_group_cmds = [
            "play", "pause", "resume", "skip", "previous", "stop",
            "queue", "nowplaying", "volume", "loop", "shuffle",
            "clear", "lyrics", "autoplay", "join", "leave",
            "status", "doctor", "setup"
        ]
        for name in expected_group_cmds:
            self.assertIn(name, group_cmd_names, f"Command /music {name} must exist in MusicCog.")

        # Verify top-level aliases exist on cog
        expected_aliases = [
            "alias_play", "alias_pause", "alias_resume", "alias_skip",
            "alias_stop", "alias_queue", "alias_np", "alias_nowplaying",
            "alias_volume", "alias_lyrics", "alias_shuffle", "alias_loop"
        ]
        for alias in expected_aliases:
            self.assertTrue(hasattr(cog, alias), f"Alias {alias} must be registered on MusicCog.")

    # =========================================================================
    # 3. INDEPENDENT DATABASE SCHEMA & PERSISTENCE
    # =========================================================================

    async def test_music_database_crud_and_guild_isolation(self):
        """Music database operates independently with per-guild settings."""
        # 1. Guild A settings
        settings_a = MusicGuildSettings(
            guild_id=self.guild_id_a,
            request_channel_id=555001,
            dj_role_id=666001,
            default_volume=65,
            autoplay_enabled=True,
            auto_leave_timeout=180,
        )
        await self.music_db.update_guild_settings(settings_a)

        # 2. Guild B settings
        settings_b = MusicGuildSettings(
            guild_id=self.guild_id_b,
            request_channel_id=555002,
            default_volume=90,
            autoplay_enabled=False,
        )
        await self.music_db.update_guild_settings(settings_b)

        # Fetch and verify complete isolation
        fetched_a = await self.music_db.get_guild_settings(self.guild_id_a)
        fetched_b = await self.music_db.get_guild_settings(self.guild_id_b)

        self.assertEqual(fetched_a.request_channel_id, 555001)
        self.assertEqual(fetched_a.default_volume, 65)
        self.assertTrue(fetched_a.autoplay_enabled)

        self.assertEqual(fetched_b.request_channel_id, 555002)
        self.assertEqual(fetched_b.default_volume, 90)
        self.assertFalse(fetched_b.autoplay_enabled)

    async def test_music_heartbeat_telemetry(self):
        """Heartbeats written by Music Bot can be read by external observers."""
        await self.music_db.update_heartbeat(
            bot_id=MUSIC_BOT_ID,
            version="2.0.0",
            status="ONLINE",
            active_sessions=3,
            playing_count=2,
        )

        hb = await self.music_db.get_heartbeat(MUSIC_BOT_ID)
        self.assertIsNotNone(hb)
        self.assertEqual(hb.bot_id, MUSIC_BOT_ID)
        self.assertEqual(hb.status, "ONLINE")
        self.assertEqual(hb.active_sessions, 3)
        self.assertEqual(hb.playing_count, 2)

    # =========================================================================
    # 4. SESSION CONCURRENCY & ISOLATION
    # =========================================================================

    async def test_session_manager_guild_isolation(self):
        """Guild A music session must be completely isolated from Guild B."""
        sm = SessionManager()

        session_a = await sm.get_session(self.guild_id_a)
        session_b = await sm.get_session(self.guild_id_b)

        self.assertIsNot(session_a, session_b)
        self.assertNotEqual(session_a.guild_id, session_b.guild_id)

        # Add track to Guild A
        track_a = QueuedTrack(
            title="Track A",
            url="https://youtube.com/watch?v=trackA",
            stream_url="http://streamA",
            duration=210,
            requester_id=self.user_id,
            requester_name="UserA",
        )
        session_a.queue.append(track_a)
        session_a.volume = 50
        session_a.state = PlaybackState.PLAYING

        # Verify Guild B is completely unaffected
        self.assertEqual(len(session_a.queue), 1)
        self.assertEqual(len(session_b.queue), 0)
        self.assertEqual(session_b.volume, 80)
        self.assertEqual(session_b.state, PlaybackState.IDLE)

    async def test_session_lock_serializes_concurrent_operations(self):
        """Concurrent skip/play operations are serialized through session.lock."""
        session = GuildMusicSession(self.guild_id_a)
        execution_order = []

        async def worker(num: int, delay: float):
            async with session.lock:
                execution_order.append(f"start_{num}")
                await asyncio.sleep(delay)
                execution_order.append(f"end_{num}")

        # Run 2 concurrent conflicting operations
        await asyncio.gather(worker(1, 0.05), worker(2, 0.01))

        # Must be strictly serialized (start_1 -> end_1 -> start_2 -> end_2)
        self.assertEqual(execution_order, ["start_1", "end_1", "start_2", "end_2"])

    # =========================================================================
    # 5. MUSIC GATEWAY & HOT-SWAPPABLE REPLACEMENT
    # =========================================================================

    async def test_music_gateway_rai_music_bot_provider(self):
        """MusicGateway queries real status without fake data."""
        # 1. Guild where Music Bot is NOT installed
        mock_guild_uninstalled = MagicMock(spec=discord.Guild)
        mock_guild_uninstalled.get_member.return_value = None

        provider = RaiMusicBotProvider(db_path=self.test_db_path, bot_id=MUSIC_BOT_ID)
        status_uninstalled = await provider.get_status(mock_guild_uninstalled)
        self.assertEqual(status_uninstalled.status, MusicBotStatus.NOT_INSTALLED)
        self.assertEqual(status_uninstalled.badge, "⚪ NOT INSTALLED")

        # 2. Guild where Music Bot IS installed and reporting recent heartbeat
        mock_member = MagicMock()
        mock_member.name = "Rai Music"
        mock_guild_installed = MagicMock(spec=discord.Guild)
        mock_guild_installed.get_member.return_value = mock_member

        # Write fresh heartbeat
        await self.music_db.update_heartbeat(
            bot_id=MUSIC_BOT_ID,
            version="2.0.0",
            status="ONLINE",
            active_sessions=1,
            playing_count=1,
        )

        status_installed = await provider.get_status(mock_guild_installed)
        self.assertEqual(status_installed.status, MusicBotStatus.CONNECTED)
        self.assertEqual(status_installed.badge, "🟢 CONNECTED")
        self.assertEqual(status_installed.active_sessions, 1)

    async def test_music_gateway_hot_swap_replacement_provider(self):
        """Proves Section 35 & 50: Music Bot can be replaced behind MusicGateway with ZERO Main Rai changes."""
        # Active default provider
        self.assertIsInstance(MusicGateway.get_provider(), RaiMusicBotProvider)

        # Hot-swap to ReplacementMusicBotProvider
        replacement = ReplacementMusicBotProvider(bot_name="NextGen Audio", bot_id=888777666)
        MusicGateway.set_provider(replacement)

        self.assertIsInstance(MusicGateway.get_provider(), ReplacementMusicBotProvider)
        status = await MusicGateway.get_status()
        self.assertEqual(status.bot_name, "NextGen Audio")
        self.assertEqual(status.status, MusicBotStatus.CONNECTED)

        res = await MusicGateway.play(self.guild_id_a, "lofi hip hop", self.user_id)
        self.assertTrue(res.success)
        self.assertIn("NextGen Audio", res.message)

    # =========================================================================
    # 6. RAI DOCTOR DIAGNOSTICS DECOUPLING
    # =========================================================================

    async def test_rai_doctor_music_gateway_diagnostic(self):
        """RaiDoctor audits MusicGateway without crashing if Music Bot is absent or offline."""
        mock_bot = MagicMock(spec=discord.Client)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_member.return_value = None  # Not installed

        provider = RaiMusicBotProvider(db_path=self.test_db_path, bot_id=MUSIC_BOT_ID)
        MusicGateway.set_provider(provider)

        diag = await RaiDoctor.diagnose_music_gateway(mock_bot, mock_guild)
        self.assertEqual(diag.name, "Music Gateway")
        self.assertEqual(diag.status, DiagnosticStatus.DISABLED)
        self.assertIn("Invite the independent Rai Music Bot", diag.repair_action)

    # =========================================================================
    # 7. FORMATTING & DURATION LOGIC
    # =========================================================================

    def test_format_duration(self):
        """Verifies duration formatting for MM:SS and HH:MM:SS."""
        self.assertEqual(format_duration(0), "LIVE / Unknown")
        self.assertEqual(format_duration(65), "01:05")
        self.assertEqual(format_duration(3665), "01:01:05")
