"""MIT License

Copyright (c) 2023 - present Vocard Development
"""

__title__ = "voicelink"
__author__ = "ChocoMeow"
__license__ = "MIT"
__copyright__ = "Copyright 2023-present Vocard Development"
__version__ = "1.0.0"

from .config import Config
from .language import LangHandler
from .mongodb import MongoDBHandler
from .exceptions import VoicelinkException
from .enums import *
from .filters import Filters
from .objects import *
from .pool import Node, NodePool
from .queue import Queue
from .player import Player
from .placeholders import BotPlaceholder, PlayerPlaceholder
from .lyrics import LYRICS_PLATFORMS
from .ipc import IPCClient
