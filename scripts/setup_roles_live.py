"""
Execution script to run Rai Automatic Role Setup on the live server.
Safe, idempotent, rate-limit aware.
"""

import asyncio
import os
import sys
import discord
from dotenv import load_dotenv

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
if not token:
    print("ERROR: DISCORD_TOKEN is missing")
    sys.exit(1)

from database.database import Database
from utils.role_manager import RoleManager

TARGET_GUILD_ID = 1457382179981099090


class RoleSetupClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents)
        self.db = Database()

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.db.connect()
        guild = self.get_guild(TARGET_GUILD_ID)
        if not guild:
            print(f"ERROR: Guild {TARGET_GUILD_ID} not found")
            await self.db.close()
            await self.close()
            return

        print(f"Target Guild: {guild.name} ({guild.id})")
        print(f"Bot Highest Role: {guild.me.top_role.name} (Position: {guild.me.top_role.position})")
        print(f"Bot Permissions: Manage Roles={guild.me.guild_permissions.manage_roles}")

        # Initialize RoleManager
        manager = RoleManager(self)

        print("\n--- Running setup_guild_roles() ---")
        report = await manager.setup_guild_roles(guild, executor="LIVE_SETUP_SCRIPT")
        print(f"Reused roles: {len(report['reused'])}")
        for r in report['reused']:
            print(f"  [REUSED] {r.encode('ascii', 'replace').decode('ascii')}")

        print(f"Created roles: {len(report['created'])}")
        for c in report['created']:
            print(f"  [CREATED] {c.encode('ascii', 'replace').decode('ascii')}")

        print(f"Skipped roles: {len(report['skipped'])}")
        for s in report['skipped']:
            print(f"  [SKIPPED] {s.encode('ascii', 'replace').decode('ascii')}")

        print(f"Errors: {len(report['errors'])}")
        for e in report['errors']:
            print(f"  [ERROR] {e.encode('ascii', 'replace').decode('ascii')}")

        print("\n--- Verifying Database Mappings ---")
        saved_roles = await self.db.get_all_guild_roles(guild.id)
        print(f"Total roles recorded in DB: {len(saved_roles)}")
        for sr in saved_roles:
            role_obj = guild.get_role(sr.discord_role_id)
            status = f"Valid (pos {role_obj.position})" if role_obj else "MISSING"
            print(f"  key={sr.role_key:<22} discord_id={sr.discord_role_id} name={sr.role_name:<25} type={sr.role_type:<10} [{status}]")

        print("\n--- Verifying Idempotency (Running setup second time) ---")
        second_report = await manager.setup_guild_roles(guild, executor="IDEMPOTENCY_CHECK")
        print(f"Second Run Created: {len(second_report['created'])} (Expected: 0)")
        print(f"Second Run Reused: {len(second_report['reused'])} (Expected: > 0)")

        print("\n--- Checking Role Audit Logs ---")
        audits = await self.db.get_recent_role_audits(guild.id, limit=10)
        print(f"Recent audit logs count: {len(audits)}")
        for a in audits:
            print(f"  [{a.timestamp[:19]}] action={a.action:<20} role_key={a.role_key:<20} success={a.success} reason={a.reason}")

        await self.db.close()
        await self.close()


async def main():
    client = RoleSetupClient()
    async with client:
        await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
