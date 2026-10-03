import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"

async def scan():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        # Get all channels
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers) as r:
            channels = await r.json()

        text_channels = [c for c in channels if c.get("type") in (0, 5)] # GUILD_TEXT, GUILD_ANNOUNCEMENT
        print(f"Found {len(text_channels)} text channels to scan.")

        found_messages = []

        for ch in text_channels:
            ch_id = ch["id"]
            ch_name = ch.get("name", "unknown")
            try:
                # Fetch recent messages (up to 100 per channel)
                async with s.get(f"https://discord.com/api/v10/channels/{ch_id}/messages?limit=100", headers=headers) as mr:
                    if mr.status != 200:
                        continue
                    msgs = await mr.json()
                    if not isinstance(msgs, list):
                        continue
                    for m in msgs:
                        author = m.get("author", {})
                        author_name = author.get("username", "")
                        global_name = author.get("global_name", "")
                        # Discord deleted users usually have username 'Deleted User' or discriminator '0000'
                        if "deleted user" in author_name.lower() or (global_name and "deleted user" in global_name.lower()):
                            found_messages.append({
                                "channel_id": ch_id,
                                "channel_name": ch_name,
                                "message_id": m["id"],
                                "author_id": author.get("id"),
                                "author_name": author_name,
                                "timestamp": m.get("timestamp"),
                                "content": m.get("content", "")[:100],
                            })
            except Exception as e:
                print(f"Error scanning #{ch_name}: {e}")

        import json
        with open("data/deleted_user_messages.json", "w", encoding="utf-8") as f:
            json.dump(found_messages, f, indent=2)

        print(f"\n--- SCAN RESULTS ---")
        print(f"Found {len(found_messages)} messages from Deleted User.")
        
        # Breakdown by channel
        channel_counts = {}
        for m in found_messages:
            c = m["channel_name"]
            channel_counts[c] = channel_counts.get(c, 0) + 1
        
        for c, count in channel_counts.items():
            safe_c = c.encode('ascii', errors='replace').decode('ascii')
            print(f"  #{safe_c}: {count} messages")


if __name__ == "__main__":
    asyncio.run(scan())
