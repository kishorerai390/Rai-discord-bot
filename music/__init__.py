"""
Music package for Rai.
Exports GuildMusicPlayer, BoundedMusicQueue, Track, AudioSourceResolver, and MusicIsolationManager.
"""

from music.queue import BoundedMusicQueue, Track
from music.source import AudioSourceResolver
from music.player import GuildMusicPlayer
from music.isolation import MusicIsolationManager
from music.playlists import PlaylistManager

__all__ = [
    "BoundedMusicQueue",
    "Track",
    "AudioSourceResolver",
    "GuildMusicPlayer",
    "MusicIsolationManager",
    "PlaylistManager",
]
