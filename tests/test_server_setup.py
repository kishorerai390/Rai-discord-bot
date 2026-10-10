import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio

from cogs.server_setup import (
    PROPOSED_STRUCTURE,
    ServerSetupCog,
    ServerSetupConfirmView,
    normalize_name,
)
from database.database import Database


@pytest_asyncio.fixture
async def test_db(tmp_path):
    db_file = tmp_path / "test_bot.db"
    db = Database(str(db_file))
    await db.connect()
    yield db
    await db.close()


def test_proposed_structure_integrity():
    """Verify that the blueprint meets minimal-text channel criteria and has valid data."""
    assert len(PROPOSED_STRUCTURE) == 7
    total_text_channels = 0
    total_voice_channels = 0

    for cat in PROPOSED_STRUCTURE:
        assert "category" in cat
        assert "channels" in cat
        for ch in cat["channels"]:
            assert "name" in ch
            assert "type" in ch
            assert ch["type"] in (0, 2)  # text (0) or voice (2)
            if ch["type"] == 0:
                total_text_channels += 1
            else:
                total_voice_channels += 1

    # Minimal text channel constraint: strictly under 10 public/private text channels
    assert total_text_channels <= 8
    assert total_voice_channels >= 10


def test_normalize_name():
    assert normalize_name("📢・announcements") == "announcements"
    assert normalize_name("💬・chat") == "chat"
    assert normalize_name("🎮・Gaming Lounge") == "gaming lounge"


@pytest.mark.asyncio
async def test_generate_preview_empty_guild():
    bot = MagicMock()
    cog = ServerSetupCog(bot)

    guild = MagicMock()
    guild.categories = []
    guild.text_channels = []
    guild.voice_channels = []

    preview = await cog.generate_preview(guild)
    assert len(preview["categories"]) == len(PROPOSED_STRUCTURE)
    assert len(preview["reused"]) == 0
    assert len(preview["to_create"]) > 0


@pytest.mark.asyncio
async def test_generate_preview_reusing_existing_channels():
    bot = MagicMock()
    cog = ServerSetupCog(bot)

    guild = MagicMock()
    existing_announcements = MagicMock(spec=discord.TextChannel)
    existing_announcements.name = "📢・announcements"
    existing_announcements.id = 2222

    guild.categories = []
    guild.text_channels = [existing_announcements]
    guild.voice_channels = []

    preview = await cog.generate_preview(guild)
    assert len(preview["reused"]) >= 1
    reused_item = next(r for r in preview["reused"] if "announcements" in r["target_name"])
    assert reused_item["action"] == "reuse"
    assert reused_item["existing_id"] == 2222


@pytest.mark.asyncio
async def test_server_setup_confirm_view():
    cog = MagicMock()
    guild = MagicMock()
    view = ServerSetupConfirmView(cog, guild, user_id=12345)

    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.user.id = 99999
    # Unauthorized user interaction check
    res = await view.interaction_check(interaction)
    assert res is False
    interaction.response.send_message.assert_called_once()

    # Authorized author check
    interaction.user.id = 12345
    res = await view.interaction_check(interaction)
    assert res is True


@pytest.mark.asyncio
async def test_server_setup_db_state(test_db):
    guild_id = 987654321
    preview_json = json.dumps({"test": "data"})
    now = "2026-10-10T21:40:00"

    # Insert preview state
    async with test_db._db.execute(
        """
        INSERT INTO server_setup_state (guild_id, status, preview_json, created_at, updated_at)
        VALUES (?, 'previewed', ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            status = 'previewed',
            preview_json = excluded.preview_json,
            updated_at = excluded.updated_at
        """,
        (guild_id, preview_json, now, now),
    ):
        await test_db._db.commit()

    async with test_db._db.execute(
        "SELECT status, preview_json FROM server_setup_state WHERE guild_id = ?",
        (guild_id,),
    ) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "previewed"
        assert json.loads(row[1]) == {"test": "data"}

