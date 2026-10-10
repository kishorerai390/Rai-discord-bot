import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

# Categories
CREATOR_CAT_ID = "1558483212873769090"
MUSIC_CAT_ID = "1555255661124784159"
GAMING_CAT_ID = "1554905821467648051"
CHILL_CAT_ID = "1554905799292231728"
REPORTS_CAT_ID = "1555428388280209422"

REPURPOSE_MAP = [
    # 1. Rename Category 1558483212873769090 to ✦ ᴄʀᴇᴀᴛᴏʀ sᴛᴜᴅɪᴏ ✦
    ("1558483212873769090", {"name": "✦ ᴄʀᴇᴀᴛᴏʀ sᴛᴜᴅɪᴏ ✦"}, "Category: ✦ ᴄʀᴇᴀᴛᴏʀ sᴛᴜᴅɪᴏ ✦"),

    # 2. Move movie-lounge to Chill & Haven
    ("1557477521661108315", {"name": "🎬・movie-lounge", "parent_id": CHILL_CAT_ID}, "#🎬・movie-lounge"),

    # 3. Creator Studio Channels
    ("1558482941817004143", {"name": "✂️・editing-chat", "parent_id": CREATOR_CAT_ID, "topic": "Video editing discussion, software help, and creative workflows."}, "#✂️・editing-chat"),
    ("1558482965175078994", {"name": "⟁・gaming-montages", "parent_id": CREATOR_CAT_ID, "topic": "Community gaming montages, edits, and frag reels showcase."}, "#⟁・gaming-montages"),
    ("1554905874437513248", {"name": "🎞️・edit-showcase", "parent_id": CREATOR_CAT_ID, "topic": "Showcase your finished edits and get feedback from editors."}, "#🎞️・edit-showcase"),
    ("1558483065578197002", {"name": "✧・pfp-and-banners", "parent_id": CREATOR_CAT_ID, "topic": "Profile pictures, Discord banners, headers, and gfx creations."}, "#✧・pfp-and-banners"),
    ("1558483087283720352", {"name": "𖦹・editing-tips", "parent_id": CREATOR_CAT_ID, "topic": "Presets, plugins, SFX packs, tutorials, and editing tips."}, "#𖦹・editing-tips"),
    ("1558483098553819228", {"name": "♧・collab-requests", "parent_id": CREATOR_CAT_ID, "topic": "Editor matchmaking, collaboration requests, and multi-creator projects."}, "#♧・collab-requests"),
    ("1558483178862288987", {"name": "🏅・edit-of-the-week", "parent_id": CREATOR_CAT_ID, "topic": "Weekly featured editor showcase and winning community edits."}, "#🏅・edit-of-the-week"),

    # 4. Music Lounge
    ("1557479356899524678", {"name": "𓂃・music-chat", "parent_id": MUSIC_CAT_ID, "topic": "Community music discussions, song recommendations, and favorite tracks."}, "#𓂃・music-chat"),

    # 5. Gaming Arena
    ("1557479367297339432", {"name": "⚔️・battle-squad", "parent_id": GAMING_CAT_ID, "topic": "Squad finder, team recruitment, and looking for group."}, "#⚔️・battle-squad"),
    ("1555428406726893619", {"name": "🎯・ranked-comms", "parent_id": GAMING_CAT_ID, "topic": "Ranked games comms, competitive strats, and tier climbing."}, "#🎯・ranked-comms"),
    ("1555428413102235701", {"name": "♛・casual-arcade", "parent_id": GAMING_CAT_ID, "topic": "Casual games, party games, and fun discussions."}, "#♛・casual-arcade"),
    ("1555428420383416400", {"name": "𖣘・gameplay-highlights", "parent_id": GAMING_CAT_ID, "topic": "Post your best clutch plays, aces, and gaming highlights."}, "#𖣘・gameplay-highlights"),
    ("1555428426607894570", {"name": "乂・free-fire", "parent_id": GAMING_CAT_ID, "topic": "Dedicated Free Fire discussion, custom rooms, and squad pairing."}, "#乂・free-fire"),

    # 6. Chill & Haven
    ("1555641081578782840", {"name": "☾・late-night-talks", "parent_id": CHILL_CAT_ID, "topic": "Cozy late night conversations, midnight thoughts, and chill vibes."}, "#☾・late-night-talks"),

    # 7. Private Reporting: Ensure Staff Lounge is under Private Reporting
    ("1545502845208629328", {"name": "🔒・staff-lounge", "parent_id": REPORTS_CAT_ID}, "#🔒・staff-lounge"),
    ("1557479979053228072", {"name": "📋・staff-ledger", "parent_id": REPORTS_CAT_ID}, "#📋・staff-ledger"),
]

async def main():
    async with aiohttp.ClientSession() as s:
        for ch_id, payload, label in REPURPOSE_MAP:
            print(f"Adapting {label} ({ch_id})...")
            for attempt in range(3):
                async with s.patch(f"https://discord.com/api/v10/channels/{ch_id}", headers=HEADERS, json=payload) as r:
                    if r.status in (200, 204):
                        print(f"  Successfully adapted: {label}")
                        break
                    elif r.status == 429:
                        data = await r.json()
                        w = data.get("retry_after", 1.5)
                        print(f"  Rate limited, waiting {w}s...")
                        await asyncio.sleep(w + 0.2)
                    else:
                        print(f"  Failed ({r.status}):", await r.text())
                        break
            await asyncio.sleep(0.5)

    print("\nChannel repurposing completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
