import asyncio
import os
import sys
from pathlib import Path

# Force UTF-8 stdout
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, "f:/Bot")

import discord
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_GUILD_ID = 1457382179981099090

from database.database import Database

async def run_review():
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    db = Database(Path("data/bot.db"))
    await db.connect()

    @client.event
    async def on_ready():
        guild = client.get_guild(TARGET_GUILD_ID)
        if not guild:
            print(f"Error: Guild {TARGET_GUILD_ID} not found.")
            await client.close()
            return

        print("=" * 60)
        print(f"🏰 SERVER AUDIT & REVIEW: {guild.name} ({guild.id})")
        print("=" * 60)

        # 1. Guild Overview
        total_members = len(guild.members)
        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)
        online = sum(1 for m in guild.members if m.status != discord.Status.offline)
        owner = guild.owner

        print(f"👑 Server Owner: {owner} (ID: {guild.owner_id})")
        print(f"👥 Member Count: {total_members} Total | {humans} Humans | {bots} Bots | {online} Online")
        print(f"📁 Categories: {len(guild.categories)}")
        print(f"💬 Text Channels: {len(guild.text_channels)}")
        print(f"🔊 Voice Channels: {len(guild.voice_channels)}")
        print(f"🎭 Roles: {len(guild.roles)}")
        print(f"✨ Boost Level: Tier {guild.premium_tier} ({guild.premium_subscription_count} Boosts)")

        # 2. Category Breakdown
        print("\n--- CATEGORIES & CHANNELS MAP ---")
        for cat in guild.categories:
            print(f"📁 [{cat.position:02d}] {cat.name} ({len(cat.channels)} channels)")
            for ch in cat.channels[:3]:  # sample preview
                type_sym = "💬" if isinstance(ch, discord.TextChannel) else "🔊"
                print(f"    {type_sym} {ch.name}")
            if len(cat.channels) > 3:
                print(f"    ... and {len(cat.channels) - 3} more")

        # 3. Verification & Onboarding Check
        print("\n--- ONBOARDING & VERIFICATION AUDIT ---")
        verify_ch = discord.utils.find(lambda c: "verify" in c.name.lower(), guild.text_channels)
        verified_role = discord.utils.find(lambda r: "verified" in r.name.lower(), guild.roles)

        if verify_ch:
            print(f"✅ Verification channel found: #{verify_ch.name} (ID: {verify_ch.id}, Pos: {verify_ch.position})")
            everyone_ow = verify_ch.overwrites_for(guild.default_role)
            print(f"   @everyone Read Messages: {everyone_ow.read_messages}")
            print(f"   @everyone Send Messages: {everyone_ow.send_messages}")
        else:
            print("⚠️ Verification channel NOT found!")

        if verified_role:
            print(f"✅ Verified Role: {verified_role.name} (ID: {verified_role.id}, Position: {verified_role.position})")
        else:
            print("⚠️ Verified Role NOT found!")

        # Unverified view isolation check
        unverified_visible_count = 0
        for ch in guild.channels:
            if isinstance(ch, discord.CategoryChannel):
                continue
            ow = ch.overwrites_for(guild.default_role)
            # Default is visible unless denied
            if ow.read_messages is True or (ow.read_messages is None and ch.category and ch.category.overwrites_for(guild.default_role).read_messages is not False):
                if ch.id != getattr(verify_ch, 'id', None):
                    unverified_visible_count += 1
        print(f"🔒 Unverified User Isolation: {unverified_visible_count} channels publicly visible without role (Ideal: Only verification channel & rules)")

        # 4. Hidden Voice Subsystem Check
        print("\n--- HIDDEN ROOMS SUBSYSTEM AUDIT ---")
        hidden_cat = discord.utils.find(lambda c: "HIDDEN ROOMS" in c.name.upper(), guild.categories)
        hidden_entry = discord.utils.find(lambda c: "CREATE PRIVATE ROOM" in c.name.upper(), guild.voice_channels)
        hidden_cfg = await db.get_hidden_voice_config(guild.id)

        if hidden_cat:
            ow = hidden_cat.overwrites_for(guild.default_role)
            print(f"✅ Category: {hidden_cat.name} (ID: {hidden_cat.id})")
            print(f"   @everyone View Category: {ow.view_channel or ow.read_messages}")
        else:
            print("⚠️ Hidden Rooms category missing!")

        if hidden_entry:
            print(f"✅ Entry Voice Channel: {hidden_entry.name} (ID: {hidden_entry.id})")
        else:
            print("⚠️ Entry Voice Channel missing!")

        print(f"   Database Config: Category ID={hidden_cfg.category_id}, Generator ID={hidden_cfg.generator_channel_id}, Staff Visibility={hidden_cfg.staff_can_view_hidden_rooms}")

        # 5. Security & Roles Permissions Audit
        print("\n--- SECURITY & ROLES AUDIT ---")
        founder_roles = []
        admin_roles = []
        mention_roles = []

        for r in guild.roles:
            if r.is_default():
                continue
            if r.permissions.administrator:
                admin_roles.append(r.name)
            if r.permissions.mention_everyone:
                mention_roles.append(r.name)

        print(f"🛡️ Roles with Administrator: {admin_roles}")
        print(f"📢 Roles with @everyone Mention Permission: {mention_roles}")

        sec_cfg = await db.get_security_config(guild.id)
        print(f"🔒 Anti-Nuke: {'🟢 Active' if sec_cfg.anti_nuke else '⚪ Disabled'}")
        print(f"🔒 Anti-Raid: {'🟢 Active' if sec_cfg.anti_raid else '⚪ Disabled'}")
        print(f"🔒 Anti-Spam: {'🟢 Active' if sec_cfg.anti_spam else '⚪ Disabled'}")
        print(f"🚨 Panic Mode: {'🔴 Active' if sec_cfg.panic_mode else '🟢 Normal'}")

        # 6. Database Health
        print("\n--- DATABASE & EXTENSIONS AUDIT ---")
        pl_list = await db.list_music_playlists(guild.id, guild.owner_id)
        events_list = await db.list_events(guild.id)
        lfg_list = await db.list_active_gaming_lfg(guild.id)
        showcases = await db.list_creator_showcases(guild.id)
        music_an = await db.get_music_analytics(guild.id)

        print(f"🎼 Music Playlists Stored: {len(pl_list)}")
        print(f"📅 Community Events: {len(events_list)}")
        print(f"🎮 Active Gaming LFG: {len(lfg_list)}")
        print(f"🎨 Creator Showcases: {len(showcases)}")
        print(f"🎧 Music Analytics: {music_an.tracks_played} plays, {music_an.total_playtime_seconds}s total")

        await db.close()
        await client.close()

    await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(run_review())
