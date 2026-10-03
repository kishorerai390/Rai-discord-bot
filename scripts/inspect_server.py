import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"

async def main():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers) as r:
            channels = await r.json()
            lines = [f"Total channels: {len(channels)}"]

            categories = [c for c in channels if c.get("type") == 4]
            categories.sort(key=lambda x: x.get("position", 0))

            for cat in categories:
                cat_name = cat.get("name", "")
                lines.append(f"\n[CATEGORY] {cat_name} (ID: {cat.get('id')}, pos: {cat.get('position')})")
                child_channels = [c for c in channels if c.get("parent_id") == cat.get("id")]
                child_channels.sort(key=lambda x: x.get("position", 0))
                for ch in child_channels:
                    t_str = "Voice" if ch.get("type") == 2 else "Text"
                    lines.append(f"    [{t_str}] #{ch.get('name')} (ID: {ch.get('id')})")

            orphan_channels = [c for c in channels if not c.get("parent_id") and c.get("type") != 4]
            if orphan_channels:
                lines.append("\n[NO CATEGORY] (Root Channels):")
                for ch in orphan_channels:
                    t_str = "Voice" if ch.get("type") == 2 else "Text"
                    lines.append(f"    [{t_str}] #{ch.get('name')} (ID: {ch.get('id')})")

            with open("data/server_channels.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print("Channels successfully written to data/server_channels.txt")

if __name__ == "__main__":
    asyncio.run(main())
