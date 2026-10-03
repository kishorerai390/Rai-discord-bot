"""
Concrete Music Providers for RAI.
"""

from music.providers.youtube import YouTubeMusicProvider
from music.providers.soundcloud import SoundCloudMusicProvider
from music.providers.direct import DirectAudioProvider

__all__ = [
    "YouTubeMusicProvider",
    "SoundCloudMusicProvider",
    "DirectAudioProvider",
]
