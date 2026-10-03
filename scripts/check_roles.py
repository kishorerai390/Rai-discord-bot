import asyncio
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"
bot_user_id = "1554732669072445532"

async def check_roles():
    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession() as s:
        # 1. Fetch guild roles
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers) as r:
            roles = await r.json()

        # 2. Fetch bot member
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/members/{bot_user_id}", headers=headers) as r:
            bot_member = await r.json()
            bot_role_ids = set(bot_member.get("roles", []))

        # Sort roles descending by position (top to bottom)
        roles.sort(key=lambda x: x.get("position", 0), reverse=True)

        lines = [
            "=" * 65,
            f"DISCORD SERVER ROLES AUDIT: RAI FAM ({guild_id})",
            f"Total Roles: {len(roles)}",
            "=" * 65,
            f"{'Pos':<5} | {'Role Name':<35} | {'Permissions':<15} | {'Assigned to Bot?'}",
            "-" * 65,
        ]

        bot_highest_pos = 0
        bot_highest_name = ""

        for role in roles:
            pos = role.get("position", 0)
            name = role.get("name", "")
            r_id = role.get("id")
            perms = int(role.get("permissions", 0))
            is_admin = bool(perms & 0x8)
            is_bot_assigned = r_id in bot_role_ids

            if is_bot_assigned and pos > bot_highest_pos:
                bot_highest_pos = pos
                bot_highest_name = name

            perm_desc = "ADMINISTRATOR" if is_admin else f"Perms: {perms}"
            bot_tag = "⭐ BOT HAS ROLE" if is_bot_assigned else ""

            lines.append(f"{pos:<5} | {name:<35} | {perm_desc:<15} | {bot_tag}")

        lines.extend([
            "=" * 65,
            f"Bot Highest Role: '{bot_highest_name}' at Position {bot_highest_pos} / {len(roles)}",
            "=" * 65,
        ])

        with open("data/server_roles.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("Roles written to data/server_roles.txt successfully.")

if __name__ == "__main__":
    asyncio.run(check_roles())
