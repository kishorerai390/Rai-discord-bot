"""
Rai Midnight Economy & Exclusive Perks Shop Cog.
Provides:
- Rai Coins & XP system (Passive earning via chat & voice activity)
- /daily: Daily login rewards with streak multiplier
- /balance & /coins: View wallet & bank
- /profile: Aesthetic midnight member identity card
- /leaderboard: Top wealthy and active members
- /pay: P2P coin transfers
- /shop: Interactive Midnight Perks Shop with automated cosmetic role creation & assignment
- Admin commands for coin management
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random
import time
from typing import TYPE_CHECKING, Dict, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.embeds import create_embed, error_embed, info_embed, success_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

# Perks catalog: (item_id, name, description, cost, role_name, hex_color, emoji)
SHOP_ITEMS = [
    {
        "id": "neon_violet",
        "name": "Neon Violet Glow",
        "desc": "Cosmetic role with a vibrant cyberpunk neon violet name",
        "cost": 1000,
        "role_name": "💜・Neon Violet",
        "color": 0x9B59B6,
        "emoji": "🟣",
    },
    {
        "id": "cyber_cyan",
        "name": "Cyber Cyan Neon",
        "desc": "Cosmetic role with an electric glowing cyan name",
        "cost": 1000,
        "role_name": "💠・Cyber Cyan",
        "color": 0x00F5FF,
        "emoji": "💠",
    },
    {
        "id": "rose_gold",
        "name": "Rose Gold Luxe",
        "desc": "Cosmetic role with an opulent metallic rose pink name",
        "cost": 1000,
        "role_name": "🌸・Rose Gold",
        "color": 0xFF69B4,
        "emoji": "🌸",
    },
    {
        "id": "vip_pass",
        "name": "VIP Lounge Pass",
        "desc": "Exclusive VIP badge role with priority voice suite access",
        "cost": 2500,
        "role_name": "👑・VIP Lounge",
        "color": 0xF1C40F,
        "emoji": "👑",
    },
    {
        "id": "diamond_patron",
        "name": "Diamond Patron",
        "desc": "Prestige diamond status role showcasing supreme server loyalty",
        "cost": 5000,
        "role_name": "💎・Diamond Patron",
        "color": 0x00E5FF,
        "emoji": "💎",
    },
]


class ShopSelectView(discord.ui.View):
    def __init__(self, bot: SentinelBot, user: discord.User | discord.Member):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user

        # Build Select Menu
        options = []
        for item in SHOP_ITEMS:
            options.append(
                discord.SelectOption(
                    label=f"{item['name']} ({item['cost']:,} Coins)",
                    description=item["desc"][:100],
                    value=item["id"],
                    emoji=item["emoji"],
                )
            )

        select = discord.ui.Select(
            placeholder="Select a perk or cosmetic role to purchase...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="rai_shop_select",
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ This shop menu belongs to someone else.", ephemeral=True)
            return

        item_id = interaction.data["values"][0]
        item = next((i for i in SHOP_ITEMS if i["id"] == item_id), None)
        if not item:
            await interaction.response.send_message("❌ Item not found.", ephemeral=True)
            return

        guild = interaction.guild
        member = guild.get_member(interaction.user.id)
        if not member:
            await interaction.response.send_message("❌ Could not resolve member.", ephemeral=True)
            return

        # Check balance
        profile = await self.bot.db.get_or_create_user_economy(guild.id, member.id)
        if profile.coins < item["cost"]:
            needed = item["cost"] - profile.coins
            await interaction.response.send_message(
                embed=error_embed(
                    "Insufficient Rai Coins",
                    f"You have **{profile.coins:,}** Rai Coins.\n"
                    f"You need **{needed:,}** more coins to purchase **{item['name']}**.\n\n"
                    f"💡 *Chat in server or claim `/daily` to earn more!*",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Find or create role
        role = discord.utils.get(guild.roles, name=item["role_name"])
        if not role:
            try:
                # Find position below bot's top role
                bot_member = guild.get_member(self.bot.user.id)
                role = await guild.create_role(
                    name=item["role_name"],
                    color=discord.Color(item["color"]),
                    reason=f"Rai Economy Perks Shop: Created role {item['name']}",
                )
            except discord.Forbidden:
                await interaction.followup.send("❌ I do not have permission to manage roles on this server.", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to create role: {e}", ephemeral=True)
                return

        # Assign role to member
        if role in member.roles:
            await interaction.followup.send(
                embed=info_embed("Already Owned", f"You already have the **{role.name}** role active!"),
                ephemeral=True,
            )
            return

        try:
            await member.add_roles(role, reason=f"Purchased from Rai Shop for {item['cost']} coins")
        except discord.Forbidden:
            await interaction.followup.send("❌ Could not assign role due to role hierarchy permissions.", ephemeral=True)
            return

        # Deduct coins & update database
        purchased = list(profile.purchased_roles or [])
        if item_id not in purchased:
            purchased.append(item_id)

        new_coins = profile.coins - item["cost"]
        await self.bot.db.update_user_economy(
            guild.id,
            member.id,
            coins=new_coins,
            purchased_roles=purchased,
        )

        embed = discord.Embed(
            title="✨ Purchase Successful! Enjoy Your Perk",
            description=(
                f"🎉 Congratulations {member.mention}!\n\n"
                f"You have purchased **{item['emoji']} {item['name']}** for **{item['cost']:,}** Rai Coins.\n"
                f"The role {role.mention} has been added to your profile.\n\n"
                f"💰 **Remaining Balance:** `{new_coins:,}` Rai Coins"
            ),
            color=item["color"],
        )
        embed.set_footer(text="Rai Midnight Economy • RAI FAM💗")
        await interaction.followup.send(embed=embed, ephemeral=True)


class EconomyCog(commands.Cog, name="Economy"):
    """Rai Midnight Economy & Perks Shop."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        # Chat cooldown tracking: (guild_id, user_id) -> float
        self._message_cooldowns: Dict[tuple[int, int], float] = {}

    # ==========================================
    # PASSIVE EARNING LISTENER
    # ==========================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Passive coins & XP for active chatter."""
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return

        # Ignore short commands
        if message.content.startswith(self.bot.command_prefix) or len(message.content.strip()) < 3:
            return

        now = time.monotonic()
        key = (message.guild.id, message.author.id)
        last_time = self._message_cooldowns.get(key, 0.0)

        # 60s cooldown between coin drops
        if now - last_time < 60.0:
            return

        self._message_cooldowns[key] = now

        # Earn 5 to 15 coins & 10 XP
        earned_coins = random.randint(5, 15)
        earned_xp = random.randint(8, 14)

        try:
            profile = await self.bot.db.get_or_create_user_economy(message.guild.id, message.author.id)
            new_xp = profile.xp + earned_xp
            new_coins = profile.coins + earned_coins
            new_level = profile.level

            # Level up check: level * 120 XP needed
            xp_needed = new_level * 120
            leveled_up = False
            if new_xp >= xp_needed:
                new_level += 1
                new_coins += new_level * 50  # Level up bonus
                leveled_up = True

            await self.bot.db.update_user_economy(
                message.guild.id,
                message.author.id,
                coins=new_coins,
                xp=new_xp,
                level=new_level,
            )

            if leveled_up:
                try:
                    await message.channel.send(
                        f"🎉 **Level Up!** {message.author.mention} reached **Level {new_level}**! (+{new_level * 50} bonus Rai Coins! 💰)",
                        delete_after=12.0,
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Passive economy reward error: {e}")

    # ==========================================
    # SLASH COMMANDS
    # ==========================================

    @app_commands.command(name="daily", description="Claim your daily Rai Coins reward with streak bonuses")
    async def daily_cmd(self, interaction: discord.Interaction):
        """Claim daily coins."""
        guild = interaction.guild
        user = interaction.user
        if not guild:
            await interaction.response.send_message("❌ Must be used in a server.", ephemeral=True)
            return

        profile = await self.bot.db.get_or_create_user_economy(guild.id, user.id)
        now_dt = datetime.datetime.now(datetime.timezone.utc)

        # Check last daily
        streak = profile.daily_streak
        if profile.last_daily:
            try:
                last_dt = datetime.datetime.fromisoformat(profile.last_daily)
                delta = now_dt - last_dt
                if delta.total_seconds() < 86400:
                    remaining_sec = int(86400 - delta.total_seconds())
                    hours = remaining_sec // 3600
                    minutes = (remaining_sec % 3600) // 60
                    await interaction.response.send_message(
                        embed=warning_embed(
                            "Daily Already Claimed",
                            f"⏰ You already claimed your daily reward!\n"
                            f"Please return in **{hours}h {minutes}m**.\n\n"
                            f"🔥 Current Streak: **{streak} Days**",
                        ),
                        ephemeral=True,
                    )
                    return
                elif delta.total_seconds() > (86400 * 2):
                    # Missed a day: reset streak
                    streak = 1
                else:
                    streak += 1
            except Exception:
                streak = 1
        else:
            streak = 1

        # Base 250 coins + 50 per streak day (cap at 7 days = 600 coins)
        effective_streak = min(streak, 7)
        streak_bonus = (effective_streak - 1) * 50
        reward = 250 + streak_bonus
        new_coins = profile.coins + reward

        await self.bot.db.update_user_economy(
            guild.id,
            user.id,
            coins=new_coins,
            daily_streak=streak,
            last_daily=now_dt.isoformat(),
        )

        embed = discord.Embed(
            title="💰 Daily Reward Claimed!",
            description=(
                f"You claimed **+{reward:,}** Rai Coins!\n\n"
                f"• **Base Reward:** `250` Coins\n"
                f"• **Streak Bonus:** `+{streak_bonus}` Coins (Day {streak})\n"
                f"• **Total Wallet:** `{new_coins:,}` Rai Coins\n\n"
                f"🔥 **Daily Streak:** `{streak} Days` {'(MAX MULTIPLIER! 🚀)' if streak >= 7 else ''}"
            ),
            color=Colors.SUCCESS,
            timestamp=now_dt,
        )
        embed.set_footer(text="Keep your streak alive by claiming again tomorrow!")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="balance", description="Check your or another member's Rai Coins balance")
    @app_commands.describe(member="Member to check (leave blank for yourself)")
    async def balance_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """View wallet balance."""
        guild = interaction.guild
        target = member or interaction.user
        if not guild:
            await interaction.response.send_message("❌ Must be used in a server.", ephemeral=True)
            return

        profile = await self.bot.db.get_or_create_user_economy(guild.id, target.id)

        embed = discord.Embed(
            title=f"💳 Balance — {target.display_name}",
            color=Colors.PRIMARY,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="💰 Wallet", value=f"**{profile.coins:,}** Rai Coins", inline=True)
        embed.add_field(name="🏦 Bank", value=f"**{profile.bank:,}** Rai Coins", inline=True)
        embed.add_field(name="⭐ Level", value=f"**Lvl {profile.level}** (`{profile.xp}` XP)", inline=True)
        embed.add_field(name="🔥 Daily Streak", value=f"**{profile.daily_streak} Days**", inline=True)
        embed.set_footer(text="Earn coins by chatting, voice activity, and /daily!")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="card", description="Display your exclusive Rai Midnight Member Card")
    @app_commands.describe(member="Member to inspect")
    async def profile_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Aesthetic profile card."""
        guild = interaction.guild
        target = member or interaction.user
        if not guild:
            await interaction.response.send_message("❌ Must be used in a server.", ephemeral=True)
            return

        profile = await self.bot.db.get_or_create_user_economy(guild.id, target.id)

        # Calculate progress to next level
        xp_needed = profile.level * 120
        progress_pct = min(100, int((profile.xp / max(1, xp_needed)) * 100))
        filled_bars = int(progress_pct / 10)
        progress_bar = "▰" * filled_bars + "▱" * (10 - filled_bars)

        # Purchased perks
        perks_list = []
        for pid in (profile.purchased_roles or []):
            item = next((i for i in SHOP_ITEMS if i["id"] == pid), None)
            if item:
                perks_list.append(f"{item['emoji']} {item['name']}")

        perks_str = "\n".join(perks_list) if perks_list else "None yet (Browse `/shop`)"

        embed = discord.Embed(
            title=f"🍸 {target.display_name} — Midnight Identity",
            description=f"Official verified member of **{guild.name}**",
            color=0x9B59B6,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="👑 Rank / Level", value=f"**Level {profile.level}**\n`[{progress_bar}]` {progress_pct}%", inline=True)
        embed.add_field(name="💰 Net Worth", value=f"**{profile.coins + profile.bank:,}** Coins\n(Wallet: {profile.coins:,})", inline=True)
        embed.add_field(name="🔥 Daily Streak", value=f"**{profile.daily_streak} Days**", inline=True)
        embed.add_field(name="✨ Active Perks & Cosmetics", value=perks_str, inline=False)
        embed.set_footer(text="RAI FAM💗 • Midnight Prestige")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="shop", description="Open the Rai Midnight Perks & Neon Cosmetics Shop")
    async def shop_cmd(self, interaction: discord.Interaction):
        """Interactive shop."""
        guild = interaction.guild
        user = interaction.user
        if not guild:
            await interaction.response.send_message("❌ Must be used in a server.", ephemeral=True)
            return

        profile = await self.bot.db.get_or_create_user_economy(guild.id, user.id)

        embed = discord.Embed(
            title="🍸 Rai Midnight Perks & Cosmetics Boutique",
            description=(
                f"Welcome to the official **RAI FAM** perks shop!\n"
                f"Use your hard-earned Rai Coins to unlock custom glowing neon color roles and VIP passes.\n\n"
                f"💰 **Your Balance:** `{profile.coins:,}` Rai Coins\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x9B59B6,
        )

        for item in SHOP_ITEMS:
            embed.add_field(
                name=f"{item['emoji']} {item['name']} — `{item['cost']:,}` Coins",
                value=f"{item['desc']}\n*Role Assigned: `{item['role_name']}`*",
                inline=False,
            )

        embed.set_footer(text="Select an item from the menu below to purchase.")
        view = ShopSelectView(self.bot, user)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="pay", description="Transfer Rai Coins to another member")
    @app_commands.describe(member="Recipient of the coins", amount="Amount of coins to send")
    async def pay_cmd(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        """Send coins."""
        guild = interaction.guild
        sender = interaction.user
        if not guild:
            await interaction.response.send_message("❌ Must be used in a server.", ephemeral=True)
            return

        if member.id == sender.id:
            await interaction.response.send_message("❌ You cannot send coins to yourself!", ephemeral=True)
            return

        if member.bot:
            await interaction.response.send_message("❌ You cannot send coins to a bot.", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be greater than 0.", ephemeral=True)
            return

        sender_profile = await self.bot.db.get_or_create_user_economy(guild.id, sender.id)
        if sender_profile.coins < amount:
            await interaction.response.send_message(
                embed=error_embed("Insufficient Funds", f"You only have **{sender_profile.coins:,}** Rai Coins."),
                ephemeral=True,
            )
            return

        # Deduct from sender, credit to recipient
        await self.bot.db.add_user_coins(guild.id, sender.id, -amount)
        recipient_profile = await self.bot.db.add_user_coins(guild.id, member.id, amount)

        embed = success_embed(
            "Transfer Complete",
            f"💸 {sender.mention} sent **{amount:,}** Rai Coins to {member.mention}!\n\n"
            f"• **Your New Balance:** `{sender_profile.coins - amount:,}` Coins\n"
            f"• **Recipient's Balance:** `{recipient_profile.coins:,}` Coins",
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="View the richest and top-level members in the server")
    @app_commands.describe(category="Rank by Coins or Level")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Richest (Coins)", value="coins"),
            app_commands.Choice(name="Highest Level", value="level"),
        ]
    )
    async def leaderboard_cmd(self, interaction: discord.Interaction, category: Optional[app_commands.Choice[str]] = None):
        """Server leaderboard."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Must be used in a server.", ephemeral=True)
            return

        cat_val = category.value if category else "coins"
        users = await self.bot.db.get_top_economy_users(guild.id, limit=10, order_by=cat_val)

        if not users:
            await interaction.response.send_message(embed=info_embed("Leaderboard", "No activity recorded yet."), ephemeral=True)
            return

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for idx, u in enumerate(users):
            prefix = medals[idx] if idx < 3 else f"`#{idx+1}`"
            member = guild.get_member(u.user_id)
            name = member.display_name if member else f"User {u.user_id}"
            if cat_val == "level":
                lines.append(f"{prefix} **{name}** — Level **{u.level}** (`{u.xp}` XP)")
            else:
                lines.append(f"{prefix} **{name}** — **{u.coins:,}** Rai Coins")

        embed = discord.Embed(
            title=f"🏆 RAI FAM Leaderboard — {'Top Wealth' if cat_val == 'coins' else 'Top Levels'}",
            description="\n".join(lines),
            color=Colors.GOLD,
        )
        embed.set_footer(text="RAI FAM💗 • Midnight Hall of Fame")
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # ADMIN COMMANDS
    # ==========================================

    economy_admin_group = app_commands.Group(
        name="economy_admin",
        description="Administrative economy and balance controls",
        default_permissions=discord.Permissions(administrator=True),
    )

    @economy_admin_group.command(name="add", description="Add coins to a member's wallet")
    @is_admin_or_owner()
    async def admin_add_coins(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
            return
        profile = await self.bot.db.add_user_coins(interaction.guild.id, member.id, amount)
        await interaction.response.send_message(
            embed=success_embed("Coins Added", f"Added **{amount:,}** Rai Coins to {member.mention}.\nNew balance: **{profile.coins:,}** Coins."),
            ephemeral=True,
        )

    @economy_admin_group.command(name="remove", description="Remove coins from a member's wallet")
    @is_admin_or_owner()
    async def admin_remove_coins(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
            return
        profile = await self.bot.db.add_user_coins(interaction.guild.id, member.id, -amount)
        await interaction.response.send_message(
            embed=success_embed("Coins Removed", f"Deducted **{amount:,}** Rai Coins from {member.mention}.\nNew balance: **{profile.coins:,}** Coins."),
            ephemeral=True,
        )


async def setup(bot: SentinelBot):
    await bot.add_cog(EconomyCog(bot))
