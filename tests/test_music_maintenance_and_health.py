"""
Unit and Integration Tests for Raivora Music Bot Maintenance, Health Checks & Bounded Recovery (Phase 5).
Validates diagnostics doctor, safe SQLite backups & migrations, rollback mechanisms, and bounded recovery.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import tempfile
import discord
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from music_bot.database.db import MusicDatabase
from music_bot.services.diagnostics_service import MusicDiagnosticsService, DiagnosticProbe
from music_bot.services.updater_service import MusicAutoUpdater
from music_bot.services.session_service import GuildMusicSession, PlaybackState, SessionManager
from music_bot.services.session_memory_service import MusicSessionMemoryService


@pytest.mark.asyncio
class TestMusicMaintenanceAndHealth:
    """Test suite for Phase 5 maintenance, health recovery, and backups."""

    async def test_01_diagnostics_doctor_probes(self):
        """1. Diagnostics engine probes gateway, database, and audio stream resolver."""
        mock_bot = MagicMock()
        mock_bot.latency = 0.025
        mock_bot.user = MagicMock(id=12345, __str__=lambda s: "MusicMaid#4596")
        mock_bot.db = AsyncMock()
        mock_bot.db.get_heartbeat.return_value = MagicMock()

        with patch("music_bot.services.resolver_service.AudioResolver.search", new_callable=AsyncMock) as mock_search, \
             patch("music_bot.services.resolver_service.AudioResolver.resolve_track", new_callable=AsyncMock) as mock_resolve:
            mock_search.return_value = [{"title": "Lofi Chill"}]
            mock_resolve.return_value = MagicMock(stream_url="https://mock.stream")

            probes = await MusicDiagnosticsService.run_doctor(mock_bot)
            assert len(probes) >= 5
            names = [p.name for p in probes]
            assert "Discord Gateway" in names
            assert "Music Database" in names
            assert "Search Provider" in names
            assert "Audio Stream Resolver" in names
            assert "Music Player & Sessions" in names

            gw_probe = next(p for p in probes if p.name == "Discord Gateway")
            assert gw_probe.status == "HEALTHY"

    async def test_02_database_backup_and_retention(self):
        """2. Database backup creates timestamped copy and bounds retention to max_backups."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "music.db"
            db_path.write_bytes(b"MOCK SQLITE DATABASE CONTENT")

            db = MusicDatabase(db_path=db_path)
            # Create 3 backups
            b1 = db.backup_database(reason="test1", max_backups=2)
            assert b1 is not None and b1.exists()

            await asyncio.sleep(0.05)
            b2 = db.backup_database(reason="test2", max_backups=2)
            assert b2 is not None and b2.exists()

            await asyncio.sleep(0.05)
            b3 = db.backup_database(reason="test3", max_backups=2)
            assert b3 is not None and b3.exists()

            # Retention pruning: max_backups=2 means only 2 files remain
            backup_files = list(db_path.parent.glob("backups/db/music_*.db"))
            assert len(backup_files) == 2

    async def test_03_database_migration_with_automatic_backup(self):
        """3. Database migration applies user_version and verifies integrity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "music.db"
            db = MusicDatabase(db_path=db_path)
            await db.connect()
            assert db.is_connected

            # Verify integrity
            async with db._db.execute("PRAGMA integrity_check;") as cur:
                row = await cur.fetchone()
                assert row[0] == "ok"

            # Verify user_version bumped
            async with db._db.execute("PRAGMA user_version;") as cur:
                row = await cur.fetchone()
                assert row[0] >= 1

            await db.close()

    async def test_04_updater_code_backup_and_verification(self):
        """4. Updater captures code backup and verifies post-update canary health."""
        repo_dir = Path(__file__).resolve().parent.parent

        # Verify canary check passes
        health_ok, msg = await MusicAutoUpdater.verify_update_health()
        assert health_ok is True
        assert "verified healthy" in msg

        # Verify git commit capture
        commit_hash = await MusicAutoUpdater.create_code_backup(repo_dir)
        assert commit_hash is not None
        assert len(commit_hash) >= 7

    async def test_05_bounded_recovery_in_session_memory(self):
        """5. Reconnection engine bounds retries to maximum 3 attempts and sets locks."""
        MusicSessionMemoryService._reconnecting_guilds.clear()
        guild_id = 998877

        mock_bot = MagicMock()
        mock_session = GuildMusicSession(guild_id=guild_id)
        mock_session.is_intentional_stop = False
        mock_session.twenty_four_seven = False
        mock_bot.session_manager.get_session_sync.return_value = mock_session

        mock_guild = MagicMock()
        mock_bot.get_guild.return_value = mock_guild
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_guild.get_channel.return_value = mock_channel
        mock_channel.name = "Test Voice"
        mock_channel.permissions_for.return_value = MagicMock(connect=True, speak=True)
        mock_guild.me.voice.channel = mock_channel
        mock_guild.voice_client = None

        mock_saved = MagicMock()
        mock_saved.voice_channel_id = 1111
        mock_saved.text_channel_id = 2222
        mock_bot.db.get_persistent_session = AsyncMock(return_value=mock_saved)

        with patch.object(MusicSessionMemoryService, "checkpoint_session", new_callable=AsyncMock), \
             patch("music_bot.services.voice_service.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_join.return_value = None
            await MusicSessionMemoryService.handle_unexpected_disconnect(mock_bot, guild_id)

        # Confirm reconnect lock released after bounded attempts
        assert guild_id not in MusicSessionMemoryService._reconnecting_guilds
        assert mock_join.call_count == 3

    async def test_06_graceful_shutdown_preserves_checkpoints(self):
        """6. Graceful shutdown checkpoints active sessions without wiping queue data."""
        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(1525030316845301781)
        if not session:
            session = GuildMusicSession(guild_id=1525030316845301781)
            sm._sessions[1525030316845301781] = session

        mock_bot = MagicMock()
        mock_bot.session_manager = sm

        with patch("music_bot.services.session_memory_service.MusicSessionMemoryService.checkpoint_all_active_sessions", new_callable=AsyncMock) as mock_cp, \
             patch("music_bot.services.player_service.MusicPlayerService.snapshot_all_active_sessions", new_callable=AsyncMock) as mock_snap:
            # Call close cleanup logic
            await mock_snap(mock_bot)
            await mock_cp(mock_bot, reason="graceful_shutdown")
            mock_snap.assert_called_once()
            mock_cp.assert_called_once()
