"""MIT License

Copyright (c) 2023 - present MusicMaid Development
"""

__title__ = "voicelink"
__author__ = "ChocoMeow"
__license__ = "MIT"
__copyright__ = "Copyright 2023-present MusicMaid Development"
__version__ = "1.0.0"

from .config import Config
from .language import LangHandler
from .mongodb import MongoDBHandler
from .exceptions import *
from .enums import *
from .filters import Filters
from .objects import *
from .pool import Node, NodePool
from .queue import Queue, QUEUE_TYPES
from .player import Player, connect_channel
from .placeholders import BotPlaceholder, PlayerPlaceholder
from .lyrics import LYRICS_PLATFORMS
from .ipc import IPCClient
from . import pool
from . import queue
from . import player
from . import utils
