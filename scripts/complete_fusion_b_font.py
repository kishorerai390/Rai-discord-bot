"""
Complete Fusion B Font & Cleanup Automation.
1. Deletes the empty category '🔐 | RAI PRIVATE CONTROL' (ID: 1555455277027950643).
2. Updates Server Stats category and member count voice channels to Fusion B.
3. Updates Security Alerts, Management & Logs, Rai Security, Rai Admin, and Rai Reports to matching Fusion B typography.
"""

import asyncio
import logging
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FusionBComplete")

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

EMPTY_CATEGORY_ID = 1555455277027950643

CATEGORIES_UPDATE = {
    1546059369085534229: "╭━━━ 📊 ╏ 𝓢ᴇʀᴠᴇʀ・𝕾ᴛᴀᴛs ━━━╮",
}

CHANNELS_UPDATE = {
    # Server Stats Voice Channels
    1546099701496029194: "👥・𝓐ʟʟ・𝓜ᴇᴍʙᴇʀs: 39",
    1546099703630798848: "👤・𝓜ᴇᴍʙᴇʀs: 26",
    1546059375574130769: "🤖・𝓑ᴏᴛs: 13",

    # Security Alerts
    1554891455003107338: "🚨・𝓐ʟᴇʀᴛs",
    1555255314532794521: "📡・𝓘ɴᴄɪᴅᴇɴᴛ-𝕷ᴏɢ",
    1554891451140149352: "📋・𝓐ᴜᴅɪᴛ-𝕿ʀᴀɪʟ",
    1555255312414674964: "🔒・𝓢ᴇᴄᴜʀɪᴛʏ-𝕮ᴇɴᴛᴇʀ",

    # Management & Logs
    1554920840699580426: "🛠️・𝓐ᴅᴍɪɴ-𝕺ᴘᴇʀᴀᴛɪᴏɴs",
    1554920847439962194: "📊・𝓢ʏsᴛᴇᴍ-𝕳ᴇᴀʟᴛʜ",
    1545502845208629328: "🎫・𝓢ᴛᴀғғ-𝕷ᴏᴜɴɢᴇ",
    1554919245824000042: "🎙️・𝓥ᴏɪᴄᴇ-𝕷ᴏɢ",

    # Rai Reports
    1555428392181047366: "🚨・𝓢ᴇᴄᴜʀɪᴛʏ-𝓡ᴇᴘᴏʀᴛ",
    1555428399919538297: "🛡️・𝓜ᴏᴅ-𝓡ᴇᴘᴏʀᴛ",
    1555428406726893619: "🎵・𝓜ᴜsɪᴄ-𝓡ᴇᴘᴏʀᴛ",
    1555428413102235701: "🔐・𝓡ᴏᴏᴍ-𝓡ᴇᴘᴏʀᴛ",
    1555428420383416400: "🤖・𝓑ᴏᴛ-𝓡ᴇᴘᴏʀᴛ",
    1555428426607894570: "⚙️・𝓢ʏsᴛᴇᴍ-𝓡ᴇᴘᴏʀᴛ",

    # Rai Security
    1555283378612478072: "🚨・𝓢ᴇᴄᴜʀɪᴛʏ-𝕬ʟᴇʀᴛs",
    1555283380961026139: "🧱・𝓐ɴᴛɪ-𝕹ᴜᴋᴇ",
    1555283386656886825: "🔒・𝓛ᴏᴄᴋᴅᴏᴡɴ-𝕮ᴏɴᴛʀᴏʟ",
    1555283387340562574: "🛡️・𝓢ᴇᴄᴜʀɪᴛʏ-𝕷ᴏɢ",
    1555283390943469685: "🔍・𝓐ᴜᴅɪᴛ-𝕸ᴏɴɪᴛᴏʀ",

    # Rai Admin
    1555283409465778218: "👑・𝓐ᴅᴍɪɴ-𝕮ᴏɴᴛʀᴏʟ",
    1555283414205075509: "📊・𝓢ᴇʀᴠᴇʀ-𝕯ᴀsʜʙᴏᴀʀᴅ",
    1555283416071675954: "⚙️・𝓑ᴏᴛ-𝕮ᴏɴғɪɢ",
    1555283417183031516: "🤖・𝓐ᴜᴛᴏᴍᴀᴛɪᴏɴ-𝕮ᴏɴᴛʀᴏʟ",
    1555283418126876856: "💾・𝓑ᴀᴄᴋᴜᴘ-𝕮ᴏɴᴛʀᴏʟ",
    1555283419355676787: "❤️・𝓢ʏsᴛᴇᴍ-𝕳ᴇᴀʟᴛʜ",
}


async def main():
    async with aiohttp.ClientSession() as session:
        # 1. Delete empty category
        url = f"https://discord.com/api/v10/channels/{EMPTY_CATEGORY_ID}"
        async with session.delete(url, headers=HEADERS) as resp:
            if resp.status in (200, 204):
                logger.info("✅ Successfully deleted empty category: 🔐 | RAI PRIVATE CONTROL")
            elif resp.status == 404:
                logger.info("ℹ️ Empty category already deleted or does not exist.")
            else:
                data = await resp.json()
                logger.warning(f"⚠️ Could not delete empty category: {resp.status} {data}")

        await asyncio.sleep(1.0)

        # 2. Update Categories
        for cat_id, name in CATEGORIES_UPDATE.items():
            url = f"https://discord.com/api/v10/channels/{cat_id}"
            async with session.patch(url, headers=HEADERS, json={"name": name}) as resp:
                if resp.status == 200:
                    logger.info(f"✅ Category {cat_id} updated -> {ascii(name)}")
                else:
                    data = await resp.json()
                    logger.warning(f"⚠️ Category {cat_id} failed: {resp.status} {data}")
            await asyncio.sleep(1.2)

        # 3. Update Channels
        for ch_id, name in CHANNELS_UPDATE.items():
            url = f"https://discord.com/api/v10/channels/{ch_id}"
            async with session.patch(url, headers=HEADERS, json={"name": name}) as resp:
                if resp.status == 200:
                    logger.info(f"✅ Channel {ch_id} updated -> {ascii(name)}")
                elif resp.status == 429:
                    retry_after = (await resp.json()).get("retry_after", 5.0)
                    logger.warning(f"⏳ Rate limited on {ch_id}, sleeping {retry_after}s...")
                    await asyncio.sleep(retry_after + 0.5)
                    async with session.patch(url, headers=HEADERS, json={"name": name}) as r2:
                        logger.info(f"✅ Channel {ch_id} updated on retry -> {ascii(name)}")
                else:
                    data = await resp.json()
                    logger.warning(f"⚠️ Channel {ch_id} failed: {resp.status} {data}")
            await asyncio.sleep(1.2)

    logger.info("🎉 All requested font styling updates and cleanup complete!")


if __name__ == "__main__":
    asyncio.run(main())
