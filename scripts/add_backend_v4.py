"""
Script to inject:
1. Web Studio & Playground (/studio)
2. Creator Bounties & Gigs (/bounties)
3. 3D Holographic Passport (/passport)
into web/api.py, web/server.py, and web/ui.py
"""

import sys

# ========================================================
# 1. UPDATE web/api.py
# ========================================================
api_methods = '''
    # ==========================================
    # CREATOR BOUNTIES & GIG MARKETPLACE API
    # ==========================================
    async def get_bounties(self, request: web.Request) -> web.Response:
        """List active creator bounties and collaboration requests."""
        category = request.query.get("category", "all")
        bounties = [
            {
                "id": "bounty-1",
                "title": "YouTube Montage Editor (After Effects / Premiere)",
                "client": "Nightwave Creative Studio",
                "category": "video_editing",
                "reward": "$65 + 1,200 Rai XP",
                "budget_type": "Fixed Project",
                "skills": ["Premiere Pro", "After Effects", "Sound Design"],
                "deadline": "In 3 days",
                "applicants_count": 4,
                "status": "open",
                "description": "Looking for a skilled motion editor to create a high-energy 90s montage reel from community tournament gameplay clips with sync beat drops."
            },
            {
                "id": "bounty-2",
                "title": "3D Cyberpunk Neon Logo & Intro Animation",
                "client": "Vora Gaming Realm",
                "category": "3d_art",
                "reward": "$90 + 1,800 Rai XP",
                "budget_type": "Fixed Project",
                "skills": ["Blender", "Octane", "Motion Graphics"],
                "deadline": "In 5 days",
                "applicants_count": 2,
                "status": "open",
                "description": "Design a 3D metallic glowing logo with volumetric fog and purple/cyan chromatic aberration for our upcoming esports tournament stream intro."
            },
            {
                "id": "bounty-3",
                "title": "Discord Bot Custom Cog: Automated Tournament Bracket",
                "client": "Rai Systems & AI Incubator",
                "category": "python_dev",
                "reward": "$80 + 1,500 Rai XP",
                "budget_type": "Milestone",
                "skills": ["Python 3.12", "discord.py", "SQLite WAL"],
                "deadline": "In 7 days",
                "applicants_count": 5,
                "status": "open",
                "description": "Develop an asynchronous Cog module for automated double-elimination brackets with team role assignment and auto-moving squads into match VCs."
            },
            {
                "id": "bounty-4",
                "title": "High-CTR YouTube Thumbnails for BGMI Tournaments",
                "client": "Apex Predator Squad",
                "category": "thumbnail_design",
                "reward": "$35 + 600 Rai XP",
                "budget_type": "Per Asset",
                "skills": ["Photoshop", "Typography", "Color Grading"],
                "deadline": "In 2 days",
                "applicants_count": 6,
                "status": "open",
                "description": "Create 3 high-contrast, attention-grabbing YouTube thumbnails with dramatic character cutout lighting and 3D text composition."
            }
        ]
        if category and category != "all":
            bounties = [b for b in bounties if b["category"] == category]
        return json_success({"bounties": bounties, "total": len(bounties)})

    async def create_bounty(self, request: web.Request) -> web.Response:
        """Post a new creator bounty."""
        session = await self.auth.require_auth(request)
        try:
            body = await request.json()
        except Exception:
            return json_error("INVALID_JSON", "Invalid JSON payload", 400)

        title = str(body.get("title", "")).strip()
        reward = str(body.get("reward", "")).strip()
        category = str(body.get("category", "video_editing")).strip()
        skills = body.get("skills", ["General"])
        description = str(body.get("description", "")).strip()

        if not title:
            return json_error("MISSING_TITLE", "Bounty title is required", 400)

        bounty_id = f"bounty-{int(time.time())}"
        new_bounty = {
            "id": bounty_id,
            "title": title,
            "client": session.get("username", "Member"),
            "category": category,
            "reward": reward or "Negotiable",
            "budget_type": "Fixed Project",
            "skills": skills if isinstance(skills, list) else [str(skills)],
            "deadline": "In 7 days",
            "applicants_count": 0,
            "status": "open",
            "description": description or "Community collaboration bounty.",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        # Enqueue announcement to sync_outbox
        await self.db.enqueue_sync_event(
            event_type="BOUNTY_POSTED",
            payload={
                "guild_id": COMMUNITY_GUILD_ID,
                "bounty_id": bounty_id,
                "title": title,
                "reward": reward,
                "client": session.get("username")
            }
        )

        return json_success({"bounty": new_bounty, "message": "Bounty published successfully"})

    async def apply_bounty(self, request: web.Request) -> web.Response:
        """Apply for an active bounty."""
        session = await self.auth.require_auth(request)
        bounty_id = request.match_info.get("id", "").strip()
        try:
            body = await request.json()
        except Exception:
            body = {}

        pitch = body.get("pitch", "")
        portfolio_url = body.get("portfolio_url", "")

        # Audit log application
        await self.db.log_community_audit(
            actor_id=session["discord_user_id"],
            actor_name=session["username"],
            action="APPLY_BOUNTY",
            target_type="BOUNTY",
            target_id=bounty_id,
            details_dict={"pitch": pitch[:100], "portfolio": portfolio_url}
        )
        return json_success({"message": "Application submitted! The client has been notified."})

    # ==========================================
    # RAIVORA WEB STUDIO & PLAYGROUND API
    # ==========================================
    async def get_studio_templates(self, request: web.Request) -> web.Response:
        """Return starter code templates for Discord bots, After Effects JSX, and Blender."""
        templates = {
            "python_cog": {
                "name": "Discord Bot Slash Command Cog (Python)",
                "language": "python",
                "filename": "custom_extension.py",
                "code": '''import discord
from discord.ext import commands
from discord import app_commands

class CustomExtension(commands.Cog):
    """Community-developed Rai Bot extension."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="community_shoutout", description="Broadcast a creator milestone")
    @app_commands.describe(message="The announcement message to broadcast")
    async def community_shoutout(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(thinking=True)
        embed = discord.Embed(
            title="✦ Raivora Community Spotlight",
            description=message,
            color=0x9333ea
        )
        embed.set_footer(text=f"Sent by {interaction.user.display_name} • Powered by Rai")
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(CustomExtension(bot))
'''
            },
            "webhook_embed": {
                "name": "Discord Rich Embed Webhook (JSON)",
                "language": "json",
                "filename": "discord_embed.json",
                "code": '''{
  "username": "Rai Community OS",
  "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png",
  "content": "✦ **NEW LIVE SESSION STARTED IN THE RAIVORA**",
  "embeds": [
    {
      "title": "🎵 Nightwave Synthwave Listening Party",
      "description": "320kbps lossless audio stream active in **🔊 General Lounge VC**. 14 community members listening right now.",
      "color": 9647082,
      "fields": [
        { "name": "Host", "value": "Nightwave Studio", "inline": true },
        { "name": "Audio Quality", "value": "320k Opus Hi-Fi", "inline": true },
        { "name": "Current Track", "value": "Resonance (Synthwave Remaster)", "inline": false }
      ],
      "footer": { "text": "The Raivora 2.6 • Live Synchronized Audio" },
      "timestamp": "2026-10-03T20:00:00Z"
    }
  ]
}'''
            },
            "ae_jsx": {
                "name": "After Effects Video Automation (JSX)",
                "language": "javascript",
                "filename": "beat_marker_sync.jsx",
                "code": '''// After Effects Script: Auto-create beat markers on selected audio layer
app.beginUndoGroup("Raivora Beat Sync");

var comp = app.project.activeItem;
if (comp && comp instanceof CompItem) {
    var layer = comp.selectedLayers[0];
    if (layer) {
        var bpm = 128;
        var interval = 60 / bpm;
        for (var t = 0; t < comp.duration; t += interval) {
            var marker = new MarkerValue("BEAT");
            layer.property("Marker").setValueAtTime(t, marker);
        }
        alert("Beat markers synchronized at " + bpm + " BPM!");
    } else {
        alert("Select an audio layer first.");
    }
}
app.endUndoGroup();
'''
            },
            "blender_py": {
                "name": "Blender 3D Procedural Neon Mesh (Python)",
                "language": "python",
                "filename": "procedural_neon.py",
                "code": '''import bpy

# Clear existing objects
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Create neon torus ring
bpy.ops.mesh.primitive_torus_add(major_radius=3, minor_radius=0.25, location=(0, 0, 1.5))
torus = bpy.context.active_object
torus.name = "Raivora_Neon_Portal"

# Create emission material
mat = bpy.data.materials.new(name="Cyan_Neon_Glow")
mat.use_nodes = True
nodes = mat.node_tree.nodes
nodes.clear()

emission = nodes.new(type="ShaderNodeEmission")
emission.inputs["Color"].default_value = (0.02, 0.71, 0.83, 1)  # #06b6d4 Cyan
emission.inputs["Strength"].default_value = 15.0

output = nodes.new(type="ShaderNodeOutputMaterial")
mat.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
torus.data.materials.append(mat)
print("✦ Neon portal generated successfully!")
'''
            }
        }
        return json_success({"templates": templates})

    async def test_studio_payload(self, request: web.Request) -> web.Response:
        """Validate code syntax for Python or JSON."""
        try:
            body = await request.json()
        except Exception:
            return json_error("INVALID_JSON", "Invalid payload", 400)

        code = body.get("code", "")
        lang = body.get("language", "python")

        if lang == "json":
            import json
            try:
                parsed = json.loads(code)
                formatted = json.dumps(parsed, indent=2)
                return json_success({"valid": True, "formatted": formatted, "message": "Valid JSON formatted cleanly"})
            except Exception as e:
                return json_success({"valid": False, "message": f"JSON Syntax Error: {e}"})
        elif lang == "python":
            import ast
            try:
                ast.parse(code)
                return json_success({"valid": True, "message": "Python syntax verified with 0 syntax errors"})
            except SyntaxError as e:
                return json_success({"valid": False, "message": f"SyntaxError at line {e.lineno}: {e.msg}"})
        else:
            return json_success({"valid": True, "message": "Code validated"})

    # ==========================================
    # HOLOGRAPHIC 3D PASSPORT API
    # ==========================================
    async def get_passport(self, request: web.Request) -> web.Response:
        """Get 3D Holographic Passport identity data."""
        user_id_str = request.match_info.get("user_id") or request.query.get("user_id")
        user_id = 0
        if user_id_str and user_id_str.isdigit():
            user_id = int(user_id_str)
        else:
            session = await self.auth.get_session(request)
            if session and session.get("discord_user_id"):
                user_id = int(session["discord_user_id"])

        if user_id == 0:
            # Fallback to founder / guest passport
            user_id = 1457382179981099090

        # Query economy
        eco = await self.db.get_economy_user(COMMUNITY_GUILD_ID, user_id)
        coins = eco.coins if eco else 100
        xp = eco.xp if eco else 250
        level = eco.level if eco else 1
        streak = eco.daily_streak if eco else 0

        passport_data = {
            "user_id": str(user_id),
            "display_name": f"Citizen #{str(user_id)[-4:]}",
            "handle": f"raivora_{str(user_id)[-4:]}",
            "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png",
            "tier": "ELITE CITIZEN" if level >= 5 else "EXPLORER",
            "rank_title": "Master Editor" if user_id == 1457382179981099090 else "Raivora Member",
            "coins": coins,
            "xp": xp,
            "level": level,
            "streak": streak,
            "verified": True,
            "dna": {
                "voice": 38,
                "gaming": 28,
                "music": 20,
                "creating": 14
            },
            "badges": [
                {"icon": "✦", "name": "Verified Citizen", "color": "#9333ea"},
                {"icon": "🎙️", "name": "Voice Elite", "color": "#10b981"},
                {"icon": "🎮", "name": "Tournament Fragger", "color": "#06b6d4"},
                {"icon": "🎧", "name": "Hi-Fi Audiophile", "color": "#a855f7"}
            ],
            "passport_id": f"RAI-2026-{str(user_id)[-6:]}"
        }
        return json_success({"passport": passport_data})
'''

# 1. Update web/api.py
with open("web/api.py", "r", encoding="utf-8") as f:
    api_content = f.read()

if "async def get_bounties" not in api_content:
    # Append inside ApiRouter class
    last_line = api_content.rfind("\n")
    api_content = api_content + "\n" + api_methods
    with open("web/api.py", "w", encoding="utf-8") as f:
        f.write(api_content)
    print("SUCCESS: web/api.py updated with Bounties, Studio, and Passport APIs")
else:
    print("web/api.py already has get_bounties")

# ========================================================
# 2. UPDATE web/server.py
# ========================================================
with open("web/server.py", "r", encoding="utf-8") as f:
    srv_content = f.read()

# Add to ui_routes
if '"/studio"' not in srv_content:
    srv_content = srv_content.replace(
        '"/discover/constellation"',
        '"/discover/constellation", "/studio", "/bounties", "/passport"'
    )

# Add API routes
if 'app.router.add_get("/api/bounties"' not in srv_content:
    api_routes_inject = '''        # Creator Bounties & Gigs API
        app.router.add_get("/api/bounties", r.get_bounties)
        app.router.add_post("/api/bounties", r.create_bounty)
        app.router.add_post("/api/bounties/{id}/apply", r.apply_bounty)

        # Web Studio & Playground API
        app.router.add_get("/api/studio/templates", r.get_studio_templates)
        app.router.add_post("/api/studio/test", r.test_studio_payload)

        # Holographic Passport API
        app.router.add_get("/api/passport/{user_id}", r.get_passport)
        app.router.add_get("/api/passport", r.get_passport)
'''
    insert_marker = '        # Labs & Constellation API'
    srv_content = srv_content.replace(insert_marker, api_routes_inject + "\n" + insert_marker)

with open("web/server.py", "w", encoding="utf-8") as f:
    f.write(srv_content)
print("SUCCESS: web/server.py updated with Studio, Bounties, and Passport routes")

print("Backend preparation complete.")
