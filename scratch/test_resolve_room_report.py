import os
import sys
import asyncio
sys.path.insert(0, os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from database.database import Database
from utils.owner_reporter import get_owner_report_channel

async def main():
    token = os.getenv("DISCORD_TOKEN")
    intents = discord.Intents.default()
    intents.guilds = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.db = Database("data/bot.db")
    await bot.db.connect()

    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user}")
        cfg = await bot.db.get_owner_reports_config(1457382179981099090)
        print("CFG:", cfg)
        guild = bot.get_guild(1457382179981099090)
        print("GUILD:", guild)
        if not guild:
            guild = await bot.fetch_guild(1457382179981099090)
            print("FETCHED GUILD:", guild)
        ch = await get_owner_report_channel(bot, 1457382179981099090, "room")
        print(f"Resolved room report channel: {ch} (ID: {getattr(ch, 'id', None)})")
        await bot.close()

    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
