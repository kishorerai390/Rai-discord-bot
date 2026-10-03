"""
Futuristic Cyberpunk Discord Server Branding & Structure Management System for 『RΛI』.
Handles:
- Category & channel specifications
- Emergency channel definitions
- Voice channel branding
- Role branding & hierarchy preservation
- Non-destructive dry-run structure preview & explicit admin deployment
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import discord

from config.settings import Branding, Colors
from utils.embeds import create_embed, DEFAULT_BRAND, DEFAULT_FOOTER

logger = logging.getLogger("Rai.Branding")

# ==========================================
# 1. SPECIFICATION REGISTRY
# ==========================================

# Internal safe identifiers -> Discord display names
CATEGORIES_SPEC = {
    "rai_security": {
        "name": "🛡️・RΛI SECURITY",
        "description": "Server defense, threat detection, and audit infrastructure",
        "channels": [
            ("🚨・threat-detection", "Real-time threat detection feeds"),
            ("☢️・anti-nuke", "Anti-nuke administrative action containment"),
            ("⚔️・anti-raid", "Anti-raid velocity monitoring and quarantine"),
            ("🔐・anti-spam", "Anti-spam filtering alerts and rate limit violations"),
            ("🤖・automod", "Autonomous moderation and disciplinary logs"),
            ("🔒・lockdown", "Emergency lockdown status and perimeter controls"),
            ("🕵️・security-events", "Chronological threat and security incident timeline"),
            ("📋・audit-logs", "Administrative audit trail and configuration changes"),
        ],
    },
    "rai_music": {
        "name": "🎵・RΛI MUSIC",
        "description": "High-fidelity audio streaming and queue controls",
        "channels": [
            ("🎧・now-playing", "Live track metadata and interactive control panel"),
            ("📜・queue", "Current guild audio buffer and upcoming tracks"),
            ("🎶・music-control", "Interactive playback buttons and controls"),
            ("🔊・dj-control", "DJ role access and override controls"),
            ("💿・playlists", "Saved user and guild playlists repository"),
            ("🎼・music-requests", "Public member song requests and searches"),
        ],
    },
    "rai_system": {
        "name": "⚙️・RΛI SYSTEM",
        "description": "Bot operational telemetry, database, and diagnostics",
        "channels": [
            ("🤖・bot-status", "Discord gateway heartbeat and status updates"),
            ("📊・system-stats", "Server metrics and telemetry overview"),
            ("🧠・ai-status", "Neural incident responder and brain status"),
            ("💾・database", "Database connection metrics and WAL snapshots"),
            ("🩺・health-status", "Subsystem supervisor and lag detector output"),
            ("🔧・maintenance", "Self-healing and scheduled maintenance logs"),
            ("📡・system-events", "Background workers and task lifecycle notifications"),
        ],
    },
    "rai_admin": {
        "name": "👑・RΛI ADMIN",
        "description": "High-privilege founder and administrator controls",
        "channels": [
            ("⚡・admin-control", "Direct command terminal for server administrators"),
            ("🛠️・configuration", "Settings toggles, thresholds, and operational flags"),
            ("🔑・permissions", "Role hierarchy and permission overrides"),
            ("🧰・tools", "Server management and utility operations"),
            ("📦・backup", "Scheduled server snapshot and configuration backups"),
            ("♻️・restore", "Safe restoration points and rollback tools"),
            ("🚨・emergency-control", "Immediate emergency stop and manual panic switch"),
        ],
    },
}

EMERGENCY_CHANNELS_SPEC = [
    ("🚨・raid-alert", "Mass join spikes and automated quarantine notices"),
    ("🔴・critical-alert", "Severe security violations requiring admin action"),
    ("☢️・nuke-detection", "Unauthorized channel/role deletions detected"),
    ("🔒・emergency-lock", "Perimeter lockdown status and containment controls"),
    ("🛡️・security-center", "Master security dashboard and shield overview"),
    ("📡・incident-log", "Detailed forensics and evidence collection logs"),
]

VOICE_CHANNELS_SPEC = [
    "🔊・RΛI MUSIC",
    "🎧・RΛI LOUNGE",
    "🎵・MUSIC ROOM",
    "🎶・LISTENING ROOM",
    "⚡・RAI RADIO",
]

ROLES_SPEC = {
    "bot": [
        ("𖤐 RΛI • CORE", 0x00F0FF, "Master bot identity role"),
        ("🤖 RΛI • BOT", 0x9D00FF, "Core automation service role"),
        ("⚡ RΛI • SYSTEM", 0x2B2D31, "Background daemon worker role"),
    ],
    "security": [
        ("🛡️ Security", 0xEB459E, "Security controller access"),
        ("⚔️ Guardian", 0x5865F2, "Server defense and raid response"),
        ("🔐 Security Admin", 0xFF0055, "Security policy management"),
        ("🚨 Incident Manager", 0xED4245, "Incident response and alerts"),
        ("🕵️ Threat Analyst", 0x3498DB, "Forensics and log auditor"),
    ],
    "music": [
        ("🎧 DJ", 0x9D00FF, "Music playback and queue management"),
        ("🎵 Music Manager", 0x5865F2, "Playlist and volume administrator"),
        ("🎚️ Audio Controller", 0x00F0FF, "Voice channel audio controller"),
    ],
    "staff": [
        ("👑 Owner", 0xF1C40F, "Server Founder & Primary Administrator"),
        ("⚡ Administrator", 0xE67E22, "Full management permissions"),
        ("🛡️ Moderator", 0x2ECC71, "Member discipline and chat moderation"),
        ("🔧 Staff", 0x95A5A6, "General server support staff"),
    ],
}


# ==========================================
# 2. PLAN & DRY-RUN DATASTRUCTURES
# ==========================================

@dataclass
class ChannelPlanItem:
    name: str
    purpose: str
    category_name: str
    is_emergency: bool = False
    is_voice: bool = False


@dataclass
class RolePlanItem:
    name: str
    color_hex: int
    group: str
    description: str


@dataclass
class ServerStructurePlan:
    guild_id: int
    guild_name: str
    categories_to_create: List[str] = field(default_factory=list)
    channels_to_create: List[ChannelPlanItem] = field(default_factory=list)
    channels_to_rename: List[Tuple[str, str]] = field(default_factory=list)  # (old, new)
    roles_to_create: List[RolePlanItem] = field(default_factory=list)
    roles_to_rename: List[Tuple[str, str]] = field(default_factory=list)      # (old, new)
    untouched_channels: List[str] = field(default_factory=list)
    untouched_roles: List[str] = field(default_factory=list)
    permission_notes: List[str] = field(default_factory=list)


# ==========================================
# 3. INSPECTION & PLANNING ENGINE
# ==========================================

class ServerBrandingManager:
    """Safe, non-destructive server branding and structure orchestrator."""

    @staticmethod
    def normalize_name(name: str) -> str:
        """Strip emojis, special dots, and spaces to match underlying channel types."""
        clean = name.lower()
        for char in ["・", "-", "_", " ", "🚨", "☢️", "⚔️", "🔐", "🤖", "🔒", "🕵️", "📋", "🎧", "📜", "🎶", "🔊", "💿", "🎼", "⚙️", "📊", "🧠", "💾", "🩺", "🔧", "📡", "👑", "⚡", "🛠️", "🔑", "🧰", "📦", "♻️", "🔴", "🛡️"]:
            clean = clean.replace(char, "")
        return clean.strip()

    @classmethod
    def generate_plan(cls, guild: discord.Guild, include_voice: bool = False) -> ServerStructurePlan:
        """
        Inspects existing guild categories, channels, and roles.
        Generates a non-destructive plan indicating what will be created or mapped,
        WITHOUT modifying any Discord resources.
        """
        plan = ServerStructurePlan(guild_id=guild.id, guild_name=guild.name)

        existing_categories = {c.name.lower(): c for c in guild.categories}
        existing_text_channels = {c.name.lower(): c for c in guild.text_channels}
        existing_voice_channels = {c.name.lower(): c for c in guild.voice_channels}
        existing_roles = {r.name.lower(): r for r in guild.roles}

        # 1. Inspect Categories & Text Channels
        for cat_key, cat_data in CATEGORIES_SPEC.items():
            cat_name = cat_data["name"]
            cat_found = None
            for ex_name, ex_cat in existing_categories.items():
                if cls.normalize_name(ex_name) == cls.normalize_name(cat_name):
                    cat_found = ex_cat
                    break

            if not cat_found:
                plan.categories_to_create.append(cat_name)

            for ch_name, ch_purpose in cat_data["channels"]:
                ch_found = None
                for ex_name, ex_ch in existing_text_channels.items():
                    if cls.normalize_name(ex_name) == cls.normalize_name(ch_name):
                        ch_found = ex_ch
                        break

                if not ch_found:
                    plan.channels_to_create.append(
                        ChannelPlanItem(name=ch_name, purpose=ch_purpose, category_name=cat_name)
                    )
                else:
                    if ch_found.name != ch_name:
                        plan.channels_to_rename.append((ch_found.name, ch_name))
                    else:
                        plan.untouched_channels.append(ch_found.name)

        # 2. Inspect Emergency Channels
        emergency_cat = "🛡️・RΛI SECURITY"
        for em_name, em_purpose in EMERGENCY_CHANNELS_SPEC:
            em_found = None
            for ex_name, ex_ch in existing_text_channels.items():
                if cls.normalize_name(ex_name) == cls.normalize_name(em_name):
                    em_found = ex_ch
                    break
            if not em_found:
                plan.channels_to_create.append(
                    ChannelPlanItem(name=em_name, purpose=em_purpose, category_name=emergency_cat, is_emergency=True)
                )

        # 3. Optional Voice Channels
        if include_voice:
            music_cat = "🎵・RΛI MUSIC"
            for vc_name in VOICE_CHANNELS_SPEC:
                vc_found = None
                for ex_name, ex_vc in existing_voice_channels.items():
                    if cls.normalize_name(ex_name) == cls.normalize_name(vc_name):
                        vc_found = ex_vc
                        break
                if not vc_found:
                    plan.channels_to_create.append(
                        ChannelPlanItem(name=vc_name, purpose="Voice streaming lounge", category_name=music_cat, is_voice=True)
                    )

        # 4. Inspect Roles (DO NOT modify existing permissions)
        for group, role_list in ROLES_SPEC.items():
            for r_name, r_color, r_desc in role_list:
                r_found = None
                for ex_name, ex_r in existing_roles.items():
                    if cls.normalize_name(ex_name) == cls.normalize_name(r_name):
                        r_found = ex_r
                        break

                if not r_found:
                    plan.roles_to_create.append(
                        RolePlanItem(name=r_name, color_hex=r_color, group=group.upper(), description=r_desc)
                    )
                else:
                    if r_found.name != r_name:
                        plan.roles_to_rename.append((r_found.name, r_name))
                    else:
                        plan.untouched_roles.append(r_found.name)

        plan.permission_notes.append(
            "🔒 **Existing Permissions Preserved**: Bot will NOT alter administrative, moderation, or channel permissions on any existing role."
        )
        plan.permission_notes.append(
            "🛡️ **Admin Safety**: Emergency and Admin categories will be created with private permissions viewable only by Administrators."
        )

        return plan

    @classmethod
    async def apply_plan(
        cls,
        guild: discord.Guild,
        plan: ServerStructurePlan,
        bot_member: discord.Member,
    ) -> Dict[str, Any]:
        """
        Executes structural deployment safely upon explicit administrator confirmation:
        - Never deletes existing channels or roles.
        - Preserves existing permissions.
        - Avoids duplicate creations.
        """
        results = {
            "categories_created": 0,
            "channels_created": 0,
            "roles_created": 0,
            "errors": [],
        }

        # 1. Create or map categories
        category_map: Dict[str, discord.CategoryChannel] = {}
        for cat in guild.categories:
            category_map[cat.name] = cat

        for cat_name in plan.categories_to_create:
            if cat_name not in category_map:
                try:
                    overwrites = {}
                    # Admin and Security categories default to restricted visibility
                    if "ADMIN" in cat_name or "SECURITY" in cat_name:
                        overwrites[guild.default_role] = discord.PermissionOverwrite(read_messages=False)
                        overwrites[bot_member] = discord.PermissionOverwrite(read_messages=True, manage_channels=True)

                    new_cat = await guild.create_category(
                        name=cat_name,
                        overwrites=overwrites,
                        reason="『RΛI』 Futuristic Cyberpunk Server Structure Setup",
                    )
                    category_map[cat_name] = new_cat
                    results["categories_created"] += 1
                except Exception as e:
                    results["errors"].append(f"Category '{cat_name}': {e}")

        # 2. Create planned channels inside target categories
        for ch_item in plan.channels_to_create:
            cat = category_map.get(ch_item.category_name)
            try:
                # Double-check existence to avoid race-condition duplication
                if ch_item.is_voice:
                    if not any(cls.normalize_name(vc.name) == cls.normalize_name(ch_item.name) for vc in guild.voice_channels):
                        await guild.create_voice_channel(
                            name=ch_item.name,
                            category=cat,
                            reason="『RΛI』 Server Branding Setup",
                        )
                        results["channels_created"] += 1
                else:
                    if not any(cls.normalize_name(tc.name) == cls.normalize_name(ch_item.name) for tc in guild.text_channels):
                        overwrites = {}
                        if ch_item.is_emergency or "admin" in ch_item.name or "audit" in ch_item.name:
                            overwrites[guild.default_role] = discord.PermissionOverwrite(read_messages=False)
                            overwrites[bot_member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

                        await guild.create_text_channel(
                            name=ch_item.name,
                            category=cat,
                            topic=f"『RΛI』 • {ch_item.purpose}",
                            overwrites=overwrites,
                            reason="『RΛI』 Server Branding Setup",
                        )
                        results["channels_created"] += 1
            except Exception as e:
                results["errors"].append(f"Channel '{ch_item.name}': {e}")

        # 3. Create planned roles without altering existing permissions
        for r_item in plan.roles_to_create:
            try:
                if not any(cls.normalize_name(r.name) == cls.normalize_name(r_item.name) for r in guild.roles):
                    await guild.create_role(
                        name=r_item.name,
                        color=discord.Color(r_item.color_hex),
                        mentionable=False,
                        reason=f"『RΛI』 Cyberpunk Role Branding ({r_item.group})",
                    )
                    results["roles_created"] += 1
            except Exception as e:
                results["errors"].append(f"Role '{r_item.name}': {e}")

        return results

    @classmethod
    def format_plan_embed(cls, plan: ServerStructurePlan) -> discord.Embed:
        """Generates a rich, futuristic preview embed for administrator inspection."""
        embed = discord.Embed(
            title=f"{DEFAULT_BRAND} • SERVER STRUCTURE PREVIEW",
            color=Colors.CYBER_CYAN,
            description=(
                f"**Target Guild:** `{plan.guild_name}`\n"
                f"*Review the planned structure below. This is a non-destructive dry-run. "
                f"No changes will be applied until explicitly confirmed.*"
            ),
        )

        cat_summary = (
            f"**To Create ({len(plan.categories_to_create)}):**\n" +
            ("\n".join(f"• `{c}`" for c in plan.categories_to_create) if plan.categories_to_create else "*All categories exist.*")
        )
        embed.add_field(name="📁 Categories", value=cat_summary, inline=False)

        ch_summary = (
            f"**To Create ({len(plan.channels_to_create)}):**\n" +
            ("\n".join(f"• `{c.name}` *({c.category_name})*" for c in plan.channels_to_create[:12]) if plan.channels_to_create else "*All channels exist.*")
        )
        if len(plan.channels_to_create) > 12:
            ch_summary += f"\n*...and {len(plan.channels_to_create) - 12} more.*"
        embed.add_field(name="💬 Channels", value=ch_summary, inline=False)

        roles_summary = (
            f"**To Create ({len(plan.roles_to_create)}):**\n" +
            ("\n".join(f"• `{r.name}` *({r.group})*" for r in plan.roles_to_create) if plan.roles_to_create else "*All roles exist.*")
        )
        embed.add_field(name="🏷️ Roles", value=roles_summary, inline=False)

        embed.add_field(
            name="🛡️ Safe Mode Guarantees",
            value="\n".join(plan.permission_notes),
            inline=False,
        )

        embed.set_footer(text=DEFAULT_FOOTER)
        return embed
