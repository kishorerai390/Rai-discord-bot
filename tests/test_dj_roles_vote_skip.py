from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from music_bot.services.dj_access_service import DJAccessService


class FakeChannel:
    def __init__(self, members):
        self.id = 77
        self.members = members


class FakeMember:
    def __init__(self, user_id, channel=None, roles=None, *, admin=False, manage_guild=False):
        self.id = user_id
        self.bot = False
        self.guild = SimpleNamespace(id=123)
        self.voice = SimpleNamespace(channel=channel) if channel else None
        self.roles = roles or []
        self.guild_permissions = SimpleNamespace(
            administrator=admin,
            manage_guild=manage_guild,
        )


class FakeBot:
    def __init__(self, settings):
        self.db = SimpleNamespace(get_guild_settings=AsyncMock(return_value=settings))
        self.get_guild = lambda guild_id: SimpleNamespace(id=guild_id)


def test_required_votes_is_always_ceil_of_fifty_percent():
    assert DJAccessService.required_votes(0) == 1
    assert DJAccessService.required_votes(1) == 1
    assert DJAccessService.required_votes(2) == 1
    assert DJAccessService.required_votes(3) == 2
    assert DJAccessService.required_votes(5) == 3
    assert DJAccessService.required_votes(10) == 5


def test_record_vote_prunes_stale_voters_and_prevents_duplicates():
    votes = {10, 99}
    assert DJAccessService.record_vote(votes, 10, {10, 20, 30}) == 1
    assert DJAccessService.record_vote(votes, 10, {10, 20, 30}) == 1
    assert DJAccessService.record_vote(votes, 20, {10, 20, 30}) == 2
    assert votes == {10, 20}


@pytest.mark.asyncio
async def test_configured_dj_role_grants_immediate_skip_and_stop_access():
    role = SimpleNamespace(id=555)
    member = FakeMember(10, roles=[role])
    settings = SimpleNamespace(dj_role_id=555)
    bot = FakeBot(settings)

    assert await DJAccessService.is_dj(bot, member.guild, member) is True


@pytest.mark.asyncio
async def test_non_dj_requires_fifty_percent_of_voice_members():
    settings = SimpleNamespace(dj_role_id=555)
    bot = FakeBot(settings)
    first = FakeMember(10)
    second = FakeMember(20)
    third = FakeMember(30)
    channel = FakeChannel([first, second, third])
    for member in (first, second, third):
        member.voice = SimpleNamespace(channel=channel)
    voice_client = SimpleNamespace(channel=channel)
    session = SimpleNamespace(
        guild_id=123,
        voice_client=voice_client,
        skip_votes=set(),
    )

    with patch(
        "music_bot.services.player_service.MusicPlayerService.skip",
        new_callable=AsyncMock,
        return_value=(True, "Skipped", None),
    ) as skip:
        success, message, _ = await DJAccessService.request_skip(bot, session, first)
        assert success is False
        assert "1/2" in message
        skip.assert_not_awaited()

        success, message, _ = await DJAccessService.request_skip(bot, session, second)
        assert success is True
        assert "Vote passed" in message
        skip.assert_awaited_once()


@pytest.mark.asyncio
async def test_listener_outside_bot_voice_channel_cannot_vote():
    channel = FakeChannel([])
    member = FakeMember(10, channel=SimpleNamespace(id=78, members=[]))
    session = SimpleNamespace(guild_id=123, voice_client=SimpleNamespace(channel=channel), skip_votes=set())
    bot = FakeBot(SimpleNamespace(dj_role_id=555))

    success, message, _ = await DJAccessService.request_skip(bot, session, member)

    assert success is False
    assert "Join Rem's voice channel" in message
    assert not session.skip_votes


@pytest.mark.asyncio
async def test_admin_can_use_dj_controls_without_configured_role():
    member = FakeMember(10, admin=True)
    bot = FakeBot(SimpleNamespace(dj_role_id=None))

    assert await DJAccessService.is_dj(bot, member.guild, member) is True


@pytest.mark.asyncio
async def test_member_without_dj_role_cannot_stop():
    member = FakeMember(10)
    bot = FakeBot(SimpleNamespace(dj_role_id=555))

    assert await DJAccessService.is_dj(bot, member.guild, member) is False
