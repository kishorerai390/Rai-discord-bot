"""
Deploy Fusion B (Royal Luxury: Cursive Initial + Gothic Accent + Clean Small Caps)
across Server ID 1457382179981099090 with skip-if-already-named and network retry handling.
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
logger = logging.getLogger("FusionBDeploy")

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

CATEGORIES_MAP = {
    1545803464712650844: "╭━━━ 𝓘ɴғᴏʀᴍᴀᴛɪᴏɴ ━━━╮",
    1545803478490812578: "╭━━━ 𝓒ᴏᴍᴍᴜɴɪᴛʏ ━━━╮",
    1555255661124784159: "╭━━━ 𝓜ᴜsɪᴄ・𝕷ᴏᴜɴɢᴇ ━━━╮",
    1554891379174416474: "╭━━━ 𝓟ʀɪᴠᴀᴛᴇ・𝕍ᴏɪᴄᴇ ━━━╮",
    1554905776030613535: "╭━━━ 𝓥ɪᴘ・𝕾ᴜɪᴛᴇs ━━━╮",
    1554905799292231728: "╭━━━ 𝓒ʜɪʟʟ & 𝕳ᴀᴠᴇɴ ━━━╮",
    1554905821467648051: "╭━━━ 𝓖ᴀᴍɪɴɢ・𝕬ʀᴇɴᴀ ━━━╮",
    1554905866673856714: "╭━━━ 𝓒ɪɴᴇᴍᴀ & 𝕾ᴛʀᴇᴀᴍs ━━━╮",
    1554905886261121107: "╭━━━ 𝓔xᴇᴄᴜᴛɪᴠᴇ・𝕳𝕼 ━━━╮",
    1554891443343204494: "╭━━━ 𝓢ᴇᴄᴜʀɪᴛʏ・𝕬ʟᴇʀᴛs ━━━╮",
    1555255294190424136: "╭━━━ 𝓜ᴀɴᴀɢᴇᴍᴇɴᴛ・𝕷ᴏɢs ━━━╮",
    1554891470325031013: "╭━━━ 𝓕ᴏᴄᴜs & 𝕬ғᴋ ━━━╮",
    1555428388280209422: "╭━━━ 📋 ╏ 𝓡ᴀɪ・𝕽ᴇᴘᴏʀᴛs ━━━╮",
    1555283372488658954: "╭━━━ 🛡️ ╏ 𝓡ᴀɪ・𝕾ᴇᴄᴜʀɪᴛʏ ━━━╮",
    1555283377249063083: "╭━━━ ⚙️ ╏ 𝓡ᴀɪ・𝕬ᴅᴍɪɴ ━━━╮",
}

CHANNELS_MAP = {
    # Information & Welcome
    1545502700840427702: "✨・𝓥ᴇʀɪғʏ-𝕳ᴇʀᴇ",
    1545502705643167876: "🌸・𝓦ᴇʟᴄᴏᴍᴇ",
    1545502710101704714: "📜・𝓡ᴜʟᴇs-ᴀɴᴅ-𝕲ᴜɪᴅᴇ",
    1545502718792175646: "📢・𝓐ɴɴᴏᴜɴᴄᴇᴍᴇɴᴛs",
    1545502722739150898: "📌・𝓢ᴇʀᴠᴇʀ-𝕽ᴏʟᴇs",
    
    # Community
    1545502730699808768: "💬・𝓖ᴇɴᴇʀᴀʟ-𝕮ʜᴀᴛ",
    1551184138932068373: "📸・𝓜ᴇᴅɪᴀ-ᴀɴᴅ-𝕮ʟɪᴘs",
    1549416359723532480: "🤖・𝓑ᴏᴛ-𝕮ᴏᴍᴍᴀɴᴅs",

    # Music Text & Controls
    1555255695933186228: "🎶・𝓜ᴜsɪᴄ-𝕮ᴏɴᴛʀᴏʟ",
    1555255691705323651: "🎧・𝓝ᴏᴡ-𝕻ʟᴀʏɪɴɢ",
    1555283393242206301: "📜・𝓠ᴜᴇᴜᴇ",
    1555283394274005092: "🔊・𝓓ᴊ-𝕮ᴏɴᴛʀᴏʟ",
    1555283395330842714: "💿・𝓟ʟᴀʏʟɪsᴛs",
    1555283396660428830: "🎼・𝓜ᴜsɪᴄ-𝕽ᴇǫᴜᴇsᴛs",
    
    # Dynamic Voice
    1555459478155960421: "🛠️・𝓡ᴏᴏᴍ-𝕮ᴏɴᴛʀᴏʟ",
    1554891383117193307: "➕・𝓒ʀᴇᴀᴛᴇ・𝕽ᴏᴏᴍ",
    1554891386577485927: "🔐・𝓟ʀɪᴠᴀᴛᴇ・𝕽ᴏᴏᴍ",
    
    # Music Voice
    1555255317170749472: "🔊・𝓜ᴜsɪᴄ・𝕽ᴏᴏᴍ Ⅰ",
    1555255319494402141: "🎧・𝓛ᴏ-𝓕ɪ・𝕷ᴏᴜɴɢᴇ",
    1555255321948327936: "🎵・𝓜ᴜsɪᴄ・𝕽ᴏᴏᴍ Ⅱ",
    1555255323705475228: "🎶・𝓛ɪsᴛᴇɴɪɴɢ・𝕽ᴏᴏᴍ",
    1555255325706424412: "⚡・𝟐𝟒/𝟕・𝓡ᴀᴅɪᴏ",

    # VIP Suites Voice
    1554905780397015172: "💎・𝓢ᴏʟᴏ・𝕾ᴀɴᴄᴛᴜᴍ",
    1554905785233051812: "🥂・𝓓ᴜᴏ・𝕷ᴏᴜɴɢᴇ Ⅰ",
    1554905791994003616: "🥂・𝓓ᴜᴏ・𝕷ᴏᴜɴɢᴇ Ⅱ",
    1554905795555237931: "✨・𝓣ʀɪᴏ・𝕮ʜᴀᴍʙᴇʀ",
    1554909104760422430: "👑・𝓢ǫᴜᴀᴅ・𝕾ᴜɪᴛᴇ",

    # Chill & Haven Voice
    1554905803666751590: "🎵・𝟐𝟒/𝟕 𝓡ᴀᴅɪᴏ & 𝕭ᴇᴀᴛs",
    1554905807240302652: "☕・𝓝ɪɢʜᴛ・𝓞ᴡʟ・𝕮ᴀғᴇ",
    1554905810574774286: "🌊・𝓥ɪʙᴇ・𝕾ᴛᴜᴅɪᴏ",
    1554905813737545770: "🎤・𝓞ᴘᴇɴ・𝕸ɪᴄ & 𝕾ᴛᴀɢᴇ",

    # Gaming Voice
    1554905825544241302: "🔥・𝓑ᴀᴛᴛʟᴇ・𝕾ǫᴜᴀᴅ",
    1554905836768469032: "🎯・𝓡ᴀɴᴋᴇᴅ・𝕮ᴏᴍᴍs Ⅰ",
    1554905842300485642: "🎯・𝓡ᴀɴᴋᴇᴅ・𝕮ᴏᴍᴍs Ⅱ",
    1554905829033902151: "🕹️・𝓒ᴀsᴜᴀʟ・𝕬ʀᴄᴀᴅᴇ",

    # Cinema & Streams
    1554905870817689600: "🍿・𝓒ɪɴᴇᴍᴀ・𝕳ᴀʟʟ",
    1554905874437513248: "📺・𝓢ᴛʀᴇᴀᴍ・𝕾ʜᴏᴡᴄᴀsᴇ",

    # Executive Voice
    1554905907509596180: "🏛️・𝓔xᴇᴄᴜᴛɪᴠᴇ・𝕭ᴏᴀʀᴅʀᴏᴏᴍ",
    1554905899414454446: "🔮・𝓒ʀᴇᴀᴛᴏʀ・𝕾ᴛᴜᴅɪᴏ",
    1554905903508095066: "🛡️・𝓢ᴛᴀғғ・𝕺ᴘᴇʀᴀᴛɪᴏɴs 𝕍ℂ",

    # Focus & AFK
    1554891485818921042: "💤・𝓐ғᴋ・𝓢ʟᴇᴇᴘ",
    
    # Reports Channels
    1555428392181047366: "🚨・𝓼ᴇᴄᴜʀɪᴛʏ-ʀᴇᴘᴏʀᴛ",
    1555428399919538297: "🛡️・𝓶ᴏᴅ-ʀᴇᴘᴏʀᴛ",
    1555428406726893619: "🎵・𝓶ᴜsɪᴄ-ʀᴇᴘᴏʀᴛ",
    1555428413102235701: "🔐・𝓻ᴏᴏᴍ-ʀᴇᴘᴏʀᴛ",
    1555428420383416400: "🤖・𝓫ᴏᴛ-ʀᴇᴘᴏʀᴛ",
    1555428426607894570: "⚙️・𝓼ʏsᴛᴇᴍ-ʀᴇᴘᴏʀᴛ",
}

ROLES_MAP = {
    1545494610489643038: "👑 ╏ 𝓕ᴏᴜɴᴅᴇʀ",
    1545506927788687470: "⚡ ╏ 𝓗ᴇᴀᴅ 𝕬ᴅᴍɪɴ",
    1545494600347680918: "🛡️ ╏ 𝓜ᴏᴅᴇʀᴀᴛᴏʀ",
    1545494591883579434: "🚀 ╏ 𝓢ᴇʀᴠᴇʀ 𝕭ᴏᴏsᴛᴇʀ",
    1545494578512134176: "🤖 ╏ 𝓑ᴏᴛs",
    1545834928221069522: "🎵 ╏ 𝓓ᴊ 𝕸ᴀsᴛᴇʀ",
    1545494584203673740: "💖 ╏ 𝓡ᴀɪ 𝕱ᴀᴍ",
    1549504522953695269: "✨ ╏ 𝓥ᴇʀɪғɪᴇᴅ 𝕸ᴇᴍʙᴇʀ",
    1551184081067450451: "💎 ╏ 𝓥ɪᴘ 𝕸ᴇᴍʙᴇʀ",
    1555255357746446416: "👑 ╏ 𝓞ᴡɴᴇʀ",
    1555255359952916542: "⚡ ╏ 𝓐ᴅᴍɪɴɪsᴛʀᴀᴛᴏʀ",
    1555255361835901012: "🛡️ ╏ 𝓜ᴏᴅᴇʀᴀᴛᴏʀ",
    1555255364746879046: "🔧 ╏ 𝓢ᴛᴀғғ",
}

NEW_GUILD_NAME = "✦ 𝓣ʜᴇ 𝕽ᴀɪᴠᴏʀᴀ ╏ 𝓡ᴏʏᴀʟ 𝕾ᴇᴄᴜʀɪᴛʏ & 𝓒ᴏᴍᴍᴜɴɪᴛʏ ✦"

async def patch_with_retry(session: aiohttp.ClientSession, url: str, payload: dict, item_desc: str):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            async with session.patch(url, headers=HEADERS, json=payload) as r:
                if r.status == 200:
                    logger.info(f"✅ Renamed {item_desc} -> {payload.get('name')}")
                    return True
                elif r.status == 429:
                    data = await r.json()
                    wait_time = float(data.get("retry_after", 3.0))
                    logger.warning(f"⏳ Rate limited on {item_desc}. Backing off {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time + 1.0)
                else:
                    resp_text = await r.text()
                    logger.error(f"❌ Failed to rename {item_desc} [HTTP {r.status}]: {resp_text}")
                    return False
        except (aiohttp.ClientError, asyncio.TimeoutError) as net_err:
            logger.warning(f"⚠️ Network glitch ({net_err}) on {item_desc}. Retrying in 2s...")
            await asyncio.sleep(2.0)
    return False

async def main():
    async with aiohttp.ClientSession() as session:
        # Fetch current channels to skip already-renamed ones
        logger.info("Fetching current channels...")
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            curr_channels = {int(c["id"]): c["name"] for c in await r.json()}

        # 1. Update Guild Name if needed
        logger.info("Checking Server Name...")
        url_guild = f"https://discord.com/api/v10/guilds/{GUILD_ID}"
        async with session.get(url_guild, headers=HEADERS) as r:
            guild_data = await r.json()
            if guild_data.get("name") != NEW_GUILD_NAME:
                await patch_with_retry(session, url_guild, {"name": NEW_GUILD_NAME}, "Server Name")
            else:
                logger.info("Server Name already matches! Skipping.")

        # 2. Update Categories
        logger.info("Checking Categories...")
        for cid, name in CATEGORIES_MAP.items():
            if curr_channels.get(cid) == name:
                logger.info(f"Category {cid} already named {name}. Skipping.")
                continue
            url = f"https://discord.com/api/v10/channels/{cid}"
            await patch_with_retry(session, url, {"name": name}, f"Category {cid}")
            await asyncio.sleep(1.2)

        # 3. Update Channels (Text & Voice)
        logger.info("Checking Channels...")
        for cid, name in CHANNELS_MAP.items():
            if curr_channels.get(cid) == name:
                logger.info(f"Channel {cid} already named {name}. Skipping.")
                continue
            url = f"https://discord.com/api/v10/channels/{cid}"
            await patch_with_retry(session, url, {"name": name}, f"Channel {cid}")
            await asyncio.sleep(1.2)

        # 4. Update Server Roles
        logger.info("Fetching Roles...")
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS) as r:
            curr_roles = {int(role["id"]): role["name"] for role in await r.json()}

        logger.info("Checking Roles...")
        for rid, name in ROLES_MAP.items():
            if curr_roles.get(rid) == name:
                logger.info(f"Role {rid} already named {name}. Skipping.")
                continue
            url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles/{rid}"
            await patch_with_retry(session, url, {"name": name}, f"Role {rid}")
            await asyncio.sleep(1.2)

    logger.info("🎉 All Fusion B font styles successfully deployed across server 1457382179981099090!")

if __name__ == "__main__":
    asyncio.run(main())
