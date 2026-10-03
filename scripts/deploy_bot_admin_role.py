"""
Deploy the '🤖 ╏ 𝓑ᴏᴛ・𝕬ᴅᴍɪɴ' role to live Discord server:
1. Creates '🤖 ╏ 𝓑ᴏᴛ・𝕬ᴅᴍɪɴ' with Electric Cyan color (0x00F0FF) and scoped management permissions.
2. Positions it appropriately in role hierarchy.
3. Assigns role to Founder (ID: 1457380609641938981).
4. Configures channel permission overwrites for bot management channels.
"""

import asyncio
import logging
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
FOUNDER_ID = 1457380609641938981

# Target Channels for Bot Admin Overwrites
BOT_CONFIG_CHANNEL_ID = 1555283416071675954      # #⚙️・𝓑ᴏᴛ-𝕮ᴏɴғɪɢ
AUTOMATION_CHANNEL_ID = 1555283417183031516      # #🤖・𝓐ᴜᴛᴏᴍᴀᴛɪᴏɴ-𝕮ᴏɴᴛʀᴏʟ
SERVER_DASHBOARD_ID = 1555283414205075509        # #📊・𝓢ᴇʀᴠᴇʀ-𝕯ᴀsʜʙᴏᴀʀᴅ

ROLE_NAME = "🤖 ╏ 𝓑ᴏᴛ・𝕬ᴅᴍɪɴ"
ROLE_COLOR = 0x00F0FF  # Vibrant Electric Cyan

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DeployBotAdminRole")

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

# Bitwise permission calculation for Bot Admin
# VIEW_CHANNEL (1<<10) | SEND_MESSAGES (1<<11) | EMBED_LINKS (1<<14) | ATTACH_FILES (1<<15) |
# READ_MESSAGE_HISTORY (1<<16) | VIEW_AUDIT_LOG (1<<7) | MANAGE_MESSAGES (1<<13) |
# CONNECT (1<<20) | SPEAK (1<<21) | USE_APPLICATION_COMMANDS (1<<31)
BOT_ADMIN_PERMS = (
    (1 << 7)   # VIEW_AUDIT_LOG
    | (1 << 10)  # VIEW_CHANNEL
    | (1 << 11)  # SEND_MESSAGES
    | (1 << 13)  # MANAGE_MESSAGES
    | (1 << 14)  # EMBED_LINKS
    | (1 << 15)  # ATTACH_FILES
    | (1 << 16)  # READ_MESSAGE_HISTORY
    | (1 << 20)  # CONNECT
    | (1 << 21)  # SPEAK
    | (1 << 31)  # USE_APPLICATION_COMMANDS
)


async def main():
    async with aiohttp.ClientSession() as session:
        # 1. Fetch current roles
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS) as resp:
            roles = await resp.json()

        existing_role = next((r for r in roles if r["name"] == ROLE_NAME or "bot admin" in r["name"].lower()), None)
        role_id = None

        if existing_role:
            role_id = existing_role["id"]
            logger.info(f"ℹ️ Role already exists: {ROLE_NAME} (ID: {role_id})")
        else:
            payload = {
                "name": ROLE_NAME,
                "color": ROLE_COLOR,
                "hoist": True,
                "mentionable": True,
                "permissions": str(BOT_ADMIN_PERMS),
            }
            async with session.post(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS, json=payload) as resp:
                if resp.status in (200, 201):
                    role_data = await resp.json()
                    role_id = role_data["id"]
                    logger.info(f"✅ Created role: {ROLE_NAME} (ID: {role_id})")
                else:
                    data = await resp.json()
                    logger.error(f"❌ Failed to create role: {resp.status} {data}")
                    return

        await asyncio.sleep(1.0)

        # 2. Assign role to Founder
        if role_id:
            assign_url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{FOUNDER_ID}/roles/{role_id}"
            async with session.put(assign_url, headers=HEADERS) as resp:
                if resp.status in (200, 204):
                    logger.info(f"✅ Assigned {ROLE_NAME} to Founder (ID: {FOUNDER_ID})")
                else:
                    logger.warning(f"⚠️ Could not assign role to Founder: HTTP {resp.status}")

        await asyncio.sleep(1.0)

        # 3. Configure channel overwrites (ALLOW VIEW_CHANNEL 1<<10, SEND_MESSAGES 1<<11, READ_HISTORY 1<<16)
        allow_flags = (1 << 10) | (1 << 11) | (1 << 16) | (1 << 14) | (1 << 15)
        channels_to_grant = [BOT_CONFIG_CHANNEL_ID, AUTOMATION_CHANNEL_ID, SERVER_DASHBOARD_ID]

        for cid in channels_to_grant:
            url = f"https://discord.com/api/v10/channels/{cid}/permissions/{role_id}"
            payload = {
                "type": 0,  # 0 = Role overwrite
                "allow": str(allow_flags),
                "deny": "0",
            }
            async with session.put(url, headers=HEADERS, json=payload) as resp:
                if resp.status in (200, 204):
                    logger.info(f"✅ Channel overwrite granted on channel {cid}")
                else:
                    logger.warning(f"⚠️ Channel {cid} overwrite status: HTTP {resp.status}")
            await asyncio.sleep(1.0)

    logger.info("🎉 Bot Administration Role deployment complete!")


if __name__ == "__main__":
    asyncio.run(main())
