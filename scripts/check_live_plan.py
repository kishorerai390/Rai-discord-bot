import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = 1457382179981099090

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import discord
from utils.branding import ServerBrandingManager

async def main():
    intents = discord.Intents.default()
    intents.guilds = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user}")
        guild = client.get_guild(guild_id)
        if not guild:
            print(f"Guild {guild_id} not found!")
            await client.close()
            return

        print(f"Analyzing guild: {guild.name} ({guild.id})")
        plan = ServerBrandingManager.generate_plan(guild, include_voice=True)
        print(f"\n--- PLAN SUMMARY ---")
        print(f"Categories to create ({len(plan.categories_to_create)}):")
        for cat in plan.categories_to_create:
            print(f"  + {cat}")

        print(f"\nChannels to create ({len(plan.channels_to_create)}):")
        for ch in plan.channels_to_create:
            print(f"  + #{ch.name} (Category: {ch.category_name}, Voice={ch.is_voice})")

        print(f"\nRoles to create ({len(plan.roles_to_create)}):")
        for r in plan.roles_to_create:
            print(f"  + {r.name} ({r.group})")

        await client.close()

    await client.start(token)

if __name__ == "__main__":
    asyncio.run(main())
