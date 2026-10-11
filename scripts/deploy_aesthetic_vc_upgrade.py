"""
Aesthetic Voice Channel System Deployment for Rai Server.
Implements the 8-Category Aesthetic VC System:
- Category 1: 🍒・Personal Area ! (with ➕・Create Your VC + Solo, Duo, Trio, Squad, Space)
- Category 2: 🍒・Fun Voice Channels ! (Vibin, Just Us, No Stress, Dream Land)
- Category 3: 🍒・Gaming Zone ! (Game On, Clutch Time, Tryhard, Lobby 404, One More Match)
- Category 4: 🍒・Editing Zone ! (Edit Lab, Magic Cuts, Pixel World, Render Room, Creative Mind)
- Category 5: 🍒・Private Zone ! (No Entry, Dark Room, Only Us, Secret Spot, Our Little World)
- Category 6: 🍒・Music Zone ! (Lost Tunes, Vibe Check, Midnight Beats)
- Category 7: 🍒・Theater ! (Movie <1, Movie <2)
- Category 8: 🍒・AFK Zone ! (Sleeping !, Gone For A While !)

Safeguards:
- Reuses and renames existing categories/channels where available (Zero unnecessary deletions).
- Rate-limited with 1.2s delay between API calls.
- Updates database TempVoiceConfig seamlessly.
"""

from __future__ import annotations

import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, "F:/Bot")

import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

# Role IDs for permission overwrites
EVERYONE_ID = str(GUILD_ID)
VIP_LOUNGE_ROLE_ID = "1557477503746969782"
VIP_MEMBER_ROLE_ID = "1551184081067450451"
SERVER_BOOSTER_ROLE_ID = "1545494591883579434"
HEAD_ADMIN_ROLE_ID = "1545506927788687470"
MODERATOR_ROLE_ID = "1545494600347680918"


async def api_patch(session: aiohttp.ClientSession, url: str, data: dict, desc: str = ""):
    async with session.patch(url, headers=HEADERS, json=data) as resp:
        if resp.status in (200, 204):
            print(f"  [SUCCESS] {desc}")
            return await resp.json()
        else:
            err = await resp.text()
            print(f"  [ERROR] {desc} -> HTTP {resp.status}: {err}")
            return None


async def api_post(session: aiohttp.ClientSession, url: str, data: dict, desc: str = ""):
    async with session.post(url, headers=HEADERS, json=data) as resp:
        if resp.status in (200, 201):
            res = await resp.json()
            print(f"  [CREATED] {desc} (ID: {res.get('id')})")
            return res
        else:
            err = await resp.text()
            print(f"  [ERROR] {desc} -> HTTP {resp.status}: {err}")
            return None


async def main():
    print("=" * 65)
    print("   🍒 DEPLOYING AESTHETIC ROLE-BASED VOICE CHANNEL SYSTEM")
    print("=" * 65)

    async with aiohttp.ClientSession() as session:
        # Fetch current channels
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            channels = await r.json()

        ch_map = {c["id"]: c for c in channels}
        name_to_ch = {c["name"]: c for c in channels}

        # -----------------------------------------------------------------
        # CATEGORY 1: 🍒・Personal Area !
        # -----------------------------------------------------------------
        print("\n[CAT 1] 🍒・Personal Area !")
        cat1_id = "1554891379174416474"  # Reusing former Private Voice cat
        await api_patch(session, f"https://discord.com/api/v10/channels/{cat1_id}", {"name": "🍒・Personal Area !"}, "Rename Cat 1")
        await asyncio.sleep(1.2)

        # Trigger channel
        trigger_id = "1557461916144767046"
        await api_patch(session, f"https://discord.com/api/v10/channels/{trigger_id}", {"name": "➕・Create Your VC", "parent_id": cat1_id}, "Rename Trigger VC")
        await asyncio.sleep(1.2)

        # Static presets
        presets = [
            ("🦢・Solo <3", 1),
            ("🐇・Us Two <3", 2),
            ("🐉・Three Souls <3", 3),
            ("🧸・Little Gang <3", 5),
            ("🪐・Our Space <3", 0),
        ]
        for name, limit in presets:
            existing = next((c for c in channels if c["name"] == name and c.get("parent_id") == cat1_id), None)
            if existing:
                print(f"  [EXISTS] {name}")
            else:
                payload = {"name": name, "type": 2, "parent_id": cat1_id, "user_limit": limit}
                await api_post(session, f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", payload, f"Create {name}")
                await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # CATEGORY 2: 🍒・Fun Voice Channels !
        # -----------------------------------------------------------------
        print("\n[CAT 2] 🍒・Fun Voice Channels !")
        cat2_id = "1554905799292231728"  # Reusing former Chill & Haven cat
        await api_patch(session, f"https://discord.com/api/v10/channels/{cat2_id}", {"name": "🍒・Fun Voice Channels !"}, "Rename Cat 2")
        await asyncio.sleep(1.2)

        fun_renames = [
            ("1554905807240302652", "❄️・Vibin' ~!"),
            ("1554905810574774286", "🌷・Just Us <3"),
            ("1554905813737545770", "🦋・No Stress <1"),
            ("1557479364856123444", "☁️・Dream Land <2"),
        ]
        for cid, new_name in fun_renames:
            await api_patch(session, f"https://discord.com/api/v10/channels/{cid}", {"name": new_name, "parent_id": cat2_id}, f"Rename {new_name}")
            await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # CATEGORY 3: 🍒・Gaming Zone !
        # -----------------------------------------------------------------
        print("\n[CAT 3] 🍒・Gaming Zone !")
        cat3_id = "1554905821467648051"  # Reusing former Gaming Arena cat
        await api_patch(session, f"https://discord.com/api/v10/channels/{cat3_id}", {"name": "🍒・Gaming Zone !"}, "Rename Cat 3")
        await asyncio.sleep(1.2)

        gaming_renames = [
            ("1554905825544241302", "🎮・Game On ~?"),
            ("1554905836768469032", "🔥・Clutch Time !"),
            ("1554905829033902151", "🎯・Tryhard <3"),
            ("1558483012830888060", "🕹️・Lobby 404"),
        ]
        for cid, new_name in gaming_renames:
            await api_patch(session, f"https://discord.com/api/v10/channels/{cid}", {"name": new_name, "parent_id": cat3_id}, f"Rename {new_name}")
            await asyncio.sleep(1.2)

        # Create 5th gaming VC if not existing
        if not next((c for c in channels if c["name"] == "⚡・One More Match !"), None):
            await api_post(session, f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", {"name": "⚡・One More Match !", "type": 2, "parent_id": cat3_id}, "Create ⚡・One More Match !")
            await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # CATEGORY 4: 🍒・Editing Zone !
        # -----------------------------------------------------------------
        print("\n[CAT 4] 🍒・Editing Zone !")
        cat4_id = "1554905886261121107"  # Reusing former Executive HQ cat
        await api_patch(session, f"https://discord.com/api/v10/channels/{cat4_id}", {"name": "🍒・Editing Zone !"}, "Rename Cat 4")
        await asyncio.sleep(1.2)

        # Rename existing creator VCs into Editing Zone
        await api_patch(session, "https://discord.com/api/v10/channels/1554905899414454446", {"name": "💎・Edit Lab ~!", "parent_id": cat4_id}, "Rename 💎・Edit Lab ~!")
        await asyncio.sleep(1.2)
        await api_patch(session, "https://discord.com/api/v10/channels/1554905874437513248", {"name": "🪄・Magic Cuts <3", "parent_id": cat4_id}, "Rename 🪄・Magic Cuts <3")
        await asyncio.sleep(1.2)

        editing_vcs = [
            "🎨・Pixel World",
            "🎬・Render Room",
            "🖥️・Creative Mind <3",
        ]
        for name in editing_vcs:
            if not next((c for c in channels if c["name"] == name and c.get("parent_id") == cat4_id), None):
                await api_post(session, f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", {"name": name, "type": 2, "parent_id": cat4_id}, f"Create {name}")
                await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # CATEGORY 5: 🍒・Private Zone ! (With Locked Permission Overwrites)
        # -----------------------------------------------------------------
        print("\n[CAT 5] 🍒・Private Zone !")
        cat5_id = "1554905776030613535"  # Reusing former VIP Suites cat
        # Category overwrites: @everyone CONNECT denied (0x100000 = 1048576)
        cat5_overwrites = [
            {"id": EVERYONE_ID, "type": 0, "allow": "0", "deny": "1048576"},
            {"id": VIP_LOUNGE_ROLE_ID, "type": 0, "allow": "1048576", "deny": "0"},
            {"id": VIP_MEMBER_ROLE_ID, "type": 0, "allow": "1048576", "deny": "0"},
            {"id": SERVER_BOOSTER_ROLE_ID, "type": 0, "allow": "1048576", "deny": "0"},
            {"id": HEAD_ADMIN_ROLE_ID, "type": 0, "allow": "1048576", "deny": "0"},
            {"id": MODERATOR_ROLE_ID, "type": 0, "allow": "1048576", "deny": "0"},
        ]
        await api_patch(session, f"https://discord.com/api/v10/channels/{cat5_id}", {"name": "🍒・Private Zone !", "permission_overwrites": cat5_overwrites}, "Rename Cat 5 & Lock")
        await asyncio.sleep(1.2)

        await api_patch(session, "https://discord.com/api/v10/channels/1557481242054758482", {"name": "🖤・No Entry <3", "parent_id": cat5_id}, "Rename 🖤・No Entry <3")
        await asyncio.sleep(1.2)

        private_vcs = [
            "🌑・Dark Room ~?",
            "🪽・Only Us <3",
            "🗝️・Secret Spot",
            "💌・Our Little World <3",
        ]
        for name in private_vcs:
            if not next((c for c in channels if c["name"] == name and c.get("parent_id") == cat5_id), None):
                await api_post(session, f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", {"name": name, "type": 2, "parent_id": cat5_id}, f"Create {name}")
                await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # CATEGORY 6: 🍒・Music Zone !
        # -----------------------------------------------------------------
        print("\n[CAT 6] 🍒・Music Zone !")
        cat6_id = "1555255661124784159"  # Reusing former Music Lounge cat
        await api_patch(session, f"https://discord.com/api/v10/channels/{cat6_id}", {"name": "🍒・Music Zone !"}, "Rename Cat 6")
        await asyncio.sleep(1.2)

        await api_patch(session, "https://discord.com/api/v10/channels/1555255325706424412", {"name": "🎧・Lost Tunes <3", "parent_id": cat6_id}, "Rename 🎧・Lost Tunes <3")
        await asyncio.sleep(1.2)

        # Unarchive and rename second radio
        await api_patch(session, "https://discord.com/api/v10/channels/1558483052550692884", {"name": "🎶・Vibe Check !", "parent_id": cat6_id}, "Restore & Rename 🎶・Vibe Check !")
        await asyncio.sleep(1.2)

        if not next((c for c in channels if c["name"] == "🌌・Midnight Beats"), None):
            await api_post(session, f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", {"name": "🌌・Midnight Beats", "type": 2, "parent_id": cat6_id}, "Create 🌌・Midnight Beats")
            await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # CATEGORY 7: 🍒・Theater !
        # -----------------------------------------------------------------
        print("\n[CAT 7] 🍒・Theater !")
        existing_theater = next((c for c in channels if c["name"] == "🍒・Theater !" and c["type"] == 4), None)
        if not existing_theater:
            cat7 = await api_post(session, f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", {"name": "🍒・Theater !", "type": 4}, "Create Cat 7 🍒・Theater !")
            cat7_id = cat7["id"] if cat7 else None
            await asyncio.sleep(1.2)
        else:
            cat7_id = existing_theater["id"]

        if cat7_id:
            theater_vcs = ["🍂・Movie <1", "🍂・Movie <2"]
            for name in theater_vcs:
                if not next((c for c in channels if c["name"] == name and c.get("parent_id") == cat7_id), None):
                    await api_post(session, f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", {"name": name, "type": 2, "parent_id": cat7_id}, f"Create {name}")
                    await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # CATEGORY 8: 🍒・AFK Zone !
        # -----------------------------------------------------------------
        print("\n[CAT 8] 🍒・AFK Zone !")
        cat8_id = "1554891470325031013"  # Reusing former Pods & AFK cat
        await api_patch(session, f"https://discord.com/api/v10/channels/{cat8_id}", {"name": "🍒・AFK Zone !"}, "Rename Cat 8")
        await asyncio.sleep(1.2)

        await api_patch(session, "https://discord.com/api/v10/channels/1554891485818921042", {"name": "💤・Sleeping !", "parent_id": cat8_id}, "Rename 💤・Sleeping !")
        await asyncio.sleep(1.2)

        if not next((c for c in channels if c["name"] == "🌙・Gone For A While !"), None):
            await api_post(session, f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", {"name": "🌙・Gone For A While !", "type": 2, "parent_id": cat8_id}, "Create 🌙・Gone For A While !")
            await asyncio.sleep(1.2)

        # -----------------------------------------------------------------
        # UPDATE DATABASE CONFIG FOR DYNAMIC VC
        # -----------------------------------------------------------------
        print("\n[DB] Updating TempVoiceConfig in SQLite...")
        from database.database import Database
        db = Database()
        await db.connect()
        cfg = await db.get_temp_voice_config(GUILD_ID)
        cfg.hub_channel_id = int(trigger_id)
        cfg.category_id = int(cat1_id)
        cfg.enabled = True
        await db.save_temp_voice_config(cfg)
        await db.close()
        print("  [SUCCESS] TempVoiceConfig updated: hub=1557461916144767046, category=1554891379174416474")

    print("\n" + "=" * 65)
    print("   🍒 AESTHETIC VC UPGRADE COMPLETED SUCCESSFULLY")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
