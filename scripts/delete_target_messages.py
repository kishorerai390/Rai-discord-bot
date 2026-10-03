import asyncio
import os
import aiohttp
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")

async def delete_messages():
    if not os.path.exists("data/all_target_user_messages.json"):
        print("Error: data/all_target_user_messages.json not found.")
        return

    with open("data/all_target_user_messages.json", "r", encoding="utf-8") as f:
        messages = json.load(f)

    print(f"Total messages queued for deletion: {len(messages)}")

    # Group by channel
    channel_msgs = {}
    for m in messages:
        ch_id = m["channel_id"]
        ch_name = m.get("channel_name", ch_id)
        if ch_id not in channel_msgs:
            channel_msgs[ch_id] = {"name": ch_name, "msgs": []}
        channel_msgs[ch_id]["msgs"].append(m)

    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "X-Audit-Log-Reason": "Cleanup messages from Deleted User requested by Administrator"
    }

    now = datetime.now(timezone.utc)
    fourteen_days_ago = now - timedelta(days=14)

    total_deleted = 0
    total_failed = 0

    async with aiohttp.ClientSession() as session:
        for ch_id, ch_data in channel_msgs.items():
            name = ch_data["name"]
            msgs = ch_data["msgs"]
            safe_name = name.encode("ascii", errors="replace").decode("ascii")
            print(f"\nProcessing channel #{safe_name} ({len(msgs)} messages)...")

            recent_ids = []
            old_ids = []

            for m in msgs:
                # Parse timestamp to determine bulk delete eligibility
                ts_str = m.get("timestamp")
                is_recent = False
                if ts_str:
                    try:
                        # e.g. 2026-09-17T18:08:55.051000+00:00
                        ts = datetime.fromisoformat(ts_str)
                        if ts > fourteen_days_ago:
                            is_recent = True
                    except Exception:
                        pass
                
                if is_recent:
                    recent_ids.append(m["message_id"])
                else:
                    old_ids.append(m["message_id"])

            # Bulk delete recent messages in batches of 100
            for i in range(0, len(recent_ids), 100):
                batch = recent_ids[i:i + 100]
                if len(batch) == 1:
                    # Single message cannot be bulk deleted
                    old_ids.append(batch[0])
                    continue

                url = f"https://discord.com/api/v10/channels/{ch_id}/messages/bulk-delete"
                while True:
                    async with session.post(url, headers=headers, json={"messages": batch}) as resp:
                        if resp.status == 204:
                            total_deleted += len(batch)
                            print(f"  [Bulk Deleted] {len(batch)} messages")
                            break
                        elif resp.status == 429:
                            data = await resp.json()
                            retry_after = data.get("retry_after", 1.0)
                            print(f"  Rate limited, waiting {retry_after}s...")
                            await asyncio.sleep(retry_after)
                        else:
                            print(f"  Bulk delete returned {resp.status}, falling back to individual delete...")
                            old_ids.extend(batch)
                            break
                await asyncio.sleep(1.0)

            # Individual delete for older messages
            for mid in old_ids:
                url = f"https://discord.com/api/v10/channels/{ch_id}/messages/{mid}"
                retries = 3
                while retries > 0:
                    async with session.delete(url, headers=headers) as resp:
                        if resp.status in (204, 404): # 204 No Content or 404 already deleted
                            total_deleted += 1
                            break
                        elif resp.status == 429:
                            data = await resp.json()
                            retry_after = data.get("retry_after", 1.5)
                            print(f"  Rate limited on message {mid}, waiting {retry_after}s...")
                            await asyncio.sleep(retry_after)
                        else:
                            retries -= 1
                            if retries == 0:
                                total_failed += 1
                                print(f"  Failed to delete message {mid}: status {resp.status}")
                            await asyncio.sleep(1.0)
                await asyncio.sleep(0.5)

    print("\n=============================================")
    print(f"DELETION SUMMARY:")
    print(f"Total Successfully Deleted: {total_deleted}")
    print(f"Total Failed: {total_failed}")
    print("=============================================")

if __name__ == "__main__":
    asyncio.run(delete_messages())
