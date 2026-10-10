import asyncio, os, sys, aiohttp
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

async def main():
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=headers) as r:
            roles = await r.json()
            roles.sort(key=lambda x: x["position"], reverse=True)
            for role in roles:
                managed = " [Managed/Bot]" if role.get("managed") else ""
                print(f"Pos {role['position']:02d}: {role['name']} (ID: {role['id']}){managed}")

if __name__ == "__main__":
    asyncio.run(main())
