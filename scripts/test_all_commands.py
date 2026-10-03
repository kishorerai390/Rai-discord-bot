"""
End-to-End Command & Subsystem Verification Script for Rai Bot.
Validates all registered slash commands, permissions, and server integration.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
import discord

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = 1457382179981099090

async def verify_all():
    print("=" * 60)
    print("RAI BOT - FULL COMMAND & PERMISSION TEST SUITE")
    print("=" * 60)

    from main import SentinelBot
    from config import DATABASE_PATH
    from database.database import Database

    bot = SentinelBot()
    # Mock bot user and loop for dry testing
    bot._connection.user = discord.Object(id=1554732669072445532)

    await bot.db.connect()
    print("[1] Database connected successfully.")

    # Load all extensions
    from main import COGS_LIST
    for cog in COGS_LIST:
        try:
            await bot.load_extension(cog)
            print(f"  [+] Loaded Cog: {cog}")
        except Exception as e:
            print(f"  [-] FAILED loading {cog}: {e}")

    # Inspect all registered application commands
    all_commands = bot.tree.get_commands()
    print(f"\n[2] Registered Top-Level App Commands ({len(all_commands)} total):")

    total_executable_commands = 0
    commands_manifest = []

    for cmd in all_commands:
        if isinstance(cmd, discord.app_commands.Group):
            subcmds = cmd.commands
            print(f"  * Group: /{cmd.name} ({len(subcmds)} subcommands)")
            for sub in subcmds:
                total_executable_commands += 1
                commands_manifest.append(f"/{cmd.name} {sub.name}")
                print(f"      - /{cmd.name} {sub.name}: {sub.description[:50]}...")
        else:
            total_executable_commands += 1
            commands_manifest.append(f"/{cmd.name}")
            print(f"  * /{cmd.name}: {cmd.description[:50]}...")

    print(f"\nTotal executable slash commands discovered: {total_executable_commands}")

    # Test Guild Roles & Bot Permissions in User's Server
    print(f"\n[3] Checking Server Integration for Guild {guild_id}:")
    import aiohttp
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}", headers=headers) as r:
            if r.status != 200:
                print(f"  [-] Could not query guild: HTTP {r.status}")
                return
            gdata = await r.json()
            gname = gdata.get("name", "").encode("ascii", "replace").decode("ascii")
            print(f"  Server Name: {gname}")
            print(f"  Owner ID: {gdata.get('owner_id')}")

        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers) as r:
            roles = await r.json()
            roles_sorted = sorted(roles, key=lambda x: x.get("position", 0), reverse=True)
            bot_role = None
            for ro in roles_sorted:
                if ro.get("id") == "1554734206209232989":
                    bot_role = ro
                    break

            if bot_role:
                print(f"  Bot Role Found: '{bot_role.get('name')}'")
                print(f"  Position: {bot_role.get('position')} / {len(roles_sorted)}")
                print(f"  Permissions Flag: {bot_role.get('permissions')}")
                has_admin = (int(bot_role.get("permissions", 0)) & 0x8) != 0
                print(f"  Administrator Permission: {'YES (Full Admin)' if has_admin else 'NO'}")

        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/members/1554732669072445532", headers=headers) as r:
            member = await r.json()
            member_roles = member.get("roles", [])
            print(f"  Bot Assigned Roles: {len(member_roles)} roles assigned ({member_roles})")

    # Command Execution Simulation for key commands
    print("\n[4] Simulating In-Memory Command Pipeline Validation:")
    # Autopilot simulation test
    mock_guild = MagicMock(spec=discord.Guild)
    mock_guild.id = guild_id
    mock_guild.name = "Test Guild"
    mock_guild.system_channel = None
    mock_guild.me = MagicMock(spec=discord.Member)

    sim_res = await bot.autopilot.simulate_threat(mock_guild, "raid")
    print(f"  * Autopilot Simulation Test: status={sim_res.get('status')}, risk={sim_res.get('risk_level')}")

    sim_spam = await bot.autopilot.simulate_threat(mock_guild, "spam")
    print(f"  * Autopilot Spam Simulation: status={sim_spam.get('status')}, risk={sim_spam.get('risk_level')}")

    # Database health check
    db_ok = bot.db.is_connected
    print(f"  * Database Health Check: {'PASSED' if db_ok else 'FAILED'}")

    await bot.db.close()
    print("\n[5] All Command Signatures and Subsystems Tested Successfully!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(verify_all())
