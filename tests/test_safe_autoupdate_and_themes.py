import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from music_bot.services.updater_service import MusicAutoUpdater
from web.music_api import MusicApiRouter


class TestSafeAutoUpdateAndThemes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.owner_id = 1457380609641938981
        self.bot.voice_clients = []
        self.auth_manager = MagicMock()
        self.router = MusicApiRouter(self.auth_manager, bot=self.bot)

    async def test_is_voice_busy_idle(self):
        """When no voice clients or empty channels exist, is_voice_busy returns False."""
        self.bot.voice_clients = []
        is_busy, count = MusicAutoUpdater.is_voice_busy(self.bot)
        self.assertFalse(is_busy)
        self.assertEqual(count, 0)

    async def test_is_voice_busy_active_listeners(self):
        """When human members are present in a voice channel, is_voice_busy returns True."""
        mock_channel = MagicMock()
        human_member = MagicMock(bot=False)
        bot_member = MagicMock(bot=True)
        mock_channel.members = [human_member, bot_member]

        mock_vc = MagicMock()
        mock_vc.channel = mock_channel
        self.bot.voice_clients = [mock_vc]

        is_busy, count = MusicAutoUpdater.is_voice_busy(self.bot)
        self.assertTrue(is_busy)
        self.assertEqual(count, 1)

    async def test_get_system_update_status_endpoint(self):
        """Validates GET /api/system/update_status reports git status and voice activity."""
        with patch.object(MusicAutoUpdater, "check_git_updates", new_callable=AsyncMock) as mock_git:
            mock_git.return_value = {
                "is_git": True,
                "has_updates": True,
                "pending_commits": 2,
                "pending_messages": ["feat: add themes", "fix: voice"],
                "current_commit": "b7dd6eb",
                "current_branch": "feature/vocard-bot",
            }
            request = MagicMock(spec=web.Request)
            resp = await self.router.get_system_update_status(request)
            self.assertEqual(resp.status, 200)

            import json
            body = json.loads(resp.text)
            self.assertTrue(body["success"])
            self.assertEqual(body["data"]["pending_commits"], 2)
            self.assertEqual(body["data"]["current_commit"], "b7dd6eb")
            self.assertTrue(body["data"]["safe_to_update"])

    async def test_trigger_system_update_busy_warning(self):
        """Validates trigger_system_update warns when voice is busy and force is False."""
        # Setup active human in voice
        mock_channel = MagicMock()
        mock_channel.members = [MagicMock(bot=False)]
        mock_vc = MagicMock(channel=mock_channel)
        self.bot.voice_clients = [mock_vc]

        request = MagicMock(spec=web.Request)
        request.json = AsyncMock(return_value={"force": False})

        with patch.object(self.router, "_require_authenticated_user", new_callable=AsyncMock) as mock_user:
            mock_user.return_value = {"user_id": "1457380609641938981", "is_admin": True}
            resp = await self.router.trigger_system_update(request)
            self.assertEqual(resp.status, 200)

            import json
            body = json.loads(resp.text)
            self.assertTrue(body["success"])
            self.assertEqual(body["data"]["status"], "warning_busy")
            self.assertEqual(body["data"]["active_listeners"], 1)

    async def test_trigger_system_update_forced_or_idle(self):
        """Validates trigger_system_update pulls and schedules supervisor restart when forced."""
        request = MagicMock(spec=web.Request)
        request.json = AsyncMock(return_value={"force": True})

        with patch.object(self.router, "_require_authenticated_user", new_callable=AsyncMock) as mock_user, \
             patch.object(MusicAutoUpdater, "pull_git_updates", new_callable=AsyncMock) as mock_pull, \
             patch.object(MusicAutoUpdater, "schedule_supervisor_restart") as mock_restart:
            mock_user.return_value = {"user_id": "1457380609641938981", "is_admin": True}
            mock_pull.return_value = (True, "Already up to date.")

            resp = await self.router.trigger_system_update(request)
            self.assertEqual(resp.status, 200)

            import json
            body = json.loads(resp.text)
            self.assertTrue(body["success"])
            self.assertEqual(body["data"]["status"], "restarting")
            mock_restart.assert_called_once()

    def test_ui_contains_theme_and_presence_elements(self):
        """Validates web/ui.py includes theme engine, particles, and DJ presence elements."""
        from web.ui import UI_HTML
        self.assertIn("html[data-theme=\"sakura\"]", UI_HTML)
        self.assertIn("html[data-theme=\"cyberpunk\"]", UI_HTML)
        self.assertIn("html[data-theme=\"lofi\"]", UI_HTML)
        self.assertIn("ambient-particle-canvas", UI_HTML)
        self.assertIn("dj-presence-badge", UI_HTML)
        self.assertIn("dj-crown-badge", UI_HTML)
        self.assertIn("settings-pending-commits", UI_HTML)


if __name__ == "__main__":
    unittest.main()
