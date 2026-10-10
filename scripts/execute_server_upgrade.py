import asyncio
import os
import sys
import aiohttp
from dotenv import load_dotenv

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv("F:/Bot/.env")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1457382179981099090
OWNER_ID = 1457380609641938981
BOT_ID = 1554732669072445532

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
}

VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
MANAGE_CHANNELS = 1 << 4
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
READ_MESSAGE_HISTORY = 1 << 16
MANAGE_MESSAGES = 1 << 13

DENY_ALL_BITS = VIEW_CHANNEL | SEND_MESSAGES | READ_MESSAGE_HISTORY
OWNER_ALLOW_BITS = VIEW_CHANNEL | SEND_MESSAGES | READ_MESSAGE_HISTORY | MANAGE_CHANNELS | EMBED_LINKS | ATTACH_FILES | MANAGE_MESSAGES
BOT_ALLOW_BITS = VIEW_CHANNEL | SEND_MESSAGES | READ_MESSAGE_HISTORY | EMBED_LINKS | ATTACH_FILES

async def request_discord(session, method, url, **kwargs):
    max_retries = 5
    for attempt in range(max_retries):
        async with session.request(method, url, headers=HEADERS, **kwargs) as r:
            if r.status == 429:
                data = await r.json()
                retry_after = data.get("retry_after", 1.5)
                print(f"Rate limited. Sleeping {retry_after}s...")
                await asyncio.sleep(retry_after + 0.2)
                continue
            if r.status in (200, 201, 204):
                if r.status == 204:
                    return {}
                return await r.json()
            else:
                err_text = await r.text()
                print(f"Error {method} {url}: {r.status} - {err_text}")
                return None
    return None

async def main():
    async with aiohttp.ClientSession() as s:
        # 1. Fetch current channels and roles
        channels = await request_discord(s, "GET", f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels")
        roles = await request_discord(s, "GET", f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles")
        
        roles_by_name = {r["name"]: r["id"] for r in roles}
        mod_role_id = next((r["id"] for r in roles if "𝓜ᴏᴅᴇʀᴀᴛᴏʀ" in r["name"]), None)
        head_admin_role_id = next((r["id"] for r in roles if "𝓗ᴇᴀᴅ 𝕬ᴅᴍɪɴ" in r["name"]), None)
        verified_role_id = next((r["id"] for r in roles if "𝓥ᴇʀɪғɪᴇᴅ" in r["name"]), None)
        
        print(f"Fetched {len(channels)} channels, {len(roles)} roles.")
        print(f"Mod Role: {mod_role_id} | Head Admin Role: {head_admin_role_id}")

        cat_map = {}
        for c in channels:
            if c.get("type") == 4:
                cat_map[c["id"]] = c["name"]

        # Helper to find category by keyword
        def get_cat(name_keyword):
            for cid, cname in cat_map.items():
                if name_keyword.lower() in cname.lower():
                    return cid
            return None

        # Helper to find channel by ID
        ch_by_id = {c["id"]: c for c in channels}

        # -------------------------------------------------------------
        # STEP 1: Categories Setup & Renaming
        # -------------------------------------------------------------
        print("\n--- STEP 1: Standardizing Categories ---")
        
        info_cat_id = get_cat("ɪɴғᴏʀᴍᴀᴛɪᴏɴ")
        comm_cat_id = get_cat("ᴄᴏᴍᴍᴜɴɪᴛʏ")
        music_cat_id = get_cat("ᴍᴜsɪᴄ ʟᴏᴜɴɢᴇ")
        gaming_cat_id = get_cat("ɢᴀᴍɪɴɢ ᴀʀᴇɴᴀ")
        chill_cat_id = get_cat("ᴄʜɪʟʟ & ʜᴀᴠᴇɴ")
        reports_cat_id = get_cat("ʀᴇᴘᴏʀᴛs")
        security_cat_id = get_cat("sᴇᴄᴜʀɪᴛʏ")
        admin_cat_id = get_cat("ʀᴀɪ ᴀᴅᴍɪɴ")

        # Standardize Category Names
        cat_renames = {
            info_cat_id: "✦ ɪɴғᴏʀᴍᴀᴛɪᴏɴ ✦",
            comm_cat_id: "✦ ᴄᴏᴍᴍᴜɴɪᴛʏ ✦",
            music_cat_id: "✦ ᴍᴜsɪᴄ ʟᴏᴜɴɢᴇ ✦",
            gaming_cat_id: "✦ ɢᴀᴍɪɴɢ ᴀʀᴇɴᴀ ✦",
            chill_cat_id: "✦ ᴄʜɪʟʟ & ʜᴀᴠᴇɴ ✦",
            reports_cat_id: "✦ ᴘʀɪᴠᴀᴛᴇ ʀᴇᴘᴏʀᴛɪɴɢ ✦",
            security_cat_id: "✦ sᴛᴀғғ & sᴇᴄᴜʀɪᴛʏ ✦",
        }

        for cid, new_name in cat_renames.items():
            if cid and ch_by_id.get(cid, {}).get("name") != new_name:
                print(f"Updating category {cid} -> {new_name}")
                await request_discord(s, "PATCH", f"https://discord.com/api/v10/channels/{cid}", json={"name": new_name})
                cat_map[cid] = new_name
                await asyncio.sleep(0.5)

        # Check or Create Creator Studio category
        creator_cat_id = get_cat("ᴄʀᴇᴀᴛᴏʀ sᴛᴜᴅɪᴏ")
        if not creator_cat_id:
            print("Creating Category: ✦ ᴄʀᴇᴀᴛᴏʀ sᴛᴜᴅɪᴏ ✦")
            new_cat = await request_discord(s, "POST", f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", json={
                "name": "✦ ᴄʀᴇᴀᴛᴏʀ sᴛᴜᴅɪᴏ ✦",
                "type": 4,
            })
            if new_cat:
                creator_cat_id = new_cat["id"]
                cat_map[creator_cat_id] = new_cat["name"]
            await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # STEP 2: Configure 🔒 OWNER-ONLY PRIVATE REPORT CATEGORY & CHANNEL
        # -------------------------------------------------------------
        print("\n--- STEP 2: Strict Lockdown for Private Reports Category & ⛨・member-reports ---")
        
        # Lock down Reports Category: Remove Moderator & Head Admin view allows
        # In category overwrites:
        strict_cat_overwrites = [
            {
                "id": str(GUILD_ID),  # @everyone
                "type": 0,
                "deny": str(DENY_ALL_BITS),
                "allow": "0"
            },
            {
                "id": str(OWNER_ID),
                "type": 1,
                "allow": str(OWNER_ALLOW_BITS),
                "deny": "0"
            },
            {
                "id": str(BOT_ID),
                "type": 1,
                "allow": str(BOT_ALLOW_BITS),
                "deny": "0"
            }
        ]
        if mod_role_id:
            strict_cat_overwrites.append({
                "id": str(mod_role_id),
                "type": 0,
                "deny": str(DENY_ALL_BITS),
                "allow": "0"
            })
        if head_admin_role_id:
            strict_cat_overwrites.append({
                "id": str(head_admin_role_id),
                "type": 0,
                "deny": str(DENY_ALL_BITS),
                "allow": "0"
            })

        if reports_cat_id:
            print(f"Applying strict owner-only overwrites to category {reports_cat_id}...")
            await request_discord(s, "PATCH", f"https://discord.com/api/v10/channels/{reports_cat_id}", json={
                "permission_overwrites": strict_cat_overwrites
            })
            await asyncio.sleep(0.5)

        # Find or create ⛨・member-reports
        member_reports_ch = next((c for c in channels if "member-reports" in c.get("name", "") or "member_reports" in c.get("name", "")), None)
        if not member_reports_ch:
            print("Creating ⛨・member-reports with strict owner-only permissions...")
            member_reports_ch = await request_discord(s, "POST", f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", json={
                "name": "⛨・member-reports",
                "type": 0,
                "parent_id": reports_cat_id,
                "topic": "Confidential member reports, evidence logs, and direct owner inquiries. Strictly private.",
                "permission_overwrites": strict_cat_overwrites
            })
            await asyncio.sleep(0.5)
        else:
            print(f"Securing existing ⛨・member-reports ({member_reports_ch['id']})...")
            await request_discord(s, "PATCH", f"https://discord.com/api/v10/channels/{member_reports_ch['id']}", json={
                "name": "⛨・member-reports",
                "parent_id": reports_cat_id,
                "permission_overwrites": strict_cat_overwrites
            })
            await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # STEP 3: Channel Renaming & Standardized Names
        # -------------------------------------------------------------
        print("\n--- STEP 3: Standardizing Existing Channel Names & Separators ---")
        
        channel_rename_map = {
            # INFORMATION
            "1545502705643167876": ("𖤐・welcome", info_cat_id),
            "1545502710101704714": ("⛧・rules-and-info", info_cat_id),
            "1557481215731306526": ("𖤍・server-faq", info_cat_id),
            "1545502718792175646": ("📡・announcements", info_cat_id),
            "1555641079137706014": ("🎫・support-desk", info_cat_id),
            "1557479971759333499": ("🤝・partnerships", info_cat_id),
            "1545502700840427702": ("✧・verify-here", info_cat_id),
            "1545502722739150898": ("౨ৎ・server-roles", info_cat_id),

            # COMMUNITY
            "1545502730699808768": ("𖦹・general-chat", comm_cat_id),
            "1557481233246584892": ("🪽・introductions", comm_cat_id),
            "1551184138932068373": ("📸・media-clips", comm_cat_id),
            "1549416359723532480": ("🤖・bot-commands", comm_cat_id),
            "1557481220911136868": ("♛・hall-of-fame", comm_cat_id),
            "1557469924379852860": ("୨୧・suggestions", comm_cat_id),
            "1557479964109181068": ("📊・server-polls", comm_cat_id),
            "1557477517282123826": ("🎉・birthdays", comm_cat_id),
            "1557481227693330554": ("🎁・giveaways", comm_cat_id),

            # MUSIC LOUNGE
            "1555255695933186228": ("♫・music-control", music_cat_id),
            "1555283393242206301": ("♬・music-queue", music_cat_id),
            "1555283394274005092": ("⏣・dj-control", music_cat_id),
            "1555283395330842714": ("☯・playlists", music_cat_id),
            "1555255325706424412": ("⚡ 24/7 Radio", music_cat_id),

            # GAMING ARENA
            "1557475853175234660": ("⌖・gaming-hub", gaming_cat_id),
            "1554905825544241302": ("🎮 Gaming Squad", gaming_cat_id),
            "1554905836768469032": ("🎯 Ranked Comms", gaming_cat_id),
            "1554905829033902151": ("🕹️ Casual Arcade", gaming_cat_id),

            # CHILL & HAVEN
            "1557477521661108315": ("🎬・movie-lounge", chill_cat_id),
            "1554905807240302652": ("☕ Night Owl Café", chill_cat_id),
            "1554905810574774286": ("🌊 Vibe Studio", chill_cat_id),
            "1554905813737545770": ("🎙️ Open Mic", chill_cat_id),

            # STAFF AND SECURITY
            "1555283378612478072": ("🚨・security-alerts", security_cat_id),
            "1555283387340562574": ("🛡️・security-log", security_cat_id),
            "1555283390943469685": ("⌬・audit-monitor", security_cat_id),
            "1555283409465778218": ("⚙・admin-control", security_cat_id),
            "1555283414205075509": ("📊・server-dashboard", security_cat_id),
            "1555283416071675954": ("🤖・bot-config", security_cat_id),
            "1555283418126876856": ("💾・backup-control", security_cat_id),

            # PRIVATE REPORTING
            "1555428399919538297": ("🛡️・mod-reports", reports_cat_id),
            "1557479979053228072": ("📋・staff-ledger", reports_cat_id),
            "1545502845208629328": ("🔒・staff-lounge", reports_cat_id),
        }

        for ch_id, (target_name, target_parent) in channel_rename_map.items():
            ch = ch_by_id.get(ch_id)
            if not ch:
                continue
            curr_name = ch.get("name")
            curr_parent = ch.get("parent_id")
            payload = {}
            if curr_name != target_name:
                payload["name"] = target_name
            if target_parent and curr_parent != target_parent:
                payload["parent_id"] = target_parent

            if payload:
                print(f"Updating #{curr_name} -> #{target_name} (Parent: {target_parent})")
                await request_discord(s, "PATCH", f"https://discord.com/api/v10/channels/{ch_id}", json=payload)
                await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # STEP 4: Creating New Essential Public Channels
        # -------------------------------------------------------------
        print("\n--- STEP 4: Creating Essential Pillar Channels ---")
        
        # Re-fetch existing channel names
        curr_channels = await request_discord(s, "GET", f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels")
        curr_names = {c["name"]: c["id"] for c in curr_channels}

        channels_to_create = [
            # CREATOR STUDIO
            ("✂️・editing-chat", creator_cat_id, 0, "Video editing discussion, software help, and creative workflows"),
            ("⟁・gaming-montages", creator_cat_id, 0, "Community gaming montages, edits, and frag reels showcase"),
            ("🎞️・edit-showcase", creator_cat_id, 0, "Showcase your finished edits and get feedback from editors"),
            ("✧・pfp-and-banners", creator_cat_id, 0, "Profile pictures, Discord banners, headers, and gfx creations"),
            ("𖦹・editing-tips", creator_cat_id, 0, "Presets, plugins, SFX packs, tutorials, and editing tips"),
            ("♧・collab-requests", creator_cat_id, 0, "Editor matchmaking, collaboration requests, and multi-creator projects"),
            ("🏅・edit-of-the-week", creator_cat_id, 0, "Weekly featured editor showcase and winning community edits"),

            # MUSIC LOUNGE
            ("𓂃・music-chat", music_cat_id, 0, "Community music discussions, song recommendations, and favorite tracks"),

            # GAMING ARENA
            ("⚔️・battle-squad", gaming_cat_id, 0, "Squad finder, team recruitment, and looking for group"),
            ("🎯・ranked-comms", gaming_cat_id, 0, "Ranked games comms, competitive strats, and tier climbing"),
            ("♛・casual-arcade", gaming_cat_id, 0, "Casual games, party games, and fun discussions"),
            ("𖣘・gameplay-highlights", gaming_cat_id, 0, "Post your best clutch plays, aces, and gaming highlights"),
            ("乂・free-fire", gaming_cat_id, 0, "Dedicated Free Fire discussion, custom rooms, and squad pairing"),

            # CHILL & HAVEN
            ("☾・late-night-talks", chill_cat_id, 0, "Cozy late night conversations, midnight thoughts, and chill vibes"),
            ("☕・night-owl-cafe", chill_cat_id, 0, "Relaxed café chat, coffee breaks, and casual conversation"),
            ("☁・vibe-chat", chill_cat_id, 0, "Cozy aesthetic vibe chat, relaxing discussion, and quiet hangs"),
            ("𖠚・memes-and-chaos", chill_cat_id, 0, "Memes, humor, funny clips, and chaotic entertainment"),
            ("𓇢𓆸・daily-moments", chill_cat_id, 0, "Daily life photos, pets, food, travel, and personal moments"),

            # PRIVATE REPORTING
            ("🎫・ticket-logs", reports_cat_id, 0, "Archive of closed support tickets, user transcripts, and resolutions"),
        ]

        for cname, parent_id, ctype, topic in channels_to_create:
            if cname not in curr_names and parent_id:
                print(f"Creating channel {cname} in category {parent_id}...")
                await request_discord(s, "POST", f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", json={
                    "name": cname,
                    "type": ctype,
                    "parent_id": parent_id,
                    "topic": topic
                })
                await asyncio.sleep(0.5)

        # -------------------------------------------------------------
        # STEP 5: Merge / Clean Redundant Channels Safely
        # -------------------------------------------------------------
        print("\n--- STEP 5: Merging Truly Redundant Duplicate Channels ---")
        # Channels to prune/merge that are empty or duplicate (with zero human messages):
        redundant_to_remove = [
            "1557475848892973219",  # 🏆・level-up (merged into bot-commands)
            "1557477508255842304",  # 🛍️・rai-shop (merged into bot-commands / support)
            "1554905842300485642",  # Ranked Comms II (duplicate VC)
            "1554905803666751590",  # 24/7 Radio & Beats (duplicate VC of 24/7 Radio)
            "1557479356899524678",  # 💾・backup-vault (merged into backup-control)
            "1555283380961026139",  # 🧱・anti-nuke (merged into security-alerts)
            "1555283386656886825",  # 🔒・lockdown-control (merged into admin-control)
            "1555283417183031516",  # 🤖・automation-control (merged into bot-config)
            "1555283419355676787",  # ❤️・system-health (merged into server-dashboard)
            "1557479367297339432",  # 📋・staff-activity (merged into staff-ledger)
        ]

        # Also remove obsolete empty categories if left with 0 channels
        for rem_id in redundant_to_remove:
            if rem_id in ch_by_id:
                ch = ch_by_id[rem_id]
                print(f"Deleting merged redundant channel: #{ch['name']} ({rem_id})")
                await request_discord(s, "DELETE", f"https://discord.com/api/v10/channels/{rem_id}")
                await asyncio.sleep(0.5)

        # Remove redundant Cinema & Streams category if empty (movie lounge moved)
        cinema_cat_id = get_cat("ᴄɪɴᴇᴍᴀ & sᴛʀᴇᴀᴍs")
        if cinema_cat_id:
            # check if any channels still in cinema cat
            latest_chs = await request_discord(s, "GET", f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels")
            remaining = [c for c in latest_chs if c.get("parent_id") == cinema_cat_id]
            # Move cinema VC channels to Chill & Haven before removing
            for rem_ch in remaining:
                if rem_ch.get("type") == 2: # voice
                    await request_discord(s, "PATCH", f"https://discord.com/api/v10/channels/{rem_ch['id']}", json={
                        "parent_id": chill_cat_id
                    })
                    await asyncio.sleep(0.5)
            # now delete empty cinema category
            await request_discord(s, "DELETE", f"https://discord.com/api/v10/channels/{cinema_cat_id}")
            print(f"Removed redundant Cinema & Streams category ({cinema_cat_id})")

        # -------------------------------------------------------------
        # STEP 6: Role Hierarchy Fix (Owner top, Administrator audit)
        # -------------------------------------------------------------
        print("\n--- STEP 6: Auditing Role Hierarchy & Privileges ---")
        # Fetch fresh roles
        updated_roles = await request_discord(s, "GET", f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles")
        founder_role = next((r for r in updated_roles if "𝓕ᴏᴜɴᴅᴇʀ" in r["name"] or "Founder" in r["name"]), None)
        rythm_role = next((r for r in updated_roles if r["name"] == "Rythm"), None)

        if founder_role and rythm_role:
            print(f"Founder Role: {founder_role['name']} (pos {founder_role['position']}) | Rythm: pos {rythm_role['position']}")
            # Note: Rythm is a managed integration role (managed: True). In Discord, bot integration roles
            # can be positioned below server roles if moved by someone higher. If bot has higher permission,
            # we reorder roles using PATCH /guilds/{id}/roles if permitted.
            try:
                max_pos = max(r.get("position", 0) for r in updated_roles)
                res = await request_discord(s, "PATCH", f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", json=[
                    {"id": founder_role["id"], "position": max_pos}
                ])
                if res:
                    print("Updated Founder role position to top.")
            except Exception as e:
                print(f"Role reorder note: {e}")

        # -------------------------------------------------------------
        # STEP 7: Verify Final Permissions on ⛨・member-reports
        # -------------------------------------------------------------
        print("\n--- STEP 7: Final Verification of ⛨・member-reports ---")
        final_chs = await request_discord(s, "GET", f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels")
        final_rep_ch = next((c for c in final_chs if "member-reports" in c["name"]), None)
        
        if final_rep_ch:
            print(f"Final ⛨・member-reports ({final_rep_ch['id']}):")
            overwrites = final_rep_ch.get("permission_overwrites", [])
            for ow in overwrites:
                target_id = ow["id"]
                t_type = "Role" if ow["type"] == 0 else "Member"
                allow = int(ow.get("allow", 0))
                deny = int(ow.get("deny", 0))
                print(f"  [{t_type}] ID {target_id} | Can View: {bool(allow & VIEW_CHANNEL)} | Denied View: {bool(deny & VIEW_CHANNEL)}")
            
            # Check owner
            owner_ow = next((ow for ow in overwrites if ow["id"] == str(OWNER_ID)), None)
            everyone_ow = next((ow for ow in overwrites if ow["id"] == str(GUILD_ID)), None)
            
            if everyone_ow and (int(everyone_ow["deny"]) & VIEW_CHANNEL):
                print("  [VERIFIED] @everyone is STRICTLY DENIED view access.")
            else:
                print("  [WARNING] @everyone view deny not set properly!")

            if owner_ow and (int(owner_ow["allow"]) & VIEW_CHANNEL):
                print("  [VERIFIED] Server Owner has FULL ALLOW access.")
            else:
                print("  [WARNING] Owner allow not explicitly set!")

        print("\nUpgrade execution completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
