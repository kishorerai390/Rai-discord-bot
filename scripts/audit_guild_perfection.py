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

async def main():
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as s:
        # Guild info
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}", headers=headers) as r:
            guild = await r.json()
            print(f"=== GUILD: {guild.get('name')} ===")
            print(f"Description: {guild.get('description')}")
            print(f"Features: {guild.get('features')}")
            print(f"Vanity: {guild.get('vanity_url_code')}")
            print(f"Premium Tier: {guild.get('premium_tier')}, Boosts: {guild.get('premium_subscription_count')}")

        # Channels
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=headers) as r:
            channels = await r.json()
            categories = {c["id"]: c["name"] for c in channels if c["type"] == 4}
            print(f"\n=== CHANNELS ({len(channels)}) ===")
            for ch in sorted(channels, key=lambda x: (x.get("parent_id") or "0", x.get("position", 0))):
                cat_name = categories.get(ch.get("parent_id"), "ROOT")
                type_str = "VOICE" if ch["type"] == 2 else "TEXT" if ch["type"] == 0 else "CAT" if ch["type"] == 4 else f"T{ch['type']}"
                print(f"[{cat_name}] [{type_str}] {ch['name']} (ID: {ch['id']})")

        # Emojis & Stickers
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/emojis", headers=headers) as r:
            emojis = await r.json()
            print(f"\n=== CUSTOM EMOJIS: {len(emojis)} ===")

        # AutoMod Rules
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/auto-moderation/rules", headers=headers) as r:
            if r.status == 200:
                rules = await r.json()
                print(f"\n=== AUTOMOD RULES: {len(rules)} ===")
                for rule in rules:
                    print(f"- {rule.get('name')} (enabled: {rule.get('enabled')})")
            else:
                print(f"\n=== AUTOMOD RULES: Status {r.status} ===")

if __name__ == "__main__":
    asyncio.run(main())
