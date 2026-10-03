"""
Clean up unused duplicate roles and restyle active roles with Fusion B typography.
- Prunes 14 empty/duplicate placeholder roles created at position 1.
- Renames populated staff and interest roles with official Fusion B typography.
- Re-orders '🤖 ╏ 𝓑ᴏᴛ・𝕬ᴅᴍɪɴ' above Moderator in the hierarchy.
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
logger = logging.getLogger("RoleRestyler")

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

# 14 unused 0-member duplicate placeholder roles to delete
ROLES_TO_PRUNE = [
    1555255327836995606,  # 𖤐 RΛI • CORE
    1555255334166339757,  # 🤖 RΛI • BOT
    1555255337441955931,  # ⚡ RΛI • SYSTEM
    1555255339903881397,  # 🛡️ Security
    1555255342202626291,  # ⚔️ Guardian
    1555255344559685723,  # 🔐 Security Admin
    1555255345990078572,  # 🚨 Incident Manager
    1555255348166795389,  # 🕵️ Threat Analyst
    1555255350402228344,  # 🎵 Music Manager
    1555255355829657650,  # 🎚️ Audio Controller
    1555255357746446416,  # 👑 ╏ 𝓞ᴡɴᴇʀ
    1555255359952916542,  # ⚡ ╏ 𝓐ᴅᴍɪɴɪsᴛʀᴀᴛᴏʀ
    1555255361835901012,  # 🛡️ ╏ 𝓜ᴏᴅᴇʀᴀᴛᴏʀ
    1555255364746879046,  # 🔧 ╏ 𝓢ᴛᴀғғ
]

# Populated roles to restyle to Fusion B typography
ROLES_TO_RESTYLE = {
    1545494610489643038: "👑 ╏ 𝓕ᴏᴜɴᴅᴇʀ",
    1545506927788687470: "⚡ ╏ 𝓗ᴇᴀᴅ 𝕬ᴅᴍɪɴ",
    1545494600347680918: "🛡️ ╏ 𝓜ᴏᴅᴇʀᴀᴛᴏʀ",
    1551184071101649038: "🛠️ ╏ 𝓣ʀɪᴀʟ 𝕸ᴏᴅ",
    1551184094313062470: "🎯 ╏ 𝓥ᴀʟᴏʀᴀɴᴛ / 𝕮𝕾𝟐",
    1551184098834251786: "⚡ ╏ 𝓑𝓖𝓜𝓘 / 𝕻𝖀𝕭𝕲",
    1551184102957523048: "🔥 ╏ 𝓕ʀᴇᴇ 𝕱ɪʀᴇ",
    1550199913093144649: "📢 ╏ 𝓐ɴɴᴏᴜɴᴄᴇᴍᴇɴᴛs",
    1550199917262143560: "🎁 ╏ 𝓖ɪᴠᴇᴀᴡᴀʏs",
    1550199921007792188: "🏆 ╏ 𝓣ᴏᴜʀɴᴀᴍᴇɴᴛs",
}

BOT_ADMIN_ROLE_ID = 1555632650473971734


async def main():
    async with aiohttp.ClientSession() as session:
        # Step 1: Prune empty placeholder roles
        logger.info(f"--- Step 1: Pruning {len(ROLES_TO_PRUNE)} empty placeholder roles ---")
        for rid in ROLES_TO_PRUNE:
            url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles/{rid}"
            async with session.delete(url, headers=HEADERS) as resp:
                if resp.status in (200, 204):
                    logger.info(f"✅ Deleted unused role ID: {rid}")
                elif resp.status == 404:
                    logger.info(f"ℹ️ Role {rid} already removed.")
                else:
                    data = await resp.json()
                    logger.warning(f"⚠️ Could not delete role {rid}: HTTP {resp.status} {data}")
            await asyncio.sleep(1.0)

        # Step 2: Restyle populated roles to Fusion B font
        logger.info("--- Step 2: Restyling active roles to Fusion B font ---")
        for rid, new_name in ROLES_TO_RESTYLE.items():
            url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles/{rid}"
            payload = {"name": new_name}
            async with session.patch(url, headers=HEADERS, json=payload) as resp:
                if resp.status == 200:
                    logger.info(f"✅ Restyled role {rid} -> {ascii(new_name)}")
                elif resp.status == 429:
                    retry_after = (await resp.json()).get("retry_after", 5.0)
                    logger.warning(f"⏳ Rate limit on role {rid}, sleeping {retry_after}s...")
                    await asyncio.sleep(retry_after + 0.5)
                    async with session.patch(url, headers=HEADERS, json=payload) as r2:
                        logger.info(f"✅ Restyled role {rid} on retry -> {ascii(new_name)}")
                else:
                    data = await resp.json()
                    logger.warning(f"⚠️ Could not restyle role {rid}: HTTP {resp.status} {data}")
            await asyncio.sleep(1.2)

        # Step 3: Position '🤖 ╏ 𝓑ᴏᴛ・𝕬ᴅᴍɪɴ' above Moderator
        # Fetch current roles to determine positions
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS) as resp:
            roles = await resp.json()

        mod_role = next((r for r in roles if r["id"] == 1545494600347680918), None)
        bot_admin = next((r for r in roles if r["id"] == BOT_ADMIN_ROLE_ID), None)

        if mod_role and bot_admin:
            target_pos = mod_role.get("position", 25) + 1
            logger.info(f"Setting position of Bot Admin role ({BOT_ADMIN_ROLE_ID}) to {target_pos}...")
            pos_payload = [{"id": BOT_ADMIN_ROLE_ID, "position": target_pos}]
            async with session.patch(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS, json=pos_payload) as resp:
                if resp.status == 200:
                    logger.info("✅ Bot Admin position updated successfully.")
                else:
                    logger.warning(f"⚠️ Role re-order status: HTTP {resp.status}")

    logger.info("🎉 All roles cleaned up, restyled, and organized!")


if __name__ == "__main__":
    asyncio.run(main())
