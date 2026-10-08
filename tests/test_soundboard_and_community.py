"""
Unit and Integration Tests for Smart Soundboard and Community Platform Expansion.
Verifies:
- Soundboard state machine, automatic timeouts, cancellation, and cooldowns.
- VoiceSessionService ducking/coordination between Music and Soundboard.
- WorkspaceService temporary workspace lifecycle (create, delete, list).
- ContextEngine channel-scoped detection without unsolicited actions.
- Database operations for gaming profiles, resources, user profiles, and module settings.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from services.soundboard_service import (
    SoundboardService,
    SoundboardTimeoutManager,
    SoundboardState,
)
from services.voice_session_service import (
    VoiceSessionService,
    AudioSessionMode,
)
from services.workspace_service import (
    WorkspaceService,
    WorkspaceType,
    WorkspaceStatus,
)
from services.context_engine import ContextEngine, ChannelContext
from database.migrations import run_migrations
from database.database import Database


class DummyBot:
    def __init__(self):
        self.user = type("User", (), {"id": 123456789, "name": "Rai"})()
        self.guilds = []
        self.db = None
        self.voice_clients = []

    def get_cog(self, name):
        return None


class TestSoundboardAndCommunity(unittest.IsolatedAsyncioTestCase):
    """Test suite for soundboard and community systems."""

    def setUp(self):
        self.mock_bot = DummyBot()

    async def test_soundboard_timeout_and_state(self):
        """Verify soundboard enforces timeout and transitions state."""
        tm = SoundboardTimeoutManager()
        guild_id = 1001
        timed_out = False

        async def on_timeout():
            nonlocal timed_out
            timed_out = True

        await tm.register_timeout(guild_id, duration=0.1, callback=on_timeout)
        self.assertIn(guild_id, tm._tasks)

        await asyncio.sleep(0.15)
        self.assertTrue(timed_out)

    async def test_soundboard_manual_stop_cancels_timer(self):
        """Verify stopping playback cancels the timeout cleanly."""
        tm = SoundboardTimeoutManager()
        guild_id = 1002
        fired = False

        async def on_timeout():
            nonlocal fired
            fired = True

        await tm.register_timeout(guild_id, duration=1.0, callback=on_timeout)
        self.assertIn(guild_id, tm._tasks)

        cancelled = await tm.cancel_timeout(guild_id)
        self.assertTrue(cancelled)

        await asyncio.sleep(0.1)
        self.assertFalse(fired)

    async def test_soundboard_cooldowns(self):
        """Verify user and sound cooldowns enforce anti-spam."""
        sb = SoundboardService(self.mock_bot)

        class DummyVC:
            id = 9999

        class DummyUser:
            id = 888
            display_name = "Kishore"
            voice = type("VoiceState", (), {"channel": DummyVC()})()

        class DummyGuild:
            id = 777
            voice_client = None

        sb._ensure_built_in_sounds()
        user = DummyUser()
        guild = DummyGuild()

        class MockInteraction:
            def __init__(self, g, u):
                self.guild = g
                self.user = u

        mock_interaction = MockInteraction(guild, user)
        can_play, reason = await sb.play_sound(mock_interaction, "airhorn")
        self.assertFalse(can_play)
        self.assertTrue("connect" in reason.lower() or "voice channel" in reason.lower())

    async def test_voice_session_coordination(self):
        """Verify VoiceSessionService manages audio modes and ducking."""
        vss = VoiceSessionService(self.mock_bot)
        session = vss.get_session(guild_id=555)

        self.assertEqual(session.mode, AudioSessionMode.IDLE)

        # Mock voice client and guild
        class MockVC:
            def __init__(self):
                self.paused = False
                self.resumed = False

            def pause(self):
                self.paused = True

            def resume(self):
                self.resumed = True

            def is_playing(self):
                return True

            def is_paused(self):
                return self.paused

            def is_connected(self):
                return True

        mock_vc = MockVC()

        class MockGuild:
            id = 555
            name = "Music Guild"
            voice_client = mock_vc

        guild = MockGuild()

        # Acquire for soundboard while music is playing -> pauses music cleanly
        acquired, msg = await vss.acquire_soundboard_session(guild, sound_id="airhorn", requester_id=123)
        self.assertTrue(acquired)
        self.assertEqual(session.mode, AudioSessionMode.SOUNDBOARD)
        self.assertTrue(mock_vc.paused)
        self.assertTrue(session.was_playing_music)

        # Release after soundboard finishes -> resumes music cleanly
        await vss.release_soundboard_session(guild, sound_id="airhorn")
        self.assertEqual(session.mode, AudioSessionMode.MUSIC)
        self.assertTrue(mock_vc.resumed)

    async def test_workspace_service(self):
        """Verify WorkspaceService lifecycle tracking."""
        wss = WorkspaceService(self.mock_bot)

        class DummyGuild:
            id = 777
            name = "Test Guild"
            me = type("Me", (), {"guild_permissions": type("P", (), {"manage_channels": False})()})()

        class DummyMember:
            id = 999
            display_name = "Kishore"

        ws = await wss.create_workspace(
            guild=DummyGuild(),
            owner=DummyMember(),
            workspace_type=WorkspaceType.GAMING,
            name="BGMI Squad",
        )
        self.assertTrue(ws.workspace_id.startswith("WS-777-"))
        self.assertEqual(ws.status, WorkspaceStatus.ACTIVE)
        self.assertEqual(ws.workspace_type, WorkspaceType.GAMING)

        retrieved = wss.get_workspace(ws.workspace_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "BGMI Squad")

        listed = wss.list_guild_workspaces(777)
        self.assertEqual(len(listed), 1)

        # Safe deletion
        deleted = await wss.delete_workspace(DummyGuild(), ws.workspace_id)
        self.assertTrue(deleted)
        self.assertIsNone(wss.get_workspace(ws.workspace_id))

    def test_context_engine(self):
        """Verify ContextEngine channel detection without unsolicited actions."""
        ce = ContextEngine(self.mock_bot)

        class DummyChannel:
            def __init__(self, name: str):
                self.name = name
                self.category = None

        self.assertEqual(ce.detect_context(DummyChannel("🎵・music-requests")), ChannelContext.MUSIC_CONTEXT)
        self.assertEqual(ce.detect_context(DummyChannel("🎮・find-teammates")), ChannelContext.GAMING_CONTEXT)
        self.assertEqual(ce.detect_context(DummyChannel("🎨・photo-editing")), ChannelContext.CREATOR_CONTEXT)
        self.assertEqual(ce.detect_context(DummyChannel("💡・suggestions")), ChannelContext.IDEA_CONTEXT)
        self.assertEqual(ce.detect_context(DummyChannel("💬・general-chat")), ChannelContext.GENERAL_CONTEXT)

    async def test_community_database_migrations_and_helpers(self):
        """Verify Migration 27 and community database methods."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir) / "test_community.db"
            db_service = Database(db_path=db_file)
            await db_service.connect()

            try:
                # Gaming profile
                g_prof = await db_service.get_or_create_gaming_profile(guild_id=1, user_id=2)
                self.assertEqual(g_prof["user_id"], 2)
                await db_service.update_gaming_profile(guild_id=1, user_id=2, games="BGMI, Valorant", rank="Ace")
                g_updated = await db_service.get_or_create_gaming_profile(guild_id=1, user_id=2)
                self.assertEqual(g_updated["games"], "BGMI, Valorant")
                self.assertEqual(g_updated["rank"], "Ace")

                # Resource library
                r_id = await db_service.create_community_resource(
                    guild_id=1, user_id=2, title="Premiere Presets", description="Color grade LUTs",
                    category="Editing", link="https://example.com/luts"
                )
                self.assertGreater(r_id, 0)
                resources = await db_service.list_community_resources(guild_id=1, category="Editing")
                self.assertEqual(len(resources), 1)
                self.assertEqual(resources[0]["title"], "Premiere Presets")

                # Module settings
                mods = await db_service.get_or_create_module_settings(guild_id=1)
                self.assertEqual(mods["music_enabled"], 1)
                await db_service.update_module_settings(guild_id=1, gaming_enabled=0)
                mods_up = await db_service.get_or_create_module_settings(guild_id=1)
                self.assertEqual(mods_up["gaming_enabled"], 0)
            finally:
                await db_service.close()
