import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

# Remaining cosmetic & special roles to polish
ADDITIONAL_UPDATES = {
    1557477503746969782: "👑 ┆ VIP LOUNGE",
    1557477500886581310: "🌸 ┆ ROSE GOLD",
    1557477498466336830: "💠 ┆ CYBER CYAN",
    1557477496524509224: "💜 ┆ NEON VIOLET",
    1555632650473971734: "🤖 ┆ BOT ADMIN",
    1558161370615390319: "🟢 ┆ UNBYPASSABLE",
    1558161368090284133: "🔴 ┆ SECURED",
    1558161373245214861: "🛡️ ┆ RAI SENTINEL",
    1554876448467329185: "🤖 ┆ OFFICIAL BOT",
    1557476518886641694: "🤖 ┆ RAI SENTINEL",
}

async def main():
    print("🚀 Polishing remaining server roles...")
    async with aiohttp.ClientSession() as session:
        for role_id, new_name in ADDITIONAL_UPDATES.items():
            payload = {"name": new_name}
            async with session.patch(
                f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles/{role_id}",
                headers=HEADERS,
                json=payload
            ) as r:
                if r.status == 200:
                    print(f"✅ Polished: {new_name}")
                else:
                    err = await r.text()
                    print(f"⚠️ Skipped {role_id} ({new_name}): Status {r.status} - {err}")
            await asyncio.sleep(0.8)

if __name__ == "__main__":
    asyncio.run(main())
