import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
HEADERS = {"Authorization": f"Bot {TOKEN}"}

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            channels = await r.json()

    categories = [c for c in channels if c.get("type") == 4]
    categories.sort(key=lambda x: x.get("position", 0))

    cat_map = {c["id"]: c["name"] for c in categories}
    grouped = {}
    for c in channels:
        pid = c.get("parent_id")
        if pid:
            grouped.setdefault(pid, []).append(c)

    lines = []
    lines.append("==================================================")
    lines.append(f"FINAL AUDIT & LAYOUT: RAI FAM ({len(channels)} total)")
    lines.append("==================================================")

    total_public_text = 0

    for cat in categories:
        cid = cat["id"]
        cname = cat["name"]
        children = grouped.get(cid, [])
        children.sort(key=lambda x: (x.get("type") == 2, x.get("position", 0)))
        lines.append(f"\n📁 CATEGORY: {cname} ({len(children)} channels)")
        for ch in children:
            t = "VC" if ch["type"] == 2 else "Text"
            lines.append(f"   [{t:4s}] #{ch['name']} (ID: {ch['id']})")
            if t == "Text" and not any(k in cname.lower() for k in ("sᴛᴀғғ", "admin", "stats", "reports", "private", "detention")):
                total_public_text += 1

    lines.append(f"\nTotal Public Community Text Channels: {total_public_text}")

    with open("data/final_audit_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Report written to data/final_audit_report.txt (Public text: {total_public_text})")

if __name__ == "__main__":
    asyncio.run(main())
