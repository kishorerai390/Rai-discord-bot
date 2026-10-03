"""
Safely remove the '⚙️・RΛI SYSTEM' category and its child channels from the live Discord server.
Explicitly authorized by the server owner.
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

import discord


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

        # Find category matching '⚙️・RΛI SYSTEM'
        target_cats = [
            cat for cat in guild.categories
            if "SYSTEM" in cat.name.upper() and ("RΛI" in cat.name.upper() or "RAI" in cat.name.upper() or "⚙" in cat.name)
        ]

        if not target_cats:
            print("No matching category for '⚙️・RΛI SYSTEM' found.")
            await client.close()
            return

        for cat in target_cats:
            print(f"\nProcessing category: '{cat.name}' (ID: {cat.id})")
            channels = list(cat.channels)
            print(f"Found {len(channels)} child channels to remove:")
            for ch in channels:
                print(f"  - Deleting #{ch.name} ({ch.id})...")
                try:
                    await ch.delete(reason="Removed by server administrator request")
                    print(f"    ✓ Deleted #{ch.name}")
                except Exception as e:
                    print(f"    ✗ Failed to delete #{ch.name}: {e}")

            print(f"Deleting category '{cat.name}'...")
            try:
                await cat.delete(reason="Removed by server administrator request")
                print(f"✓ Category '{cat.name}' deleted successfully.")
            except Exception as e:
                print(f"✗ Failed to delete category '{cat.name}': {e}")

        print("\nRemoval complete!")
        await client.close()

    await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
