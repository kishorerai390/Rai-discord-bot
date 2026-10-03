import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

# Desired Category Order (Top to Bottom)
CATEGORY_ORDER = [
    1546059369085534229,  # 0: Server Stats
    1545803464712650844,  # 1: Information
    1545803478490812578,  # 2: Community
    1555255661124784159,  # 3: Music Lounge
    1554891379174416474,  # 4: Private Voice (Dynamic VC)
    1554905776030613535,  # 5: VIP Suites
    1554905799292231728,  # 6: Chill & Haven
    1554905821467648051,  # 7: Gaming Arena
    1554905866673856714,  # 8: Cinema & Streams
    1554891470325031013,  # 9: Focus & AFK
    1554905886261121107,  # 10: Executive HQ
    1555283372488658954,  # 11: Rai Security
    1555283377249063083,  # 12: Rai Admin
    1555428388280209422,  # 13: Rai Reports
    1554891443343204494,  # 14: Security Alerts (Legacy Archive)
    1555255294190424136,  # 15: Management Logs (Legacy Archive)
]

# Desired Channel Order within each category (channel_id: relative_position)
CHANNEL_ORDER = {
    # 0: Server Stats
    1546099701496029194: 0,  # All Members
    1546099703630798848: 1,  # Members
    1546059375574130769: 2,  # Bots

    # 1: Information
    1545502700840427702: 0,  # Verify Here
    1545502705643167876: 1,  # Welcome
    1545502710101704714: 2,  # Rules & Guide
    1545502718792175646: 3,  # Announcements
    1545502722739150898: 4,  # Server Roles
    1555641079137706014: 5,  # Support Desk

    # 2: Community
    1545502730699808768: 0,  # General Chat
    1551184138932068373: 1,  # Media & Clips
    1549416359723532480: 2,  # Bot Commands

    # 3: Music Lounge
    1555255695933186228: 0,  # Music Control (Text)
    1555255691705323651: 1,  # Now Playing (Text)
    1555283396660428830: 2,  # Music Requests (Text)
    1555283393242206301: 3,  # Queue (Text)
    1555283394274005092: 4,  # DJ Control (Text)
    1555283395330842714: 5,  # Playlists (Text)
    1555255317170749472: 6,  # Music Room I (Voice)
    1555255321948327936: 7,  # Music Room II (Voice)
    1555255319494402141: 8,  # Lo-Fi Lounge (Voice)
    1555255323705475228: 9,  # Listening Room (Voice)
    1555255325706424412: 10, # 24/7 Radio (Voice)

    # 4: Private Voice (Dynamic VC)
    1555459478155960421: 0,  # Room Control (Text)
    1554891383117193307: 1,  # Create Room (Voice)
    1554891386577485927: 2,  # Private Room (Voice)

    # 5: VIP Suites
    1554905780397015172: 0,  # Solo Sanctum
    1554905785233051812: 1,  # Duo Lounge I
    1554905791994003616: 2,  # Duo Lounge II
    1554905795555237931: 3,  # Trio Chamber
    1554909104760422430: 4,  # Squad Suite

    # 6: Chill & Haven
    1554905803666751590: 0,  # 24/7 Radio & Beats
    1554905807240302652: 1,  # Night Owl Cafe
    1554905810574774286: 2,  # Vibe Studio
    1554905813737545770: 3,  # Open Mic & Stage

    # 7: Gaming Arena
    1554905825544241302: 0,  # Battle Squad
    1554905836768469032: 1,  # Ranked Comms I
    1554905842300485642: 2,  # Ranked Comms II
    1554905829033902151: 3,  # Casual Arcade

    # 8: Cinema & Streams
    1554905870817689600: 0,  # Cinema Hall
    1554905874437513248: 1,  # Stream Showcase

    # 9: Focus & AFK
    1555641081578782840: 0,  # Sleeping Pods (Text)
    1554891485818921042: 1,  # AFK Sleep (Voice)

    # 10: Executive HQ
    1554905907509596180: 0,  # Executive Boardroom
    1554905899414454446: 1,  # Creator Studio
    1554905903508095066: 2,  # Staff Operations VC

    # 11: Rai Security
    1555283378612478072: 0,  # Security Alerts
    1555283380961026139: 1,  # Anti-Nuke
    1555283386656886825: 2,  # Lockdown Control
    1555283387340562574: 3,  # Security Log
    1555283390943469685: 4,  # Audit Monitor

    # 12: Rai Admin
    1555283409465778218: 0,  # Admin Control
    1555283414205075509: 1,  # Server Dashboard
    1555283416071675954: 2,  # Bot Config
    1555283417183031516: 3,  # Automation Control
    1555283418126876856: 4,  # Backup Control
    1555283419355676787: 5,  # System Health

    # 13: Rai Reports
    1555428392181047366: 0,  # Security Report
    1555428399919538297: 1,  # Mod Report
    1555428406726893619: 2,  # Music Report
    1555428413102235701: 3,  # Room Report
    1555428420383416400: 4,  # Bot Report
    1555428426607894570: 5,  # System Report

    # 14: Security Alerts (Legacy)
    1554891455003107338: 0,  # Alerts
    1555255314532794521: 1,  # Incident Log
    1554891451140149352: 2,  # Audit Trail
    1555255312414674964: 3,  # Security Center

    # 15: Management Logs (Legacy)
    1554920840699580426: 0,  # Admin Operations
    1554920847439962194: 1,  # System Health
    1545502845208629328: 2,  # Staff Lounge
    1554919245824000042: 3,  # Voice Log
}

async def main():
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as s:
        # Step 1: Reorder Categories
        print("Reordering categories...")
        cat_payload = []
        for pos, cat_id in enumerate(CATEGORY_ORDER):
            cat_payload.append({"id": str(cat_id), "position": pos})

        async with s.patch(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=cat_payload) as r:
            print(f"Categories reorder status: {r.status}")

        await asyncio.sleep(1.5)

        # Step 2: Reorder Channels within Categories in chunks
        print("Reordering channels within categories...")
        ch_payload = []
        for ch_id, pos in CHANNEL_ORDER.items():
            ch_payload.append({"id": str(ch_id), "position": pos})

        # Send in chunks of 25 to respect Discord payload size
        chunk_size = 25
        for i in range(0, len(ch_payload), chunk_size):
            chunk = ch_payload[i : i + chunk_size]
            async with s.patch(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers, json=chunk) as r:
                print(f"Channels chunk {i//chunk_size + 1} reorder status: {r.status}")
            await asyncio.sleep(1.0)

        print("Orderly server alignment finished.")

if __name__ == "__main__":
    asyncio.run(main())
