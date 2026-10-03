import asyncio
import os
import aiohttp
import json
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("DISCORD_TOKEN")
guild_id = "1457382179981099090"
CH_ROLES = "1545502722739150898" # #🏷️｜roles

async def setup():
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "X-Audit-Log-Reason": "Autonomous Role System & Self-Assignable Panels Deployment"
    }

    async with aiohttp.ClientSession() as s:
        # 1. Fetch current roles
        async with s.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers) as r:
            roles = await r.json()

        roles_by_name = {r["name"].strip(): r for r in roles}
        roles_by_id = {r["id"]: r for r in roles}

        print(f"Total roles fetched: {len(roles)}")

        # 2. Check & Create Automated Security Roles
        security_roles_to_create = [
            {"name": "🟡 │ Under Observation", "color": 0xF1C40F, "hoist": False, "mentionable": False},
            {"name": "⏳ │ Muted / Timeout", "color": 0x95A5A6, "hoist": False, "mentionable": False},
            {"name": "🛑 │ Raid Protection", "color": 0xE74C3C, "hoist": False, "mentionable": False},
        ]

        created_sec_roles = {}
        for sr in security_roles_to_create:
            existing = None
            for r in roles:
                if sr["name"].lower() in r["name"].lower() or r["name"].lower() in sr["name"].lower():
                    existing = r
                    break
            if existing:
                safe_name = sr['name'].encode('ascii', errors='replace').decode('ascii')
                print(f"  [+] Security role '{safe_name}' already exists (ID: {existing['id']})")
                created_sec_roles[sr["name"]] = existing["id"]
            else:
                async with s.post(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers, json=sr) as cr:
                    if cr.status in (200, 201):
                        new_r = await cr.json()
                        created_sec_roles[sr["name"]] = new_r["id"]
                        safe_name = sr['name'].encode('ascii', errors='replace').decode('ascii')
                        print(f"  [+] Created security role '{safe_name}' (ID: {new_r['id']})")
                    else:
                        print(f"  [-] Failed to create security role: status {cr.status}")


        # 3. Move TRIAL MOD up below MODERATOR if possible
        trial_mod_role = None
        for r in roles:
            if "trial mod" in r["name"].lower():
                trial_mod_role = r
                break

        if trial_mod_role:
            safe_tm = trial_mod_role['name'].encode('ascii', errors='replace').decode('ascii')
            print(f"Found Trial Mod role: {safe_tm} at pos {trial_mod_role['position']}")

            # Bot top role is 39. So pos 38 is valid.
            reorder_payload = [{"id": trial_mod_role["id"], "position": 38}]
            async with s.patch(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers, json=reorder_payload) as pr:
                print(f"  Move Trial Mod status: {pr.status}")

        # 4. Find Game, Notification, and Color role IDs
        def find_role(keyword):
            for r in roles:
                if keyword.lower() in r["name"].lower():
                    return r
            return None

        # Game roles
        game_roles = [
            ("Valorant / CS2", "🎯", find_role("Valorant")),
            ("BGMI / PUBG", "⚡", find_role("BGMI")),
            ("Free Fire", "🔥", find_role("Free Fire")),
            ("GTA RP", "🏎️", find_role("GTA")),
            ("Rocket League", "🚀", find_role("Rocket")),
            ("Party Games", "🎲", find_role("Party Games")),
        ]

        # Notification roles
        notif_roles = [
            ("Announcements", "📢", find_role("Announcements")),
            ("Giveaways", "🎁", find_role("Giveaways")),
            ("Tournaments", "🏆", find_role("Tournaments")),
            ("Movie Nights", "🍿", find_role("Movie Nights")),
            ("Live DJ & Radio", "📻", find_role("Live DJ")),
        ]

        # Color roles
        color_roles = [
            ("Sakura Pink", "🌸", find_role("Sakura Pink")),
            ("Neon Purple", "💜", find_role("Neon Purple")),
            ("Cyber Cyan", "🩵", find_role("Cyber Cyan")),
            ("Royal Gold", "👑", find_role("Royal Gold")),
        ]

        # 5. Clear old messages in #roles if any exist
        async with s.get(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages?limit=20", headers=headers) as mr:
            if mr.status == 200:
                old_msgs = await mr.json()
                for om in old_msgs:
                    async with s.delete(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages/{om['id']}", headers=headers) as dr:
                        pass
                    await asyncio.sleep(0.5)

        # 6. Deploy Interactive Game Roles Panel
        game_options = []
        for name, emoji, r in game_roles:
            if r:
                game_options.append({
                    "label": name,
                    "value": str(r["id"]),
                    "description": f"Get pinged for {name} squad games",
                    "emoji": {"name": emoji}
                })

        game_embed = {
            "title": "🎮 RAI FAM — GAME SELECTOR ROLES",
            "description": (
                "Select your favorite games from the dropdown menu below!\n\n"
                "• Receive notifications when members are looking for a party or squad.\n"
                "• Access dedicated voice lounges in the **⚡ SQUAD ARENA**.\n"
                "• Selecting an option will **toggle** the role (add/remove)."
            ),
            "color": 0x3498DB,
            "footer": {"text": "RAI FAM Self-Assignable Roles • Click to toggle"}
        }

        game_payload = {
            "embeds": [game_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 3, # String Select
                            "custom_id": "rai_role_select_games",
                            "placeholder": "🎮 Choose your game roles...",
                            "min_values": 0,
                            "max_values": len(game_options),
                            "options": game_options
                        }
                    ]
                }
            ]
        }
        async with s.post(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages", headers=headers, json=game_payload) as r:
            print(f"Deploy Game Roles Panel: status {r.status}")

        await asyncio.sleep(1.0)

        # 7. Deploy Interactive Notification Roles Panel
        notif_options = []
        for name, emoji, r in notif_roles:
            if r:
                notif_options.append({
                    "label": name,
                    "value": str(r["id"]),
                    "description": f"Notifications for {name}",
                    "emoji": {"name": emoji}
                })

        notif_embed = {
            "title": "🔔 RAI FAM — COMMUNITY NOTIFICATIONS",
            "description": (
                "Choose what alerts and events you want to be notified about!\n\n"
                "• Stay updated on server giveaways, tournaments, and events.\n"
                "• You can change or remove your notification preferences anytime."
            ),
            "color": 0xF1C40F,
            "footer": {"text": "RAI FAM Self-Assignable Roles • Click to toggle"}
        }

        notif_payload = {
            "embeds": [notif_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 3,
                            "custom_id": "rai_role_select_notifs",
                            "placeholder": "🔔 Choose your notification alerts...",
                            "min_values": 0,
                            "max_values": len(notif_options),
                            "options": notif_options
                        }
                    ]
                }
            ]
        }
        async with s.post(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages", headers=headers, json=notif_payload) as r:
            print(f"Deploy Notification Roles Panel: status {r.status}")

        await asyncio.sleep(1.0)

        # 8. Deploy Interactive Palette Color Roles Panel
        color_options = []
        for name, emoji, r in color_roles:
            if r:
                color_options.append({
                    "label": name,
                    "value": str(r["id"]),
                    "description": f"Sets your username color to {name}",
                    "emoji": {"name": emoji}
                })

        color_embed = {
            "title": "🎨 RAI FAM — NAME COLOR PALETTE",
            "description": (
                "Customize the color of your username in chat!\n\n"
                "• Select your favorite aesthetic color from the list below.\n"
                "• Picking a new color will automatically replace your previous color."
            ),
            "color": 0xE91E63,
            "footer": {"text": "RAI FAM Aesthetic Colors • Choose 1 color"}
        }

        color_payload = {
            "embeds": [color_embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 3,
                            "custom_id": "rai_role_select_colors",
                            "placeholder": "🎨 Select your username color...",
                            "min_values": 1,
                            "max_values": 1,
                            "options": color_options
                        }
                    ]
                }
            ]
        }
        async with s.post(f"https://discord.com/api/v10/channels/{CH_ROLES}/messages", headers=headers, json=color_payload) as r:
            print(f"Deploy Color Roles Panel: status {r.status}")

    print("\nRole panels successfully deployed to #roles channel!")

if __name__ == "__main__":
    asyncio.run(setup())
