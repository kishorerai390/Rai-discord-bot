"""
Deploy Cyberpunk Server Structure Directly to Live Discord Server.
Creates:
- 4 Categories: 🛡️・RΛI SECURITY, 🎵・RΛI MUSIC, ⚙️・RΛI SYSTEM, 👑・RΛI ADMIN
- 39 Channels (34 text channels + 5 voice channels)
- 14 Roles with distinct futuristic color tokens
Preserves 100% of existing channels, categories, and roles without deletion or alteration.
"""

import asyncio
import os
import sys
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
        print(f"Logged in as {client.user} ({client.user.id})")
        guild = client.get_guild(guild_id)
        if not guild:
            print(f"ERROR: Guild {guild_id} not found!")
            await client.close()
            return

        print(f"Target Guild: {guild.name} ({guild.id})")
        print("Generating structure plan (including voice channels)...")
        plan = ServerBrandingManager.generate_plan(guild, include_voice=True)

        print(f"\nCategories to create: {len(plan.categories_to_create)}")
        print(f"Channels to create: {len(plan.channels_to_create)}")
        print(f"Roles to create: {len(plan.roles_to_create)}")

        bot_member = guild.me
        print("\nExecuting live server deployment...")
        results = await ServerBrandingManager.apply_plan(guild, plan, bot_member)

        print("\n" + "=" * 50)
        print("         DEPLOYMENT COMPLETE          ")
        print("=" * 50)
        print(f"Categories Created: {results['categories_created']}")
        print(f"Channels Created:   {results['channels_created']}")
        print(f"Roles Created:      {results['roles_created']}")
        if results["errors"]:
            print(f"Errors/Warnings ({len(results['errors'])}):")
            for err in results["errors"]:
                print(f"  - {err}")
        else:
            print("Status: 100% Clean Deployment with Zero Errors!")
        print("=" * 50)

        await client.close()

    await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
