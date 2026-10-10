"""
Royal Role Aesthetic Transformation for RAI FAM.
1. Standardizes role names to clean Small Caps with uniform divider '┆'.
2. Harmonizes role colors to the Royal Purple, Gold & Gaming accent palette.
3. 100% Non-destructive: preserves all role permissions, position hierarchy, and members.
4. Uses 1.0s backoff between updates to respect Discord REST rate limits.
"""

import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import aiohttp
from dotenv import load_dotenv

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

# Role Transformation Mapping: ID -> (New Name, Color Hex)
ROLE_UPDATES = {
    # --- Staff Hierarchy ---
    1545494610489643038: ("👑 ┆ FOUNDER", 0xF1C40F),          # Crown Gold
    1545506927788687470: ("⚡ ┆ HEAD ADMIN", 0x9333EA),        # Electric Violet
    1545494600347680918: ("🛡️ ┆ MODERATOR", 0xA855F7),         # Amethyst
    1551184071101649038: ("🛠️ ┆ TRIAL MOD", 0x7C3AED),         # Royal Purple

    # --- VIP & Community ---
    1545494591883579434: ("🚀 ┆ SERVER BOOSTER", 0xF472B6),    # Radiant Pink
    1551184081067450451: ("💎 ┆ VIP MEMBER", 0x38BDF8),        # Diamond Cyan
    1545494584203673740: ("💖 ┆ RAI FAM", 0xC084FC),           # Soft Orchid
    1549504522953695269: ("✨ ┆ VERIFIED MEMBER", 0xE0E7FF),    # Frost Lilac
    1557491522025300018: ("👤 ┆ MEMBER", 0x94A3B8),            # Slate Silver

    # --- Gaming Roles ---
    1551184094313062470: ("🎯 ┆ VALORANT / CS2", 0xFA4454),    # Tactical Red
    1551184098834251786: ("⚡ ┆ BGMI / PUBG", 0xF59E0B),        # Amber Gold
    1551184102957523048: ("🔥 ┆ FREE FIRE", 0xFB923C),         # Flame Orange

    # --- Interest & Activity ---
    1545834928221069522: ("🎵 ┆ DJ MASTER", 0x8B5CF6),          # Violet
    1550199913093144649: ("📢 ┆ ANNOUNCEMENTS", 0x6366F1),      # Iris
    1550199917262143560: ("🎁 ┆ GIVEAWAYS", 0x10B981),          # Emerald
    1550199921007792188: ("🏆 ┆ TOURNAMENTS", 0xEC4899),        # Rose Pink
    1557477515046555779: ("🎂 ┆ BIRTHDAY STAR", 0xFB7185),      # Coral

    # --- Moderation & Quarantine ---
    1554839510464987156: ("⏳ ┆ MUTED", 0x6B7280),              # Steel Grey
    1558161375996416192: ("⛓️ ┆ QUARANTINED", 0x374151),        # Dark Slate
    1554839328000315462: ("🟡 ┆ UNDER OBSERVATION", 0xEAB308),  # Warning Gold
    1554839513308860560: ("🛑 ┆ RAID CONTAINMENT", 0xEF4444),   # Containment Red

    # --- Bots ---
    1545494578512134176: ("🤖 ┆ BOTS", 0x64748B),              # Cool Slate
}


async def main():
    print(f"🚀 Starting Royal Role Aesthetic Transformation for Guild: {GUILD_ID}...")

    async with aiohttp.ClientSession() as session:
        # Fetch current roles to verify existence
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS) as r:
            roles = await r.json()

        existing_role_ids = {int(role["id"]): role for role in roles}

        updated_count = 0
        total_targets = len(ROLE_UPDATES)

        for role_id, (new_name, new_color) in ROLE_UPDATES.items():
            if role_id not in existing_role_ids:
                print(f"⏩ Role ID {role_id} not found on server. Skipping.")
                continue

            current_role = existing_role_ids[role_id]
            current_name = current_role.get("name", "")
            current_color = current_role.get("color", 0)

            # Skip if already updated
            if current_name == new_name and current_color == new_color:
                print(f"✓ '{new_name}' is already up-to-date.")
                continue

            payload = {
                "name": new_name,
                "color": new_color,
            }

            async with session.patch(
                f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles/{role_id}",
                headers=HEADERS,
                json=payload,
            ) as pr:
                if pr.status in (200, 201):
                    updated_count += 1
                    color_hex = f"#{new_color:06X}"
                    print(f"✅ [{updated_count}/{total_targets}] Updated: '{current_name}' -> '{new_name}' ({color_hex})")
                else:
                    err = await pr.text()
                    print(f"⚠️ Could not update role {role_id} ('{current_name}'): {pr.status} - {err}")

            # Safe 1.0s rate limit backoff
            await asyncio.sleep(1.0)

    print(f"\n🎉 Role Transformation Complete! Successfully polished {updated_count} roles.")
    print("✨ Member sidebar is now completely standardized with royal typography and colors.")


if __name__ == "__main__":
    asyncio.run(main())
