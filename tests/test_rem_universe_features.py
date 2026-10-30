import pytest
from types import SimpleNamespace

from music_bot.database.db import MusicDatabase


@pytest.mark.asyncio
async def test_song_memory_is_private_to_guild_and_user(tmp_path):
    db = MusicDatabase(db_path=tmp_path / "music.db")
    await db.connect()
    try:
        track = SimpleNamespace(url="https://example.test/track", title="Night Drive")
        assert await db.save_song_memory(10, 20, track, "This reminds me of home.")
        assert (await db.get_song_memory(10, 20, track.url))["memory"] == "This reminds me of home."
        assert await db.get_song_memory(10, 21, track.url) is None
        assert await db.get_song_memory(11, 20, track.url) is None
        assert len(await db.list_song_memories(10, 20)) == 1
        assert await db.delete_song_memory(10, 20, track.url)
        assert await db.get_song_memory(10, 20, track.url) is None
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_rem_bond_xp_accumulates_per_guild_user(tmp_path):
    db = MusicDatabase(db_path=tmp_path / "music.db")
    await db.connect()
    try:
        assert await db.get_rem_bond_xp(10, 20) == 0
        assert await db.add_rem_bond_xp(10, 20, 5) == 5
        assert await db.add_rem_bond_xp(10, 20, 1) == 6
        assert await db.get_rem_bond_xp(10, 21) == 0
        assert await db.get_rem_bond_xp(11, 20) == 0
    finally:
        await db.close()
