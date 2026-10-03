"""
Unit tests for the VoiceGuard audio analysis and escalation engine.
"""

import math
import struct
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from cogs.voiceguard import AudioEnergyCalculator, UserVoiceTracker, VoiceGuardEngine
from database.database import Database
from database.migrations import run_migrations


import uuid

class TestVoiceGuard(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = Path(f"data/test_voiceguard_{uuid.uuid4().hex[:8]}.db")
        self.db = Database(self.db_path)
        await self.db.connect()

        self.mock_bot = MagicMock()
        self.mock_bot.db = self.db
        self.engine = VoiceGuardEngine(self.mock_bot)

    async def asyncTearDown(self):
        await self.db.close()
        for ext in ["", "-wal", "-shm"]:
            f = Path(str(self.db_path) + ext)
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    def test_audio_rms_calculation(self):
        # 1. Silence (all zeros) -> 0.0 RMS
        silence = bytes(200)
        rms_silence = AudioEnergyCalculator.calculate_rms(silence)
        self.assertEqual(rms_silence, 0.0)

        # 2. Maximum volume sine/square wave (max 16-bit integer: 32767)
        max_samples = struct.pack("<4h", 32767, 32767, -32767, -32767)
        rms_max = AudioEnergyCalculator.calculate_rms(max_samples)
        self.assertAlmostEqual(rms_max, 1.0, places=2)

    def test_user_voice_tracker_smoothing(self):
        tracker = UserVoiceTracker(user_id=123, smoothing_window_seconds=0.5)
        now = time.monotonic()

        tracker.add_sample(now - 0.4, 0.8)
        tracker.add_sample(now - 0.2, 0.6)
        tracker.add_sample(now, 0.7)

        smoothed = tracker.get_smoothed_level(now)
        self.assertAlmostEqual(smoothed, 0.7, places=2)

    async def test_voiceguard_database_persistence(self):
        guild_id = 777001
        cfg = await self.db.get_voiceguard_config(guild_id)
        self.assertEqual(cfg.automatic_action, "warn")
        self.assertFalse(cfg.enabled)

        # Enable and configure
        await self.db.update_voiceguard_config(
            guild_id,
            enabled=True,
            default_threshold=0.70,
            automatic_action="mute",
        )
        updated = await self.db.get_voiceguard_config(guild_id)
        self.assertTrue(updated.enabled)
        self.assertEqual(updated.default_threshold, 0.70)
        self.assertEqual(updated.automatic_action, "mute")

        # Create voice incident
        inc_id = await self.db.create_voice_incident(
            guild_id=guild_id,
            user_id=456,
            channel_id=789,
            peak_level=0.92,
            average_level=0.75,
            risk_score=70,
            severity="high",
            action_taken="warn",
        )
        self.assertGreater(inc_id, 0)

        incidents = await self.db.get_voice_incidents(guild_id)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].peak_level, 0.92)


if __name__ == "__main__":
    unittest.main()
