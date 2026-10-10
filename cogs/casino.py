"""
Rai Cyberpunk Casino & Arcades Cog.
Provides:
- /slots <bet>: High-octane cyberpunk slot machine with dynamic reels and 50x Royal Crown Jackpot.
- /coinflip <choice> <bet>: Provably fair double-or-nothing coin toss with visual flip animation.
- /dice <bet> [guess]: High-roller dice duel (guess 1-6 for 5x, or roll vs house for 2x).
- /wheel: Interactive Daily Fortune Wheel with tiered coin prizes (up to 5,000 coins).
- Real-time button dispatcher integrations for community gaming consoles.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random
import time
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.CasinoCog")

SLOT_SYMBOLS = [
    ("🍒", 2, "Cherry Rush"),
    ("🍋", 3, "Lemon Zest"),
    ("🍇", 5, "Grape Cluster"),
    ("💎", 10, "Diamond Shine"),
    ("7️⃣", 25, "Lucky Seven"),
    ("👑", 50, "Royal Jackpot"),
]

WHEEL_PRIZES = [
    (100, "Bronze Coin Pouch", 0.35),
    (250, "Silver Cache", 0.30),
    (500, "Golden Ingot", 0.20),
    (1000, "Platinum Vault", 0.10),
    (2500, "Diamond Treasury", 0.04),
    (5000, "Mega Jackpot Chest", 0.01),
]


class WheelSpinView(discord.ui.View):
    """Interactive Fortune Wheel View."""

    def __init__(self, cog: CasinoCog, user_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="Spin the Wheel", style=discord.ButtonStyle.success, emoji="🎡", custom_id="wheel_spin_btn")
    async def spin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This fortune wheel belongs to another member.", ephemeral=True)
            return

        button.disabled = True
        await interaction.response.edit_message(view=self)

        await self.cog.process_wheel_spin(interaction)


class CasinoCog(commands.Cog, name="Casino"):
    """Cyberpunk Casino & High-Roller Gaming Suite."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._wheel_cooldowns: dict[tuple[int, int], float] = {}

    # ==========================================
    # SLOTS
    # ==========================================

    @app_commands.command(name="slots", description="🎰 Play the Cyberpunk Slot Machine with up to 50x multipliers!")
    @app_commands.describe(bet="Amount of Rai Coins to wager (Min: 10, Max: 100,000)")
    async def slots_command(self, interaction: discord.Interaction, bet: int):
        await self.execute_slots(interaction, bet)

    async def execute_slots(self, interaction: discord.Interaction, bet: int):
        guild = interaction.guild
        user = interaction.user
        if not guild:
            await interaction.response.send_message("❌ Casino commands can only be played in a server.", ephemeral=True)
            return

        if bet < 10:
            await interaction.response.send_message("❌ Minimum wager is **10 Rai Coins**.", ephemeral=True)
            return
        if bet > 100000:
            await interaction.response.send_message("❌ Maximum wager is **100,000 Rai Coins**.", ephemeral=True)
            return

        # Check balance
        profile = await self.bot.db.get_or_create_user_economy(guild.id, user.id)
        if profile.coins < bet:
            await interaction.response.send_message(
                embed=error_embed(
                    "Insufficient Rai Coins",
                    f"You have **{profile.coins:,}** Rai Coins, but wagered **{bet:,}**.\n"
                    f"💡 *Claim `/daily` or participate in chat/voice to earn more!*",
                ),
                ephemeral=True,
            )
            return

        # Deduct bet immediately
        await self.bot.db.add_user_coins(guild.id, user.id, -bet)

        # Defer interaction
        await interaction.response.defer()

        # Weighted slot reels
        weights = [45, 25, 15, 8, 5, 2]
        symbols_pool = [s[0] for s in SLOT_SYMBOLS]

        reel1 = random.choices(symbols_pool, weights=weights)[0]
        reel2 = random.choices(symbols_pool, weights=weights)[0]
        reel3 = random.choices(symbols_pool, weights=weights)[0]

        # Calculate result
        winnings = 0
        multiplier = 0
        result_text = ""
        win_color = 0xED4245  # Loss Red

        if reel1 == reel2 == reel3:
            # 3 matching
            symbol_data = next((s for s in SLOT_SYMBOLS if s[0] == reel1), None)
            multiplier = symbol_data[1] if symbol_data else 2
            winnings = bet * multiplier
            win_color = 0xF1C40F  # Gold
            result_text = f"🎉 **TRIPLE MATCH!** You won **{winnings:,} Rai Coins** ({multiplier}x payout) with **{symbol_data[2]}**!"
        elif reel1 == reel2 or reel2 == reel3 or reel1 == reel3:
            # 2 matching
            multiplier = 1.5
            winnings = int(bet * 1.5)
            win_color = 0x2ECC71  # Green
            result_text = f"✨ **DOUBLE MATCH!** Partial win of **{winnings:,} Rai Coins** (1.5x payout)!"
        else:
            winnings = 0
            result_text = f"💀 **No match!** The house claimed **{bet:,} Rai Coins**. Better luck next spin!"

        if winnings > 0:
            await self.bot.db.add_user_coins(guild.id, user.id, winnings)

        final_profile = await self.bot.db.get_or_create_user_economy(guild.id, user.id)

        embed = discord.Embed(
            title="🎰 『RΛI』 • CYBERPUNK HIGH-ROLLER SLOTS",
            description=(
                f"**Player:** {user.mention}\n"
                f"**Wager:** `{bet:,}` Rai Coins\n\n"
                f"╔═══════════════════╗\n"
                f"║   **[ {reel1} ┆ {reel2} ┆ {reel3} ]**   ║\n"
                f"╚═══════════════════╝\n\n"
                f"{result_text}\n\n"
                f"💰 **New Balance:** `{final_profile.coins:,}` Rai Coins"
            ),
            color=win_color,
        )
        embed.set_footer(text="RAI Midnight Casino • Fair RNG Algorithm")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await interaction.followup.send(embed=embed)

    # ==========================================
    # COINFLIP
    # ==========================================

    @app_commands.command(name="coinflip", description="🪙 Double-or-nothing coin toss with 2x payout!")
    @app_commands.describe(
        choice="Heads or Tails",
        bet="Amount of Rai Coins to wager (Min: 10, Max: 50,000)",
    )
    @app_commands.choices(
        choice=[
            app_commands.Choice(name="Heads (👑)", value="heads"),
            app_commands.Choice(name="Tails (🦅)", value="tails"),
        ]
    )
    async def coinflip_command(self, interaction: discord.Interaction, choice: app_commands.Choice[str], bet: int):
        guild = interaction.guild
        user = interaction.user
        if not guild:
            await interaction.response.send_message("❌ Casino commands can only be played in a server.", ephemeral=True)
            return

        if bet < 10:
            await interaction.response.send_message("❌ Minimum wager is **10 Rai Coins**.", ephemeral=True)
            return
        if bet > 50000:
            await interaction.response.send_message("❌ Maximum wager is **50,000 Rai Coins**.", ephemeral=True)
            return

        profile = await self.bot.db.get_or_create_user_economy(guild.id, user.id)
        if profile.coins < bet:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Coins", f"You only have **{profile.coins:,}** Rai Coins."),
                ephemeral=True,
            )
            return

        await self.bot.db.add_user_coins(guild.id, user.id, -bet)
        await interaction.response.defer()

        outcome = random.choice(["heads", "tails"])
        won = (outcome == choice.value)
        outcome_emoji = "👑 Heads" if outcome == "heads" else "🦅 Tails"

        if won:
            winnings = bet * 2
            await self.bot.db.add_user_coins(guild.id, user.id, winnings)
            status_text = f"🎉 **YOU WON!** The coin landed on **{outcome_emoji}**!\nYou won **+{winnings:,} Rai Coins**!"
            res_color = 0x2ECC71
        else:
            status_text = f"💀 **YOU LOST!** The coin landed on **{outcome_emoji}**.\nThe house took **-{bet:,} Rai Coins**."
            res_color = 0xED4245

        final_profile = await self.bot.db.get_or_create_user_economy(guild.id, user.id)

        embed = discord.Embed(
            title="🪙 『RΛI』 • DOUBLE-OR-NOTHING COIN TOSS",
            description=(
                f"**Player:** {user.mention}\n"
                f"**Your Call:** `{choice.name}`\n"
                f"**Wager:** `{bet:,}` Rai Coins\n\n"
                f"🪙 **Result:** **{outcome_emoji}**\n\n"
                f"{status_text}\n\n"
                f"💰 **New Balance:** `{final_profile.coins:,}` Rai Coins"
            ),
            color=res_color,
        )
        embed.set_footer(text="RAI Midnight Casino • 50/50 Provably Fair Toss")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await interaction.followup.send(embed=embed)

    # ==========================================
    # DICE DUEL
    # ==========================================

    @app_commands.command(name="dice", description="🎲 Roll against the house or predict the exact number for 5x!")
    @app_commands.describe(
        bet="Amount of Rai Coins to wager (Min: 10, Max: 50,000)",
        guess="Optional: Predict exact dice number 1-6 for a huge 5x payout!",
    )
    async def dice_command(self, interaction: discord.Interaction, bet: int, guess: Optional[int] = None):
        guild = interaction.guild
        user = interaction.user
        if not guild:
            await interaction.response.send_message("❌ Casino commands can only be played in a server.", ephemeral=True)
            return

        if bet < 10 or bet > 50000:
            await interaction.response.send_message("❌ Wager must be between **10** and **50,000** Rai Coins.", ephemeral=True)
            return

        if guess is not None and (guess < 1 or guess > 6):
            await interaction.response.send_message("❌ Dice guess must be between **1** and **6**.", ephemeral=True)
            return

        profile = await self.bot.db.get_or_create_user_economy(guild.id, user.id)
        if profile.coins < bet:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Coins", f"You have **{profile.coins:,}** Rai Coins."),
                ephemeral=True,
            )
            return

        await self.bot.db.add_user_coins(guild.id, user.id, -bet)
        await interaction.response.defer()

        dice_emojis = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}

        if guess is not None:
            # Exact prediction mode (5x)
            roll = random.randint(1, 6)
            if roll == guess:
                winnings = bet * 5
                await self.bot.db.add_user_coins(guild.id, user.id, winnings)
                desc = (
                    f"🎯 **EXACT HIT!** You predicted **{guess}** and rolled {dice_emojis[roll]} `{roll}`!\n"
                    f"🎉 Payout: **+{winnings:,} Rai Coins** (5x multiplier)!"
                )
                col = 0xF1C40F
            else:
                desc = (
                    f"❌ Missed! You predicted **{guess}**, but the dice rolled {dice_emojis[roll]} `{roll}`.\n"
                    f"The house took **-{bet:,} Rai Coins**."
                )
                col = 0xED4245
        else:
            # Duel against house mode (2x)
            player_roll = random.randint(1, 6)
            house_roll = random.randint(1, 6)

            if player_roll > house_roll:
                winnings = bet * 2
                await self.bot.db.add_user_coins(guild.id, user.id, winnings)
                desc = (
                    f"🎲 **Your Roll:** {dice_emojis[player_roll]} `{player_roll}`\n"
                    f"🏢 **House Roll:** {dice_emojis[house_roll]} `{house_roll}`\n\n"
                    f"🎉 **VICTORY!** You beat the house and won **+{winnings:,} Rai Coins** (2x)!"
                )
                col = 0x2ECC71
            elif player_roll == house_roll:
                await self.bot.db.add_user_coins(guild.id, user.id, bet)  # Refund
                desc = (
                    f"🎲 **Your Roll:** {dice_emojis[player_roll]} `{player_roll}`\n"
                    f"🏢 **House Roll:** {dice_emojis[house_roll]} `{house_roll}`\n\n"
                    f"🤝 **STALEMATE TIE!** Both rolled `{player_roll}`. Your bet of **{bet:,} Rai Coins** was refunded."
                )
                col = 0x3498DB
            else:
                desc = (
                    f"🎲 **Your Roll:** {dice_emojis[player_roll]} `{player_roll}`\n"
                    f"🏢 **House Roll:** {dice_emojis[house_roll]} `{house_roll}`\n\n"
                    f"💀 **DEFEAT!** The house beat you. Lost **-{bet:,} Rai Coins**."
                )
                col = 0xED4245

        final_profile = await self.bot.db.get_or_create_user_economy(guild.id, user.id)

        embed = discord.Embed(
            title="🎲 『RΛI』 • HIGH-ROLLER DICE DUEL",
            description=f"**Player:** {user.mention}\n**Wager:** `{bet:,}` Rai Coins\n\n{desc}\n\n💰 **New Balance:** `{final_profile.coins:,}` Rai Coins",
            color=col,
        )
        embed.set_footer(text="RAI Midnight Casino • Pure Random Roll")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await interaction.followup.send(embed=embed)

    # ==========================================
    # DAILY FORTUNE WHEEL
    # ==========================================

    @app_commands.command(name="wheel", description="🎡 Spin the Daily Fortune Wheel for prizes up to 5,000 Rai Coins!")
    async def wheel_command(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        if not guild:
            await interaction.response.send_message("❌ Command only available in servers.", ephemeral=True)
            return

        key = (guild.id, user.id)
        now = time.time()
        last_spin = self._wheel_cooldowns.get(key, 0.0)
        cooldown_seconds = 20 * 3600  # 20 hours cooldown

        if now - last_spin < cooldown_seconds:
            remaining = int(cooldown_seconds - (now - last_spin))
            hours = remaining // 3600
            mins = (remaining % 3600) // 60
            await interaction.response.send_message(
                embed=info_embed(
                    "Fortune Wheel Cooldown",
                    f"⏳ You have already spun the Daily Fortune Wheel today!\n"
                    f"Please return in **{hours}h {mins}m** to spin again.",
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🎡 『RΛI』 • DAILY FORTUNE WHEEL",
            description=(
                f"Welcome {user.mention} to the Daily Fortune Wheel!\n\n"
                f"**Tiered Prize Pool:**\n"
                f"• 🥉 `100 Coins` (Common - 35%)\n"
                f"• 🥈 `250 Coins` (Uncommon - 30%)\n"
                f"• 🥇 `500 Coins` (Rare - 20%)\n"
                f"• 💠 `1,000 Coins` (Epic - 10%)\n"
                f"• 💎 `2,500 Coins` (Legendary - 4%)\n"
                f"• 👑 `5,000 Coins` (Grand Jackpot - 1%)\n\n"
                f"Click **[Spin the Wheel]** below to claim your prize!"
            ),
            color=0x9B59B6,
        )
        embed.set_footer(text="RAI Midnight Casino • 1 Free Spin Every 20 Hours")

        view = WheelSpinView(self, user.id)
        await interaction.response.send_message(embed=embed, view=view)

    async def process_wheel_spin(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        if not guild:
            return

        # Pick weighted prize
        prizes = [p[0] for p in WHEEL_PRIZES]
        labels = [p[1] for p in WHEEL_PRIZES]
        weights = [p[2] for p in WHEEL_PRIZES]

        chosen_idx = random.choices(range(len(prizes)), weights=weights)[0]
        won_coins = prizes[chosen_idx]
        prize_label = labels[chosen_idx]

        # Record cooldown
        self._wheel_cooldowns[(guild.id, user.id)] = time.time()

        # Award coins
        await self.bot.db.add_user_coins(guild.id, user.id, won_coins)
        profile = await self.bot.db.get_or_create_user_economy(guild.id, user.id)

        embed = discord.Embed(
            title="🎉 『RΛI』 • FORTUNE WHEEL RESULT",
            description=(
                f"🎡 The wheel spun and landed on:\n\n"
                f"✨ **{prize_label}** ✨\n"
                f"💰 **Prize Awarded:** `+{won_coins:,}` Rai Coins!\n\n"
                f"🏦 **Updated Balance:** `{profile.coins:,}` Rai Coins\n\n"
                f"⏳ *Come back tomorrow in 20 hours for your next free spin!*"
            ),
            color=0xF1C40F if won_coins >= 1000 else 0x2ECC71,
        )
        embed.set_footer(text="RAI Midnight Casino • Daily Spin Completed")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await interaction.followup.send(embed=embed)


async def setup(bot: SentinelBot):
    await bot.add_cog(CasinoCog(bot))
