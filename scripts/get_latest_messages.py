import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"

async def get_latest():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers) as r:
            channels = await r.json()
        all_msgs = []
        for ch in channels:
            if ch.get("type") in (0, 5):
                cid = ch["id"]
                cname = ch.get("name", "unknown")
                async with s.get(f"https://discord.com/api/v10/channels/{cid}/messages?limit=5", headers=headers) as mr:
                    if mr.status == 200:
                        msgs = await mr.json()
                        for m in msgs:
                            ts = m.get("timestamp", "")
                            author = m.get("author", {}).get("username", "unknown")
                            content = m.get("content", "")
                            embed_titles = [e.get("title", "") for e in m.get("embeds", [])]
                            all_msgs.append((ts, cname, author, content, embed_titles))

        all_msgs.sort(key=lambda x: x[0], reverse=True)
        print("=== LATEST 15 MESSAGES ACROSS SERVER ===")
        for ts, ch, author, content, embeds in all_msgs[:15]:
            safe_ch = ch.encode("ascii", errors="replace").decode("ascii")
            safe_content = content[:60].encode("ascii", errors="replace").decode("ascii")
            safe_embeds = [str(e).encode("ascii", errors="replace").decode("ascii") for e in embeds]
            print(f"{ts} | #{safe_ch} | {author}: {safe_content} {safe_embeds}")

if __name__ == "__main__":
    asyncio.run(get_latest())
