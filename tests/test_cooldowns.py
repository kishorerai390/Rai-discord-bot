"""
Automated unit tests for CooldownManager.
Tests monotonic timers, sliding window burst/sustained limits, cancellation, and resets.
"""

import asyncio
import os
import unittest
from pathlib import Path

from database.database import Database
from utils.cooldowns import CooldownManager, CooldownScope

TEST_DB_PATH = Path(__file__).resolve().parent / "test_cd_bot.db"


class TestCooldowns(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if TEST_DB_PATH.exists():
            os.remove(TEST_DB_PATH)
        self.db = Database(TEST_DB_PATH)
        await self.db.connect()
        self.cm = CooldownManager(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        try:
            if TEST_DB_PATH.exists():
                os.remove(TEST_DB_PATH)
            for ext in ["-wal", "-shm"]:
                wal = Path(str(TEST_DB_PATH) + ext)
                if wal.exists():
                    os.remove(wal)
        except Exception:
            pass

    async def test_command_cooldown_reserve_and_expire(self):
        user_id = 12345
        cmd = "play"

        # First call: OK
        limited, retry_after = await self.cm.check_and_reserve(
            scope=CooldownScope.USER_CMD,
            command=cmd,
            user_id=user_id,
            cooldown_seconds=0.2,
        )
        self.assertFalse(limited)
        self.assertEqual(retry_after, 0.0)

        # Immediate second call: Rate limited
        limited2, retry_after2 = await self.cm.check_and_reserve(
            scope=CooldownScope.USER_CMD,
            command=cmd,
            user_id=user_id,
            cooldown_seconds=0.2,
        )
        self.assertTrue(limited2)
        self.assertGreater(retry_after2, 0.0)

        # Wait for expiration
        await asyncio.sleep(0.25)

        # Third call: OK again
        limited3, retry_after3 = await self.cm.check_and_reserve(
            scope=CooldownScope.USER_CMD,
            command=cmd,
            user_id=user_id,
            cooldown_seconds=0.2,
        )
        self.assertFalse(limited3)

    async def test_cancel_cooldown_on_failed_validation(self):
        user_id = 999
        cmd = "ticket"

        # Reserve
        await self.cm.check_and_reserve(
            scope=CooldownScope.USER_CMD,
            command=cmd,
            user_id=user_id,
            cooldown_seconds=10.0,
        )

        # Cancel (e.g. because argument was invalid)
        await self.cm.cancel_cooldown(
            scope=CooldownScope.USER_CMD,
            command=cmd,
            user_id=user_id,
        )

        # Should immediately be allowed again
        limited, _ = await self.cm.check_and_reserve(
            scope=CooldownScope.USER_CMD,
            command=cmd,
            user_id=user_id,
            cooldown_seconds=10.0,
        )
        self.assertFalse(limited)

    async def test_security_sliding_window_burst(self):
        guild_id = 100
        executor_id = 200
        action = "channel_delete"
        limit = 3
        window = 5

        # 1st action
        violated, count, _ = await self.cm.record_security_action(
            guild_id, executor_id, action, limit=limit, window_seconds=window
        )
        self.assertFalse(violated)
        self.assertEqual(count, 1)

        # 2nd action
        violated, count, _ = await self.cm.record_security_action(
            guild_id, executor_id, action, limit=limit, window_seconds=window
        )
        self.assertFalse(violated)
        self.assertEqual(count, 2)

        # 3rd action
        violated, count, _ = await self.cm.record_security_action(
            guild_id, executor_id, action, limit=limit, window_seconds=window
        )
        self.assertFalse(violated)
        self.assertEqual(count, 3)

        # 4th action -> Exceeds limit 3
        violated, count, reason = await self.cm.record_security_action(
            guild_id, executor_id, action, limit=limit, window_seconds=window
        )
        self.assertTrue(violated)
        self.assertEqual(count, 4)
        self.assertIn("Burst limit exceeded", reason)

    async def test_persistent_cooldown(self):
        guild_id = 555
        user_id = 777
        action = "security_lockdown"

        # Check: None
        active, _ = await self.cm.check_persistent_cooldown(guild_id, user_id, action)
        self.assertFalse(active)

        # Set persistent cooldown for 1 second
        await self.cm.set_persistent_cooldown(guild_id, user_id, action, duration_seconds=1)

        # Check: Active
        active2, exp = await self.cm.check_persistent_cooldown(guild_id, user_id, action)
        self.assertTrue(active2)
        self.assertIsNotNone(exp)

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Check: Expired
        active3, _ = await self.cm.check_persistent_cooldown(guild_id, user_id, action)
        self.assertFalse(active3)


if __name__ == "__main__":
    unittest.main()
