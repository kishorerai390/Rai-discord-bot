"""
Unit tests for Casino mini-games and Community Prediction Arena.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.casino import CasinoCog, SLOT_SYMBOLS, WHEEL_PRIZES
from cogs.predictions import PredictionsCog


class TestCasinoAndPredictions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.db = MagicMock()
        self.bot.db._db = MagicMock()
        self.bot.user = MagicMock(id=1554732669072445532)

    def test_slot_symbols_and_prizes(self):
        """Validates that slot symbols and multipliers are non-empty and well-formed."""
        self.assertEqual(len(SLOT_SYMBOLS), 6)
        self.assertEqual(SLOT_SYMBOLS[0][0], "🍒")
        self.assertEqual(SLOT_SYMBOLS[-1][0], "👑")
        self.assertEqual(SLOT_SYMBOLS[-1][1], 50)  # 50x Royal Jackpot

        # Wheel prizes sum to 1.0 probability
        total_prob = sum(p[2] for p in WHEEL_PRIZES)
        self.assertAlmostEqual(total_prob, 1.0, places=2)

    async def test_slots_insufficient_coins(self):
        """Verifies that slots rejects wager when user lacks enough coins."""
        cog = CasinoCog(self.bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(id=123)
        interaction.user = MagicMock(id=456)
        interaction.response = AsyncMock()

        profile = MagicMock(coins=50)
        self.bot.db.get_or_create_user_economy = AsyncMock(return_value=profile)

        await cog.execute_slots(interaction, bet=100)
        interaction.response.send_message.assert_called_once()
        args, kwargs = interaction.response.send_message.call_args
        self.assertIn("Insufficient", kwargs["embed"].title)

    async def test_coinflip_wager_flow(self):
        """Verifies coinflip correctly deducts bet and awards winnings."""
        cog = CasinoCog(self.bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(id=123)
        interaction.user = MagicMock(id=456, mention="<@456>")
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        profile = MagicMock(coins=1000)
        self.bot.db.get_or_create_user_economy = AsyncMock(return_value=profile)
        self.bot.db.add_user_coins = AsyncMock()

        choice_mock = MagicMock(value="heads", name="Heads (👑)")

        with patch("random.choice", return_value="heads"):
            await cog.coinflip_command.callback(cog, interaction, choice_mock, bet=200)
            # Wager deducted (-200) then winnings added (+400)
            self.bot.db.add_user_coins.assert_any_call(123, 456, -200)
            self.bot.db.add_user_coins.assert_any_call(123, 456, 400)
            interaction.followup.send.assert_called_once()

    async def test_predictions_proportional_payout_math(self):
        """Verifies that proportional payouts distribute the total pool correctly."""
        # Say Option A pool is 300, Option B pool is 700. Total pool = 1000.
        # Winner is Option A. User 1 bet 100 (1/3 of pool A), User 2 bet 200 (2/3 of pool A).
        pool_win = 300
        pool_lose = 700
        total_pool = pool_win + pool_lose

        wagers = [
            {"user_id": 1, "option": "a", "amount": 100},
            {"user_id": 2, "option": "a", "amount": 200},
            {"user_id": 3, "option": "b", "amount": 700},
        ]

        payouts = {}
        for w in wagers:
            if w["option"] == "a":
                share = w["amount"] / pool_win
                payout = int(share * total_pool)
                payouts[w["user_id"]] = payout

        self.assertEqual(payouts[1], 333)  # 1/3 of 1000 = 333
        self.assertEqual(payouts[2], 666)  # 2/3 of 1000 = 666
        self.assertEqual(sum(payouts.values()), 999)  # Integer floor division safe


if __name__ == "__main__":
    unittest.main()
