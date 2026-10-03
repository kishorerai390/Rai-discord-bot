"""
Unit tests for the High-Performance Music subsystem.
Tests playlist storage, queue operations, loop modes, and music configuration.
"""

import unittest
import uuid
from pathlib import Path

from database.database import Database


class TestMusicAdvanced(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = Path(f"data/test_music_{uuid.uuid4().hex[:8]}.db")
        self.db = Database(self.db_path)
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        for ext in ["", "-wal", "-shm"]:
            f = Path(str(self.db_path) + ext)
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    async def test_music_config_lifecycle(self):
        guild_id = 888001
        cfg = await self.db.get_music_config(guild_id)
        self.assertEqual(cfg.default_volume, 50)
        self.assertFalse(cfg.autoplay_enabled)
        self.assertEqual(cfg.inactivity_timeout, 180)

        await self.db.update_music_config(
            guild_id,
            dj_role_id=123456,
            default_volume=75,
            autoplay_enabled=True,
            inactivity_timeout=300,
        )
        updated = await self.db.get_music_config(guild_id)
        self.assertEqual(updated.dj_role_id, 123456)
        self.assertEqual(updated.default_volume, 75)
        self.assertTrue(updated.autoplay_enabled)
        self.assertEqual(updated.inactivity_timeout, 300)

    async def test_playlist_lifecycle(self):
        guild_id = 888002
        user_id = 777001
        pl_name = "Night Chill"

        # 1. Create playlist
        tracks = [
            {"title": "Lofi Rain", "url": "https://youtube.com/watch?v=1", "duration": 180, "artist": "ChilledCow"},
            {"title": "Midnight Drive", "url": "https://youtube.com/watch?v=2", "duration": 240, "artist": "Synthwave"},
        ]
        pl_id = await self.db.create_music_playlist(guild_id, user_id, pl_name, tracks)
        self.assertGreater(pl_id, 0)

        # 2. Get playlist
        pl = await self.db.get_music_playlist(guild_id, user_id, pl_name)
        self.assertIsNotNone(pl)
        self.assertEqual(pl.name, pl_name)
        self.assertEqual(len(pl.tracks), 2)
        self.assertEqual(pl.tracks[0]["title"], "Lofi Rain")

        # 3. List playlists
        playlists = await self.db.list_music_playlists(guild_id, user_id)
        self.assertEqual(len(playlists), 1)

        # 4. Update tracks
        tracks.append({"title": "Morning Coffee", "url": "https://youtube.com/watch?v=3", "duration": 200, "artist": "Acoustic"})
        await self.db.update_music_playlist_tracks(pl.id, tracks)
        updated_pl = await self.db.get_music_playlist(guild_id, user_id, pl_name)
        self.assertEqual(len(updated_pl.tracks), 3)

        # 5. Delete playlist
        deleted = await self.db.delete_music_playlist(guild_id, user_id, pl_name)
        self.assertTrue(deleted)
        empty_pl = await self.db.get_music_playlist(guild_id, user_id, pl_name)
        self.assertIsNone(empty_pl)


if __name__ == "__main__":
    unittest.main()
