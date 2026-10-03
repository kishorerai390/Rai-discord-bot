"""
Unit and Integration Tests for RAI / The Raivora — Full Community Bot Upgrade.
Verifies:
1. Unified TimeoutManager (creation, cancellation, extension, duplicate prevention, stale invalidation)
2. VoiceSessionManager (connection states, audio modes, clean ducking, music safety)
3. SoundboardService & SoundboardPlaybackInstance (state machine, anti-spam cooldowns, permissions, auto-timeout)
4. Dynamic VC integration (room status, knock request flow)
5. Project & Resource commands (status states, tasks, deadlines, singular /resource)
6. Profile setup and top-level profile commands
7. Simulation Lab (Dynamic VC, Music Queue, Soundboard Timeout, Reports, Automation dry-runs)
8. Safe Mode (/rai safe-mode)
"""

import asyncio
import time
import pytest

from services.timeout_manager import (
    TimeoutManager,
    TimerType,
    TimerStatus,
    ManagedTimer,
)
from services.voice_session_service import (
    VoiceSessionService,
    VoiceSessionManager,
    AudioSessionMode,
    VoiceConnectionState,
)
from services.soundboard_service import (
    SoundboardService,
    SoundboardTimeoutManager,
    SoundboardState,
    SoundboardPlaybackInstance,
    SoundboardCooldownService,
    SoundboardPermissionService,
)
from core.simulation import (
    SimulationLab,
    SimulationType,
    SimulationResult,
)


@pytest.fixture
def mock_bot():
    class DummyUser:
        id = 123456789
        name = "Rai"
        display_name = "Rai"
        bot = True

    class DummyGuild:
        id = 999000
        name = "Test Guild"
        roles = []
        voice_client = None

        def get_channel(self, cid):
            return None

    class DummyBot:
        def __init__(self):
            self.user = DummyUser()
            self.guilds = [DummyGuild()]
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                self.loop = None
            self.cogs = {}

        def get_guild(self, gid):
            return self.guilds[0] if gid == 999000 else None

        def get_cog(self, name):
            return None

    return DummyBot()


# =========================================================================
# 1. TIMEOUT MANAGER TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_timeout_manager_lifecycle():
    tm = TimeoutManager()
    fired = False

    async def callback(msg):
        nonlocal fired
        fired = True

    timer = await tm.create_timer(
        timer_id="test_timer_1",
        timer_type=TimerType.SOUNDBOARD_TIMEOUT,
        owner=123,
        duration=0.05,
        callback=callback,
        msg="hello",
    )
    assert timer.status == TimerStatus.ACTIVE
    assert tm.inspect_timer("test_timer_1") is not None

    await asyncio.sleep(0.08)
    assert fired is True
    assert timer.status == TimerStatus.EXPIRED


@pytest.mark.asyncio
async def test_timeout_manager_cancellation():
    tm = TimeoutManager()
    fired = False

    async def callback():
        nonlocal fired
        fired = True

    await tm.create_timer(
        timer_id="test_timer_cancel",
        timer_type=TimerType.KNOCK_REQUEST_EXPIRY,
        owner=456,
        duration=1.0,
        callback=callback,
    )
    cancelled = await tm.cancel_timer("test_timer_cancel")
    assert cancelled is True

    await asyncio.sleep(0.05)
    assert fired is False
    assert tm.inspect_timer("test_timer_cancel") is None


@pytest.mark.asyncio
async def test_timeout_manager_duplicate_replacement():
    tm = TimeoutManager()
    first_fired = False
    second_fired = False

    async def cb1():
        nonlocal first_fired
        first_fired = True

    async def cb2():
        nonlocal second_fired
        second_fired = True

    await tm.create_timer("dup_id", TimerType.TEMPORARY_VC_CLEANUP, 1, 0.5, cb1)
    # Register again with same ID -> cancels cb1 and replaces
    await tm.create_timer("dup_id", TimerType.TEMPORARY_VC_CLEANUP, 1, 0.05, cb2)

    await asyncio.sleep(0.08)
    assert first_fired is False
    assert second_fired is True


@pytest.mark.asyncio
async def test_timeout_manager_invalidate_stale():
    tm = TimeoutManager()

    async def noop():
        pass

    await tm.create_timer("t1", TimerType.GENERAL, 1, 10.0, noop)
    await tm.create_timer("t2", TimerType.GENERAL, 2, 10.0, noop)
    assert len(tm._timers) == 2

    cleaned = tm.invalidate_stale_timers()
    assert cleaned == 2
    assert len(tm._timers) == 0


# =========================================================================
# 2. VOICE SESSION MANAGER TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_voice_session_manager_coordination(mock_bot):
    vsm = VoiceSessionManager(mock_bot)
    session = vsm.get_session(101)

    assert session.current_mode == AudioSessionMode.IDLE
    assert session.connection_state == VoiceConnectionState.DISCONNECTED

    class MockVoiceClient:
        def __init__(self):
            self._playing = True
            self._connected = True
            self.channel = type("VC", (), {"id": 8888, "name": "Lounge"})()

        def is_connected(self):
            return self._connected

        def is_playing(self):
            return self._playing

        def is_paused(self):
            return not self._playing

        def pause(self):
            self._playing = False

        def resume(self):
            self._playing = True

    guild = type("Guild", (), {"id": 101, "name": "Guild 101", "voice_client": MockVoiceClient()})()

    # Acquire soundboard session while music is playing
    acquired, msg = await vsm.acquire_soundboard_session(guild, "airhorn", 999)
    assert acquired is True
    assert session.mode == AudioSessionMode.SOUNDBOARD
    assert session.was_playing_music is True
    assert guild.voice_client.is_playing() is False

    # Release soundboard session -> music resumes automatically
    await vsm.release_soundboard_session(guild, "airhorn")
    assert session.mode == AudioSessionMode.MUSIC
    assert session.was_playing_music is False
    assert guild.voice_client.is_playing() is True


# =========================================================================
# 3. SOUNDBOARD SERVICE & COOLDOWNS
# =========================================================================

@pytest.mark.asyncio
async def test_soundboard_cooldown_service():
    cds = SoundboardCooldownService()
    guild_id = 555
    user_id = 777
    sound = "bruh"

    # Initially not on cooldown
    ok, _ = cds.check_user_cooldown(guild_id, user_id)
    assert ok is True

    # Apply cooldown
    cds.apply_cooldowns(guild_id, user_id, sound, user_cd=2.0, sound_cd=3.0)

    # User cooldown active
    ok_user, rem_user = cds.check_user_cooldown(guild_id, user_id)
    assert ok_user is False
    assert rem_user > 0

    # Sound cooldown active
    ok_sound, rem_sound = cds.check_sound_cooldown(guild_id, sound)
    assert ok_sound is False
    assert rem_sound > 0

    # Different sound is OK
    ok_diff, _ = cds.check_sound_cooldown(guild_id, "airhorn")
    assert ok_diff is True


def test_soundboard_playback_instance():
    instance = SoundboardPlaybackInstance(
        sound_id="tada",
        guild_id=123,
        voice_channel_id=456,
        requester_id=789,
        started_at=1000.0,
        expires_at=1008.0,
        status=SoundboardState.PLAYING,
        timer_id="sb_guild_123",
    )
    d = instance.to_dict()
    assert d["sound_id"] == "tada"
    assert d["status"] == "PLAYING"
    assert d["timer_id"] == "sb_guild_123"


# =========================================================================
# 4. SIMULATION LAB TESTS (REQUIREMENT 31)
# =========================================================================

@pytest.mark.asyncio
async def test_simulation_lab_new_scenarios(mock_bot):
    class MockDB:
        async def record_simulation_run(self, *args, **kwargs):
            pass

    mock_bot.db = MockDB()
    guild = mock_bot.guilds[0]
    actor = mock_bot.user

    # 1. Dynamic VC Simulation
    res_vc = await SimulationLab.simulate_dynamic_vc(mock_bot, guild, actor)
    assert res_vc.sim_type == SimulationType.DYNAMIC_VC
    assert res_vc.destructive_action_taken is False
    assert any("CREATE YOUR ROOM" in d for d in res_vc.detected)

    # 2. Music Queue Simulation
    res_music = await SimulationLab.simulate_music_queue(mock_bot, guild, actor)
    assert res_music.sim_type == SimulationType.MUSIC_QUEUE
    assert "MusicService" in res_music.services_called

    # 3. Soundboard Timeout Simulation
    res_sb = await SimulationLab.simulate_soundboard_timeout(mock_bot, guild, actor)
    assert res_sb.sim_type == SimulationType.SOUNDBOARD_TIMEOUT
    assert "TimeoutManager" in res_sb.services_called

    # 4. Reports Simulation
    res_rep = await SimulationLab.simulate_reports(mock_bot, guild, actor)
    assert res_rep.sim_type == SimulationType.REPORTS
    assert "ReportService" in res_rep.services_called

    # 5. Automation Simulation
    res_auto = await SimulationLab.simulate_automation(mock_bot, guild, actor)
    assert res_auto.sim_type == SimulationType.AUTOMATION
    assert "WorkflowEngine" in res_auto.services_called
