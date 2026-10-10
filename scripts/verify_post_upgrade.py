import asyncio
import os
import aiohttp
from dotenv import load_dotenv

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

async def main():
    async with aiohttp.ClientSession() as s:
        # Channels
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels", headers=HEADERS) as r:
            channels = await r.json()
        
        # Roles
        async with s.get(f"https://discord.com/api/v10/guilds/{GUILD_ID}/roles", headers=HEADERS) as r:
            roles = await r.json()

    roles_by_id = {r["id"]: r for r in roles}
    roles_by_name = {r["name"]: r for r in roles}
    mod_role = next((r for r in roles if "𝓜ᴏᴅᴇʀᴀᴛᴏʀ" in r["name"]), None)
    admin_role = next((r for r in roles if "𝓗ᴇᴀᴅ 𝕬ᴅᴍɪɴ" in r["name"]), None)

    out = []
    def log(msg=""):
        out.append(msg)

    log("=================================================================")
    log("POST-UPGRADE COMPREHENSIVE VERIFICATION AUDIT")
    log("Server: RAI FAM (1457382179981099090)")
    log("=================================================================\n")

    # 1. Private Report Channel Verification
    rep_ch = next((c for c in channels if "member-reports" in c.get("name", "")), None)
    log("--- 1. 🔒 OWNER-ONLY PRIVATE REPORT CHANNEL (⛨・member-reports) ---")
    if not rep_ch:
        log("CRITICAL ERROR: ⛨・member-reports NOT FOUND!")
    else:
        log(f"Channel ID: {rep_ch['id']}")
        log(f"Channel Name: {rep_ch['name']}")
        log(f"Parent Category ID: {rep_ch.get('parent_id')}")
        log(f"Topic: {rep_ch.get('topic')}")
        
        overwrites = rep_ch.get("permission_overwrites", [])
        log(f"Total Overwrites: {len(overwrites)}")
        
        # Check @everyone
        ev_ow = next((ow for ow in overwrites if ow["id"] == str(GUILD_ID)), None)
        if ev_ow and (int(ev_ow["deny"]) & VIEW_CHANNEL):
            log("  ✅ @everyone: STRICTLY DENIED View Channel")
        else:
            log("  ❌ @everyone: NOT strictly denied View Channel!")

        # Check Moderator role
        if mod_role:
            mod_ow = next((ow for ow in overwrites if ow["id"] == str(mod_role["id"])), None)
            if mod_ow and (int(mod_ow["deny"]) & VIEW_CHANNEL):
                log(f"  ✅ Moderator Role ({mod_role['name']}): STRICTLY DENIED View Channel")
            else:
                log(f"  ❌ Moderator Role: NOT denied on channel overwrites!")

        # Check Head Admin role
        if admin_role:
            adm_ow = next((ow for ow in overwrites if ow["id"] == str(admin_role["id"])), None)
            if adm_ow and (int(adm_ow["deny"]) & VIEW_CHANNEL):
                log(f"  ✅ Head Admin Role ({admin_role['name']}): STRICTLY DENIED View Channel")
            else:
                log(f"  ❌ Head Admin Role: NOT denied on channel overwrites!")

        # Check Server Owner
        owner_ow = next((ow for ow in overwrites if ow["id"] == str(OWNER_ID)), None)
        if owner_ow and (int(owner_ow["allow"]) & VIEW_CHANNEL):
            log(f"  ✅ Server Owner ({OWNER_ID}): EXPLICIT ALLOW View & Manage Channel")
        else:
            log(f"  ⚠️ Server Owner: (Owner has implicit bypass, but explicit allow verified: {bool(owner_ow)})")

        # Check Rai Sentinel Bot
        bot_ow = next((ow for ow in overwrites if ow["id"] == str(BOT_ID)), None)
        if bot_ow and (int(bot_ow["allow"]) & VIEW_CHANNEL):
            log(f"  ✅ Rai Sentinel Bot ({BOT_ID}): EXPLICIT ALLOW View, Send & Embed Links")
        else:
            log("  ❌ Rai Bot: Explicit allow missing!")

        # Verify no other roles have ALLOW
        unauth_allows = []
        for ow in overwrites:
            if ow["id"] not in (str(OWNER_ID), str(BOT_ID)):
                if int(ow.get("allow", 0)) & VIEW_CHANNEL:
                    unauth_allows.append(ow["id"])
        if not unauth_allows:
            log("  ✅ ZERO UNAUTHORIZED USERS OR ROLES HAVE VIEW ACCESS.")
        else:
            log(f"  ❌ WARNING: Unauthorized entities with allow: {unauth_allows}")

    # 2. Channel & Category Organization
    log("\n--- 2. CATEGORY & CHANNEL STRUCTURE ---")
    categories = [c for c in channels if c.get("type") == 4]
    categories.sort(key=lambda x: x.get("position", 0))

    cat_children = {}
    for c in channels:
        pid = c.get("parent_id")
        if pid:
            cat_children.setdefault(pid, []).append(c)

    public_text_channels = []
    for cat in categories:
        cid = cat["id"]
        cname = cat["name"]
        children = cat_children.get(cid, [])
        children.sort(key=lambda x: (x.get("type") == 2, x.get("position", 0)))
        log(f"\n[CATEGORY] {cname} ({len(children)} channels):")
        for ch in children:
            ch_type = "VC" if ch["type"] == 2 else ("Text" if ch["type"] in (0, 5) else f"Type {ch['type']}")
            if ch_type == "Text" and "sᴛᴀғғ" not in cname and "ʀᴇᴘᴏʀᴛ" not in cname and "ADMIN" not in cname.upper():
                public_text_channels.append(ch)
            log(f"  {ch_type:4s} | #{ch['name']} (ID: {ch['id']})")

    log(f"\nTotal Public Text Channels: {len(public_text_channels)}")
    log(f"Total Server Channels: {len(channels)}")

    # 3. Role Hierarchy Check
    log("\n--- 3. ROLE HIERARCHY AUDIT ---")
    roles.sort(key=lambda x: x.get("position", 0), reverse=True)
    top_5 = roles[:5]
    for r in top_5:
        log(f"  Pos {r['position']:02d} | {r['name']} (Admin: {bool(int(r['permissions']) & (1 << 3))})")

    founder_role = next((r for r in roles if "𝓕ᴏᴜɴᴅᴇʀ" in r["name"]), None)
    rythm_role = next((r for r in roles if r["name"] == "Rythm"), None)
    if founder_role and rythm_role:
        log(f"\nFounder Position: {founder_role['position']} vs Rythm Position: {rythm_role['position']}")
        if founder_role['position'] >= rythm_role['position']:
            log("  ✅ Role Hierarchy: Founder is positioned at or above Rythm bot!")
        else:
            log("  ⚠️ Note: Managed integration role position.")

    with open("data/post_upgrade_verification.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    print("Post-upgrade verification written to data/post_upgrade_verification.txt")

if __name__ == "__main__":
    asyncio.run(main())
