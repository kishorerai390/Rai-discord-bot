import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from utils.helpers import ConfirmView, PaginationView, find_audit_executor, format_duration, parse_duration


class TestHelpers(unittest.IsolatedAsyncioTestCase):
    def test_parse_duration_valid(self):
        self.assertEqual(parse_duration("10s"), 10)
        self.assertEqual(parse_duration("5m"), 300)
        self.assertEqual(parse_duration("2h"), 7200)
        self.assertEqual(parse_duration("1d"), 86400)
        self.assertEqual(parse_duration("7D"), 7 * 86400)
        self.assertEqual(parse_duration("  30m  "), 1800)

    def test_parse_duration_invalid(self):
        self.assertIsNone(parse_duration(""))
        self.assertIsNone(parse_duration("invalid"))
        self.assertIsNone(parse_duration("-5m"))
        self.assertIsNone(parse_duration("10x"))
        self.assertIsNone(parse_duration("m10"))
        self.assertIsNone(parse_duration("1.5h"))

    def test_format_duration(self):
        self.assertEqual(format_duration(15), "15s")
        self.assertEqual(format_duration(60), "1m")
        self.assertEqual(format_duration(90), "1m 30s")
        self.assertEqual(format_duration(3600), "1h")
        self.assertEqual(format_duration(3660), "1h 1m")
        self.assertEqual(format_duration(86400), "1d")
        self.assertEqual(format_duration(90000), "1d 1h")

    async def test_confirm_view(self):
        author_id = 12345
        view = ConfirmView(author_id=author_id)
        self.assertIsNone(view.value)

        # Unauthorized user
        interaction_unauth = MagicMock(spec=discord.Interaction)
        interaction_unauth.user.id = 99999
        interaction_unauth.response.send_message = AsyncMock()
        can_interact = await view.interaction_check(interaction_unauth)
        self.assertFalse(can_interact)
        interaction_unauth.response.send_message.assert_awaited_once()

        # Authorized user Confirm
        interaction_auth = MagicMock(spec=discord.Interaction)
        interaction_auth.user.id = author_id
        interaction_auth.response.edit_message = AsyncMock()

        # Find confirm button
        confirm_btn = [c for c in view.children if getattr(c, "label", "") == "Confirm"][0]
        await confirm_btn.callback(interaction_auth)
        self.assertTrue(view.value)
        self.assertTrue(all(item.disabled for item in view.children))
        interaction_auth.response.edit_message.assert_awaited_once_with(view=view)

    async def test_confirm_view_cancel(self):
        author_id = 12345
        view = ConfirmView(author_id=author_id)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user.id = author_id
        interaction.response.edit_message = AsyncMock()

        cancel_btn = [c for c in view.children if getattr(c, "label", "") == "Cancel"][0]
        await cancel_btn.callback(interaction)
        self.assertFalse(view.value)
        self.assertTrue(all(item.disabled for item in view.children))

    async def test_pagination_view(self):
        author_id = 12345
        pages = [discord.Embed(title=f"Page {i}") for i in range(3)]
        view = PaginationView(pages=pages, author_id=author_id)

        # Initial button state
        self.assertEqual(view.current_page, 0)
        self.assertTrue(view.prev_button.disabled)
        self.assertFalse(view.next_button.disabled)

        # Navigate Next
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user.id = author_id
        interaction.response.edit_message = AsyncMock()

        await view.next_button.callback(interaction)
        self.assertEqual(view.current_page, 1)
        self.assertFalse(view.prev_button.disabled)
        self.assertFalse(view.next_button.disabled)

        # Navigate Next to Last Page
        await view.next_button.callback(interaction)
        self.assertEqual(view.current_page, 2)
        self.assertFalse(view.prev_button.disabled)
        self.assertTrue(view.next_button.disabled)

        # Navigate Back
        await view.prev_button.callback(interaction)
        self.assertEqual(view.current_page, 1)

    async def test_find_audit_executor_success(self):
        guild = MagicMock(spec=discord.Guild)
        entry = MagicMock(spec=discord.AuditLogEntry)
        entry.user = MagicMock(spec=discord.Member)
        entry.target = MagicMock()
        entry.target.id = 555
        entry.created_at = discord.utils.utcnow()

        async def mock_audit_logs(limit, action):
            yield entry

        guild.audit_logs = mock_audit_logs

        user, res_entry = await find_audit_executor(
            guild=guild,
            action=discord.AuditLogAction.kick,
            target_id=555,
            max_retries=1,
            delay_seconds=0.01,
        )
        self.assertEqual(user, entry.user)
        self.assertEqual(res_entry, entry)


if __name__ == "__main__":
    unittest.main()
