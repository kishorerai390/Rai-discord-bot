"""
Rai Community Predictions & Wagering Arena Cog.
Provides:
- /prediction create <question> <option_a> <option_b> [duration_minutes]: Opens a live wagering arena.
- /prediction bet <prediction_id> <option> <amount>: Places wagers with Rai Coins.
- /prediction resolve <prediction_id> <winning_option>: Distributes the total pool proportionally to winners.
- /prediction cancel <prediction_id>: Refunds all wagers.
- /prediction list: Shows active prediction events.
- Interactive Bet Buttons on prediction embeds.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import math
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.PredictionsCog")


class PredictionBetModal(discord.ui.Modal):
    """Modal to place a wager on a prediction."""

    def __init__(self, cog: PredictionsCog, prediction_id: int, option: str, option_label: str):
        super().__init__(title=f"Wager on Option {option.upper()}")
        self.cog = cog
        self.prediction_id = prediction_id
        self.option = option

        self.amount_input = discord.ui.TextInput(
            label=f"Wager Amount ({option_label})",
            placeholder="e.g. 100",
            min_length=1,
            max_length=8,
            required=True,
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Invalid amount. Must be an integer number.", ephemeral=True)
            return

        await self.cog.process_bet(interaction, self.prediction_id, self.option, amount)


class PredictionActionView(discord.ui.View):
    """Interactive view on prediction cards for fast betting."""

    def __init__(self, cog: PredictionsCog, prediction_id: int, label_a: str, label_b: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.prediction_id = prediction_id

        btn_a = discord.ui.Button(
            label=f"Bet {label_a[:30]}",
            style=discord.ButtonStyle.primary,
            custom_id=f"pred_bet:{prediction_id}:a",
            emoji="🔵",
        )
        btn_a.callback = self.bet_a_callback
        self.add_item(btn_a)

        btn_b = discord.ui.Button(
            label=f"Bet {label_b[:30]}",
            style=discord.ButtonStyle.danger,
            custom_id=f"pred_bet:{prediction_id}:b",
            emoji="🔴",
        )
        btn_b.callback = self.bet_b_callback
        self.add_item(btn_b)

    async def bet_a_callback(self, interaction: discord.Interaction):
        pred = await self.cog.get_prediction(self.prediction_id)
        if not pred or pred["status"] != "active":
            await interaction.response.send_message("❌ This prediction event has closed or concluded.", ephemeral=True)
            return
        modal = PredictionBetModal(self.cog, self.prediction_id, "a", pred["option_a"])
        await interaction.response.send_modal(modal)

    async def bet_b_callback(self, interaction: discord.Interaction):
        pred = await self.cog.get_prediction(self.prediction_id)
        if not pred or pred["status"] != "active":
            await interaction.response.send_message("❌ This prediction event has closed or concluded.", ephemeral=True)
            return
        modal = PredictionBetModal(self.cog, self.prediction_id, "b", pred["option_b"])
        await interaction.response.send_modal(modal)


class PredictionsCog(commands.Cog, name="Predictions"):
    """Community Prediction & Wagering Arena."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    async def get_prediction(self, prediction_id: int) -> Optional[dict]:
        async with self.bot.db._db.execute(
            "SELECT * FROM predictions WHERE id = ?", (prediction_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    # ==========================================
    # SLASH COMMAND GROUP: /prediction
    # ==========================================

    prediction_group = app_commands.Group(
        name="prediction",
        description="Community prediction polls and wagering arena",
    )

    @prediction_group.command(name="create", description="Open a new community prediction arena with wagering!")
    @app_commands.describe(
        question="The prediction question or match matchup",
        option_a="Choice A (Blue Corner)",
        option_b="Choice B (Red Corner)",
        duration_minutes="Duration in minutes before wagers close (Default: 60)",
    )
    async def prediction_create(
        self,
        interaction: discord.Interaction,
        question: str,
        option_a: str,
        option_b: str,
        duration_minutes: int = 60,
    ):
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Only Administrators or Moderators can create predictions.", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Available only in servers.", ephemeral=True)
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        ends_dt = now + datetime.timedelta(minutes=max(5, duration_minutes))
        ends_ts = int(ends_dt.timestamp())

        # Insert prediction
        async with self.bot.db._db.execute(
            """
            INSERT INTO predictions 
            (guild_id, creator_id, question, option_a, option_b, total_pool_a, total_pool_b, status, channel_id, ends_at, created_at)
            VALUES (?, ?, ?, ?, ?, 0, 0, 'active', ?, ?, ?)
            """,
            (
                guild.id,
                interaction.user.id,
                question,
                option_a,
                option_b,
                interaction.channel_id,
                ends_dt.isoformat(),
                now.isoformat(),
            ),
        ) as cursor:
            pred_id = cursor.lastrowid
        await self.bot.db._db.commit()

        embed = discord.Embed(
            title=f"📊 『RΛI』 • PREDICTION ARENA #{pred_id}",
            description=(
                f"### {question}\n\n"
                f"Wager your Rai Coins on the outcome! Total pool is distributed proportionally to the winners.\n\n"
                f"• **Closes:** <t:{ends_ts}:R> (<t:{ends_ts}:t>)\n"
                f"• **Status:** `OPEN FOR WAGERS 🟢`"
            ),
            color=0x9B59B6,
        )
        embed.add_field(
            name=f"🔵 Option A: {option_a}",
            value="Pool: `0` Coins • Ratio: `1.00x`",
            inline=True,
        )
        embed.add_field(
            name=f"🔴 Option B: {option_b}",
            value="Pool: `0` Coins • Ratio: `1.00x`",
            inline=True,
        )
        embed.add_field(
            name="💰 Total Prize Pool",
            value="`0` Rai Coins",
            inline=False,
        )
        embed.set_footer(text=f"Prediction #{pred_id} • Click below or use /prediction bet")

        view = PredictionActionView(self, pred_id, option_a, option_b)
        await interaction.response.send_message(embed=embed, view=view)

        # Store message ID
        msg = await interaction.original_response()
        await self.bot.db._db.execute(
            "UPDATE predictions SET message_id = ? WHERE id = ?",
            (msg.id, pred_id),
        )
        await self.bot.db._db.commit()

    @prediction_group.command(name="bet", description="Place a wager on an active prediction")
    @app_commands.describe(
        prediction_id="ID of the prediction",
        option="Which option to bet on (A or B)",
        amount="Amount of Rai Coins to wager",
    )
    @app_commands.choices(
        option=[
            app_commands.Choice(name="Option A (🔵)", value="a"),
            app_commands.Choice(name="Option B (🔴)", value="b"),
        ]
    )
    async def prediction_bet(
        self,
        interaction: discord.Interaction,
        prediction_id: int,
        option: app_commands.Choice[str],
        amount: int,
    ):
        await self.process_bet(interaction, prediction_id, option.value, amount)

    async def process_bet(self, interaction: discord.Interaction, prediction_id: int, option: str, amount: int):
        guild = interaction.guild
        user = interaction.user
        if not guild:
            await interaction.response.send_message("❌ Only available in servers.", ephemeral=True)
            return

        if amount < 10:
            await interaction.response.send_message("❌ Minimum wager is **10 Rai Coins**.", ephemeral=True)
            return
        if amount > 100000:
            await interaction.response.send_message("❌ Maximum wager is **100,000 Rai Coins**.", ephemeral=True)
            return

        pred = await self.get_prediction(prediction_id)
        if not pred:
            await interaction.response.send_message(f"❌ Prediction `#{prediction_id}` does not exist.", ephemeral=True)
            return

        if pred["status"] != "active":
            await interaction.response.send_message("❌ This prediction is no longer accepting wagers.", ephemeral=True)
            return

        # Check user coin balance
        profile = await self.bot.db.get_or_create_user_economy(guild.id, user.id)
        if profile.coins < amount:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Coins", f"You have **{profile.coins:,}** Rai Coins, but tried to bet **{amount:,}**."),
                ephemeral=True,
            )
            return

        # Deduct coins
        await self.bot.db.add_user_coins(guild.id, user.id, -amount)

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # Insert wager
        await self.bot.db._db.execute(
            """
            INSERT INTO prediction_wagers (prediction_id, guild_id, user_id, option, amount, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (prediction_id, guild.id, user.id, option.lower(), amount, now),
        )

        # Update pool
        if option.lower() == "a":
            new_pool_a = pred["total_pool_a"] + amount
            await self.bot.db._db.execute(
                "UPDATE predictions SET total_pool_a = ? WHERE id = ?",
                (new_pool_a, prediction_id),
            )
        else:
            new_pool_b = pred["total_pool_b"] + amount
            await self.bot.db._db.execute(
                "UPDATE predictions SET total_pool_b = ? WHERE id = ?",
                (new_pool_b, prediction_id),
            )
        await self.bot.db._db.commit()

        chosen_name = pred["option_a"] if option.lower() == "a" else pred["option_b"]
        await interaction.response.send_message(
            embed=success_embed(
                "Wager Placed!",
                f"You successfully wagered **{amount:,} Rai Coins** on **{chosen_name}** for Prediction `#{prediction_id}`!\n"
                f"Good luck! Results will pay out automatically when the event is resolved.",
            ),
            ephemeral=True,
        )

    @prediction_group.command(name="resolve", description="Resolve a prediction and distribute payouts to winners")
    @app_commands.describe(
        prediction_id="ID of the prediction to resolve",
        winning_option="The winning choice (Option A or Option B)",
    )
    @app_commands.choices(
        winning_option=[
            app_commands.Choice(name="Option A (🔵)", value="a"),
            app_commands.Choice(name="Option B (🔴)", value="b"),
        ]
    )
    async def prediction_resolve(
        self,
        interaction: discord.Interaction,
        prediction_id: int,
        winning_option: app_commands.Choice[str],
    ):
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Only Administrators or Moderators can resolve predictions.", ephemeral=True)
            return

        pred = await self.get_prediction(prediction_id)
        if not pred:
            await interaction.response.send_message(f"❌ Prediction `#{prediction_id}` not found.", ephemeral=True)
            return

        if pred["status"] != "active":
            await interaction.response.send_message(f"❌ Prediction `#{prediction_id}` is already `{pred['status']}`.", ephemeral=True)
            return

        await interaction.response.defer()

        winner_key = winning_option.value.lower()
        winning_name = pred["option_a"] if winner_key == "a" else pred["option_b"]
        losing_key = "b" if winner_key == "a" else "a"

        pool_win = pred["total_pool_a"] if winner_key == "a" else pred["total_pool_b"]
        pool_lose = pred["total_pool_b"] if winner_key == "a" else pred["total_pool_a"]
        total_pool = pool_win + pool_lose

        # Fetch all wagers for this prediction
        async with self.bot.db._db.execute(
            "SELECT user_id, option, amount FROM prediction_wagers WHERE prediction_id = ?",
            (prediction_id,),
        ) as cursor:
            wagers = await cursor.fetchall()

        winners_count = 0
        total_paid = 0

        if pool_win > 0:
            for w in wagers:
                if w["option"] == winner_key:
                    user_wager = w["amount"]
                    share = user_wager / pool_win
                    payout = int(math.floor(share * total_pool))
                    await self.bot.db.add_user_coins(pred["guild_id"], w["user_id"], payout)
                    winners_count += 1
                    total_paid += payout
        else:
            # No one bet on the winning side; refund losing bets
            for w in wagers:
                await self.bot.db.add_user_coins(pred["guild_id"], w["user_id"], w["amount"])

        # Mark as resolved
        status_val = f"resolved_{winner_key}"
        await self.bot.db._db.execute(
            "UPDATE predictions SET status = ? WHERE id = ?",
            (status_val, prediction_id),
        )
        await self.bot.db._db.commit()

        embed = discord.Embed(
            title=f"🏆 『RΛI』 • PREDICTION #{prediction_id} RESOLVED",
            description=(
                f"### {pred['question']}\n\n"
                f"🎉 **Winning Outcome:** **{winning_name}** ({'🔵 Option A' if winner_key == 'a' else '🔴 Option B'})\n\n"
                f"• **Total Prize Pool:** `{total_pool:,}` Rai Coins\n"
                f"• **Winning Bettors:** `{winners_count}` members\n"
                f"• **Total Payout Dispatched:** `{total_paid:,}` Rai Coins\n\n"
                f"All winners have received their proportional winnings directly in their coin balance!"
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text=f"Prediction #{prediction_id} Settled")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await interaction.followup.send(embed=embed)

    @prediction_group.command(name="cancel", description="Cancel a prediction and refund all placed wagers")
    @app_commands.describe(prediction_id="ID of the prediction to cancel")
    async def prediction_cancel(self, interaction: discord.Interaction, prediction_id: int):
        if not is_admin_or_owner(interaction.user):
            await interaction.response.send_message("❌ Only Administrators or Moderators can cancel predictions.", ephemeral=True)
            return

        pred = await self.get_prediction(prediction_id)
        if not pred:
            await interaction.response.send_message(f"❌ Prediction `#{prediction_id}` not found.", ephemeral=True)
            return

        if pred["status"] != "active":
            await interaction.response.send_message(f"❌ Prediction `#{prediction_id}` is already `{pred['status']}`.", ephemeral=True)
            return

        await interaction.response.defer()

        # Refund all wagers
        async with self.bot.db._db.execute(
            "SELECT user_id, amount FROM prediction_wagers WHERE prediction_id = ?",
            (prediction_id,),
        ) as cursor:
            wagers = await cursor.fetchall()

        for w in wagers:
            await self.bot.db.add_user_coins(pred["guild_id"], w["user_id"], w["amount"])

        await self.bot.db._db.execute(
            "UPDATE predictions SET status = 'cancelled' WHERE id = ?",
            (prediction_id,),
        )
        await self.bot.db._db.commit()

        await interaction.followup.send(
            embed=info_embed(
                "Prediction Cancelled",
                f"Prediction `#{prediction_id}` was cancelled. All **{len(wagers)}** wagers were 100% refunded to members.",
            )
        )

    @prediction_group.command(name="list", description="List active community prediction pools")
    async def prediction_list(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Servers only.", ephemeral=True)
            return

        async with self.bot.db._db.execute(
            "SELECT * FROM predictions WHERE guild_id = ? AND status = 'active' ORDER BY id DESC LIMIT 5",
            (guild.id,),
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message(
                embed=info_embed("No Active Predictions", "There are currently no active predictions. Staff can create one with `/prediction create`!"),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📊 『RΛI』 • ACTIVE PREDICTIONS ARENA",
            description="Participate in live predictions and win big from the community pool!\n",
            color=0x9B59B6,
        )

        for r in rows:
            pool = r["total_pool_a"] + r["total_pool_b"]
            embed.add_field(
                name=f"#{r['id']}: {r['question']}",
                value=(
                    f"• 🔵 **A:** {r['option_a']} (`{r['total_pool_a']:,}` Coins)\n"
                    f"• 🔴 **B:** {r['option_b']} (`{r['total_pool_b']:,}` Coins)\n"
                    f"• 💰 **Total Pool:** `{pool:,}` Rai Coins\n"
                    f"• ⏳ *Bet using `/prediction bet {r['id']} <a/b> <amount>`*"
                ),
                inline=False,
            )

        embed.set_footer(text="RAI Community Predictions")
        await interaction.response.send_message(embed=embed)


async def setup(bot: SentinelBot):
    await bot.add_cog(PredictionsCog(bot))
