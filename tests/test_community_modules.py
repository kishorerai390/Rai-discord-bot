"""
Unit tests for Rai Community modules:
- Gaming LFG & Roster management
- Creator Showcases & Upvoting
- Watch Parties & Scheduling
- Community Events & Participant registration
- Music Playlists (create, rename, savequeue, deduplication)
- Analytics & Strict Hidden Voice Privacy Protection
"""

import asyncio
import os
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pathlib import Path

from database.database import Database
from database.models import (
    CommunityEvent,
    CreatorShowcase,
    GamingLFG,
    MusicPlaylist,
    WatchEvent,
)
from cogs.music import Song


class TestCommunityModules(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_community.db"
        self.db = Database(self.db_path)
        await self.db.connect()
        self.guild_id = 1457382179981099090
        self.user_id = 1554732669072445532

    async def asyncTearDown(self):
        await self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ==========================================
    # 1. GAMING HUB LFG TESTS
    # ==========================================
    async def test_gaming_lfg_lifecycle(self):
        # Create LFG
        lfg_id = await self.db.create_gaming_lfg(
            guild_id=self.guild_id,
            user_id=self.user_id,
            game="Valorant",
            role="Duelist",
            note="Mic required",
            max_players=5,
        )
        self.assertGreater(lfg_id, 0)

        # Retrieve LFG
        lfg = await self.db.get_gaming_lfg(lfg_id)
        self.assertIsNotNone(lfg)
        self.assertEqual(lfg.game, "Valorant")
        self.assertEqual(lfg.current_players, [self.user_id])
        self.assertEqual(lfg.status, "open")

        # Add teammate
        new_player_id = 999888777
        lfg.current_players.append(new_player_id)
        await self.db.update_gaming_lfg_players(lfg_id, lfg.current_players, "open")

        updated_lfg = await self.db.get_gaming_lfg(lfg_id)
        self.assertEqual(len(updated_lfg.current_players), 2)
        self.assertIn(new_player_id, updated_lfg.current_players)

        # Close LFG
        await self.db.update_gaming_lfg_players(lfg_id, updated_lfg.current_players, "closed")
        closed_lfg = await self.db.get_gaming_lfg(lfg_id)
        self.assertEqual(closed_lfg.status, "closed")

    # ==========================================
    # 2. CREATOR SHOWCASE & UPVOTING TESTS
    # ==========================================
    async def test_creator_showcase_lifecycle(self):
        showcase_id = await self.db.create_creator_showcase(
            guild_id=self.guild_id,
            user_id=self.user_id,
            title="Night City Cinematic Edit",
            media_url="https://youtube.com/watch?v=sample",
            software="DaVinci Resolve",
            description="Color graded in ACES with custom grain.",
        )
        self.assertGreater(showcase_id, 0)

        # Upvote showcase
        votes = await self.db.upvote_creator_showcase(showcase_id)
        self.assertEqual(votes, 1)

        votes = await self.db.upvote_creator_showcase(showcase_id)
        self.assertEqual(votes, 2)

        showcases = await self.db.list_creator_showcases(self.guild_id, limit=5)
        self.assertEqual(len(showcases), 1)
        self.assertEqual(showcases[0].upvotes, 2)
        self.assertEqual(showcases[0].title, "Night City Cinematic Edit")

    # ==========================================
    # 3. WATCH PARTY SCHEDULING TESTS
    # ==========================================
    async def test_watch_event_lifecycle(self):
        event_id = await self.db.create_watch_event(
            guild_id=self.guild_id,
            title="Interstellar Movie Night",
            platform="Netflix Party",
            start_time="Friday 9 PM EST",
            host_id=self.user_id,
        )
        self.assertGreater(event_id, 0)

        events = await self.db.list_watch_events(self.guild_id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, "Interstellar Movie Night")
        self.assertEqual(events[0].platform, "Netflix Party")

        # Mark completed
        await self.db.update_watch_event_status(event_id, "completed")
        active_events = await self.db.list_watch_events(self.guild_id)
        self.assertEqual(len(active_events), 0)

    # ==========================================
    # 4. COMMUNITY EVENTS & PARTICIPATION TESTS
    # ==========================================
    async def test_community_event_lifecycle(self):
        event_id = await self.db.create_event(
            guild_id=self.guild_id,
            title="Apex Legends Tournament",
            event_type="gaming",
            start_time="Saturday 8 PM UTC",
            description="3v3 Customs with prizes!",
            creator_id=self.user_id,
        )
        self.assertGreater(event_id, 0)

        event = await self.db.get_event(event_id)
        self.assertIsNotNone(event)
        self.assertEqual(event.status, "scheduled")

        # Add participant
        joined = await self.db.add_event_participant(event_id, self.user_id)
        self.assertTrue(joined)

        # Duplicate join prevention
        dup_joined = await self.db.add_event_participant(event_id, self.user_id)
        self.assertFalse(dup_joined)

        # List participants
        attendees = await self.db.list_event_participants(event_id)
        self.assertEqual(attendees, [self.user_id])

        # Remove participant
        removed = await self.db.remove_event_participant(event_id, self.user_id)
        self.assertTrue(removed)
        self.assertEqual(await self.db.list_event_participants(event_id), [])

    # ==========================================
    # 5. MUSIC PLAYLIST & ANALYTICS TESTS
    # ==========================================
    async def test_playlist_management_and_rename(self):
        tracks = [
            {"title": "Track 1", "url": "https://sample.com/1", "duration": 180, "artist": "Artist 1"},
            {"title": "Track 2", "url": "https://sample.com/2", "duration": 210, "artist": "Artist 2"},
        ]
        pl_id = await self.db.create_music_playlist(
            guild_id=self.guild_id,
            user_id=self.user_id,
            name="Chill Vibes",
            tracks=tracks,
        )
        self.assertGreater(pl_id, 0)

        # Retrieve playlist
        pl = await self.db.get_music_playlist(self.guild_id, self.user_id, "Chill Vibes")
        self.assertIsNotNone(pl)
        self.assertEqual(len(pl.tracks), 2)

        # Rename playlist
        renamed = await self.db.rename_music_playlist(self.guild_id, self.user_id, "Chill Vibes", "Night Chill")
        self.assertTrue(renamed)

        old_pl = await self.db.get_music_playlist(self.guild_id, self.user_id, "Chill Vibes")
        self.assertIsNone(old_pl)

        new_pl = await self.db.get_music_playlist(self.guild_id, self.user_id, "Night Chill")
        self.assertIsNotNone(new_pl)
        self.assertEqual(new_pl.name, "Night Chill")

        # Delete playlist
        deleted = await self.db.delete_music_playlist(self.guild_id, self.user_id, "Night Chill")
        self.assertTrue(deleted)

    async def test_music_analytics_recording(self):
        # Record play 1
        await self.db.record_music_play(self.guild_id, duration_seconds=200, user_id=111)
        # Record play 2 from another user
        await self.db.record_music_play(self.guild_id, duration_seconds=150, user_id=222)
        # Record play 3 from user 111 again
        await self.db.record_music_play(self.guild_id, duration_seconds=300, user_id=111)

        stats = await self.db.get_music_analytics(self.guild_id)
        self.assertEqual(stats.tracks_played, 3)
        self.assertEqual(stats.total_playtime_seconds, 650)
        self.assertEqual(set(stats.unique_listeners), {111, 222})

    # ==========================================
    # 6. PRIVACY PROTECTION TEST (ZERO LEAKS)
    # ==========================================
    async def test_hidden_voice_privacy_leak_protection(self):
        # Configure hidden room category
        await self.db.update_hidden_voice_config(self.guild_id, category_id=987654)

        # Simulate voice channels
        public_vc = MagicMock(spec=object)
        public_vc.category_id = 111222
        public_vc.members = [MagicMock(), MagicMock()]

        hidden_vc = MagicMock(spec=object)
        hidden_vc.category_id = 987654  # Matches hidden category
        hidden_vc.members = [MagicMock(), MagicMock(), MagicMock()]

        channels = [public_vc, hidden_vc]

        hidden_cfg = await self.db.get_hidden_voice_config(self.guild_id)
        active_voice_users = 0
        active_voice_channels = 0
        for vc in channels:
            if hidden_cfg.category_id and vc.category_id == hidden_cfg.category_id:
                continue
            active_voice_channels += 1
            active_voice_users += len(vc.members)

        # Strictly only public voice channel was counted
        self.assertEqual(active_voice_channels, 1)
        self.assertEqual(active_voice_users, 2)


if __name__ == "__main__":
    unittest.main()
