"""
Music Commands module for Rai.
Bridges modular music player interfaces and discord slash commands.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)

# Expose MusicCog from cogs.music for architectural modularity
try:
    from cogs.music import MusicCog, Song, MusicControlView
    MusicCommands = MusicCog
except ImportError:
    MusicCog = None
    Song = None
    MusicControlView = None
    MusicCommands = None

__all__ = [
    "MusicCommands",
    "MusicCog",
    "Song",
    "MusicControlView",
]
