import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"
bot_id = "1554732669072445532"

CH_AUDIT_LOGS = "1545502850057244762"
CH_RULES = "1545502710101704714"
CH_TICKETS = "1545514505520545886"

async def cleanup():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        # 1. Clean audit logs role spam
        print("Cleaning audit logs role spam...")
        async with s.get(f"https://discord.com/api/v10/channels/{CH_AUDIT_LOGS}/messages?limit=100", headers=headers) as mr:
            if mr.status == 200:
                msgs = await mr.json()
                for m in msgs:
                    if m.get("author", {}).get("id") == bot_id:
                        embeds = m.get("embeds", [])
                        title = embeds[0].get("title", "") if embeds else ""
                        if "Role Created" in title or "Role Deleted" in title:
                            async with s.delete(f"https://discord.com/api/v10/channels/{CH_AUDIT_LOGS}/messages/{m['id']}", headers=headers) as dr:
                                pass
                            print(f"  Deleted audit log message: {m['id']}")
                            await asyncio.sleep(0.5)

        # 2. Clean duplicate rules embeds (leave the latest 1)
        print("\nChecking duplicate rules embeds...")
        async with s.get(f"https://discord.com/api/v10/channels/{CH_RULES}/messages?limit=20", headers=headers) as mr:
            if mr.status == 200:
                msgs = await mr.json()
                rules_msgs = [m for m in msgs if m.get("author", {}).get("id") == bot_id]
                # Leave rules_msgs[0] (latest), delete the rest
                for old in rules_msgs[1:]:
                    async with s.delete(f"https://discord.com/api/v10/channels/{CH_RULES}/messages/{old['id']}", headers=headers) as dr:
                        pass
                    print(f"  Deleted duplicate rules message: {old['id']}")
                    await asyncio.sleep(0.5)

        # 3. Clean duplicate ticket embeds (leave the latest 1)
        print("\nChecking duplicate ticket embeds...")
        async with s.get(f"https://discord.com/api/v10/channels/{CH_TICKETS}/messages?limit=20", headers=headers) as mr:
            if mr.status == 200:
                msgs = await mr.json()
                ticket_msgs = [m for m in msgs if m.get("author", {}).get("id") == bot_id]
                # Leave ticket_msgs[0] (latest), delete the rest
                for old in ticket_msgs[1:]:
                    async with s.delete(f"https://discord.com/api/v10/channels/{CH_TICKETS}/messages/{old['id']}", headers=headers) as dr:
                        pass
                    print(f"  Deleted duplicate ticket message: {old['id']}")
                    await asyncio.sleep(0.5)

    print("\nCleanup completed!")

if __name__ == "__main__":
    asyncio.run(cleanup())
