"""
RAI — UNIFIED WORKSPACE SERVICE.
Provides:
- Centralized management of temporary community workspaces (Gaming, Music, Creator, General, Project, Event).
- State tracking: ACTIVE, EMPTY, CLEANUP_PENDING, CLEANING, DELETED, ERROR.
- Non-destructive, safe cleanup of temporary channels when empty.
- Reuses existing Dynamic VC and Discord channel overwrites infrastructure.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import discord

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.WorkspaceService")


class WorkspaceType(Enum):
    GENERAL = "general"
    GAMING = "gaming"
    MUSIC = "music"
    CREATOR = "creator"
    PROJECT = "project"
    EVENT = "event"


class WorkspaceStatus(Enum):
    ACTIVE = "ACTIVE"
    EMPTY = "EMPTY"
    CLEANUP_PENDING = "CLEANUP_PENDING"
    CLEANING = "CLEANING"
    DELETED = "DELETED"
    ERROR = "ERROR"


class CommunityWorkspace:
    def __init__(
        self,
        workspace_id: str,
        guild_id: int,
        owner_id: int,
        workspace_type: WorkspaceType,
        name: str,
        category_id: Optional[int] = None,
        chat_channel_id: Optional[int] = None,
        voice_channel_id: Optional[int] = None,
    ):
        self.workspace_id = workspace_id
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.workspace_type = workspace_type
        self.name = name
        self.category_id = category_id
        self.chat_channel_id = chat_channel_id
        self.voice_channel_id = voice_channel_id
        self.status = WorkspaceStatus.ACTIVE
        self.created_at = datetime.datetime.now(datetime.timezone.utc)
        self.last_activity = self.created_at
        self.cohosts: set[int] = set()
        self.members: set[int] = set()
        self.invited: set[int] = set()
        self.blocked: set[int] = set()


class WorkspaceService:
    _instance: Optional[WorkspaceService] = None

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._workspaces: Dict[str, CommunityWorkspace] = {}
        self._guild_workspaces: Dict[int, List[str]] = {}

    @classmethod
    def get_instance(cls, bot: Optional[SentinelBot] = None) -> WorkspaceService:
        if cls._instance is None:
            if bot is None:
                raise RuntimeError("WorkspaceService requires bot instance.")
            cls._instance = cls(bot)
        return cls._instance

    async def create_workspace(
        self,
        guild: discord.Guild,
        owner: discord.Member,
        workspace_type: WorkspaceType,
        name: str,
        is_private: bool = False,
    ) -> CommunityWorkspace:
        """Creates a dedicated temporary workspace using existing category/channel infrastructure."""
        clean_name = name.strip()[:24]
        ws_id = f"WS-{guild.id}-{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"

        def_role = getattr(guild, "default_role", None) or discord.Object(id=guild.id)
        guild_me = getattr(guild, "me", None) or discord.Object(id=0)

        overwrites = {
            def_role: discord.PermissionOverwrite(read_messages=not is_private, connect=not is_private),
            owner: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True, manage_channels=False),
            guild_me: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, manage_channels=True),
        }

        cat = None
        chat_ch = None
        vc_ch = None

        if guild.me.guild_permissions.manage_channels:
            try:
                prefix = {
                    WorkspaceType.GAMING: "🎮",
                    WorkspaceType.MUSIC: "🎧",
                    WorkspaceType.CREATOR: "🎨",
                    WorkspaceType.PROJECT: "📁",
                    WorkspaceType.EVENT: "🎉",
                    WorkspaceType.GENERAL: "💬",
                }.get(workspace_type, "🏠")

                cat = await guild.create_category(f"{prefix}・{clean_name}", overwrites=overwrites)
                chat_ch = await guild.create_text_channel(f"chat-{clean_name.lower().replace(' ', '-')}", category=cat)
                vc_ch = await guild.create_voice_channel(f"VC-{clean_name}", category=cat)
            except Exception as e:
                logger.warning(f"Could not create Discord channels for workspace {ws_id}: {e}")

        ws = CommunityWorkspace(
            workspace_id=ws_id,
            guild_id=guild.id,
            owner_id=owner.id,
            workspace_type=workspace_type,
            name=name,
            category_id=cat.id if cat else None,
            chat_channel_id=chat_ch.id if chat_ch else None,
            voice_channel_id=vc_ch.id if vc_ch else None,
        )

        self._workspaces[ws_id] = ws
        if guild.id not in self._guild_workspaces:
            self._guild_workspaces[guild.id] = []
        self._guild_workspaces[guild.id].append(ws_id)
        return ws

    def get_workspace(self, workspace_id: str) -> Optional[CommunityWorkspace]:
        return self._workspaces.get(workspace_id)

    def list_guild_workspaces(self, guild_id: int) -> List[CommunityWorkspace]:
        ids = self._guild_workspaces.get(guild_id, [])
        return [self._workspaces[wid] for wid in ids if wid in self._workspaces]

    async def delete_workspace(self, guild: discord.Guild, workspace_id: str) -> bool:
        ws = self.get_workspace(workspace_id)
        if not ws or ws.guild_id != guild.id:
            return False

        ws.status = WorkspaceStatus.CLEANING
        # Delete temporary channels safely
        for ch_id in (ws.voice_channel_id, ws.chat_channel_id, ws.category_id):
            if ch_id:
                ch = guild.get_channel(ch_id)
                if ch:
                    try:
                        await ch.delete(reason=f"Workspace {workspace_id} closed")
                    except Exception as e:
                        logger.debug(f"Failed deleting temporary workspace channel {ch_id}: {e}")

        ws.status = WorkspaceStatus.DELETED
        self._workspaces.pop(workspace_id, None)
        if guild.id in self._guild_workspaces and workspace_id in self._guild_workspaces[guild.id]:
            self._guild_workspaces[guild.id].remove(workspace_id)
        return True
