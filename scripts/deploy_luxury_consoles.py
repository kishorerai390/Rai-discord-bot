"""
Deploy Luxury Consoles into target Discord channels.
Deploys:
1. Server Pulse & Live Radar -> #📊・SERVER-DASHBOARD (1555283414205075509)
2. Global Timezones & Event Schedule -> #📢・ANNOUNCEMENTS (1545502718792175646)
3. VIP & Booster Concierge -> #📌・SERVER-ROLES (1545502722739150898)
4. Zero-Trust Quarantine Vault -> #🚨・SECURITY-ALERTS (1555283378612478072)
5. Soundscape Studio & Focus Pods -> #💤・SLEEPING-PODS (1555641081578782840)
"""

import asyncio
import os
import sys

sys.path.insert(0, "F:/Bot")

import discord
from dotenv import load_dotenv

from utils.luxury_consoles import (
    build_server_pulse_embed,
    build_server_pulse_view,
    build_world_clock_embed,
    build_world_clock_view,
    build_vip_concierge_embed,
    build_vip_concierge_view,
    build_quarantine_vault_embed,
    build_quarantine_vault_view,
    build_soundscape_embed,
    build_soundscape_view,
)

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

TARGETS = {
    "pulse": 1555283414205075509,       # Server Dashboard
    "clock": 1545502718792175646,       # Announcements
    "vip": 1545502722739150898,         # Server Roles
    "quarantine": 1555283378612478072,  # Security Alerts
    "soundscape": 1555641081578782840,  # Sleeping Pods
}

class DeployClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents)

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")
        guild = self.get_guild(GUILD_ID)
        if not guild:
            print(f"Error: Guild {GUILD_ID} not found.")
            await self.close()
            return

        print(f"Connected to guild: {guild.name}")

        # 1. Deploy Server Pulse
        c_pulse = guild.get_channel(TARGETS["pulse"])
        if c_pulse:
            embed = build_server_pulse_embed(guild, self)
            view = build_server_pulse_view()
            msg = await c_pulse.send(embed=embed, view=view)
            print(f"[OK] Server Pulse deployed in #{c_pulse.name} (Msg ID: {msg.id})")

        # 2. Deploy World Clock & Event Schedule
        c_clock = guild.get_channel(TARGETS["clock"])
        if c_clock:
            embed = build_world_clock_embed(guild)
            view = build_world_clock_view()
            msg = await c_clock.send(embed=embed, view=view)
            print(f"[OK] World Clock & Events deployed in #{c_clock.name} (Msg ID: {msg.id})")

        # 3. Deploy VIP & Booster Concierge
        c_vip = guild.get_channel(TARGETS["vip"])
        if c_vip:
            embed = build_vip_concierge_embed(guild)
            view = build_vip_concierge_view()
            msg = await c_vip.send(embed=embed, view=view)
            print(f"[OK] VIP Concierge deployed in #{c_vip.name} (Msg ID: {msg.id})")

        # 4. Deploy Zero-Trust Quarantine Vault
        c_quar = guild.get_channel(TARGETS["quarantine"])
        if c_quar:
            embed = build_quarantine_vault_embed(guild)
            view = build_quarantine_vault_view()
            msg = await c_quar.send(embed=embed, view=view)
            print(f"[OK] Quarantine Vault deployed in #{c_quar.name} (Msg ID: {msg.id})")

        # 5. Deploy Soundscape Studio & Focus Pods
        c_sound = guild.get_channel(TARGETS["soundscape"])
        if c_sound:
            embed = build_soundscape_embed(guild)
            view = build_soundscape_view()
            msg = await c_sound.send(embed=embed, view=view)
            print(f"[OK] Soundscape Studio deployed in #{c_sound.name} (Msg ID: {msg.id})")

        print("All 5 luxury consoles deployed successfully!")
        await self.close()

async def main():
    client = DeployClient()
    async with client:
        await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
