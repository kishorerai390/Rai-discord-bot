"""web/routes/commands.py — Commands reference page."""

from dataclasses import dataclass, field
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@dataclass
class Command:
    name: str
    description: str
    usage: str = ""
    aliases: list[str] = field(default_factory=list)
    cooldown: int = 0
    permissions: str = ""
    examples: list[str] = field(default_factory=list)
    new: bool = False
    premium: bool = False


@dataclass
class Category:
    id: str
    name: str
    description: str
    icon: str
    color: str
    commands: list[Command] = field(default_factory=list)


# ── Command registry ───────────────────────────────────────────────
# Replace / extend with your actual bot command list
CATEGORIES: list[Category] = [
    Category(
        id="playback", name="Playback", icon="fa-play",
        color="green",
        description="Play, pause, skip, and control music playback",
        commands=[
            Command("play",   "Play a song or playlist from a URL or search query.",
                    usage="/play <query or URL>", aliases=["p"], cooldown=2,
                    examples=["/play Blinding Lights", "/play https://open.spotify.com/track/..."]),
            Command("pause",  "Pause the currently playing track.",
                    usage="/pause", aliases=["pa"], cooldown=1),
            Command("resume", "Resume the paused track.",
                    usage="/resume", aliases=["r"], cooldown=1),
            Command("stop",   "Stop playback and clear the queue.",
                    usage="/stop", aliases=["s", "dc"], cooldown=2),
            Command("skip",   "Skip the current track.",
                    usage="/skip [amount]", aliases=["sk", "next"], cooldown=1,
                    examples=["/skip", "/skip 3"]),
            Command("seek",   "Seek to a specific position in the track.",
                    usage="/seek <time>", cooldown=2,
                    examples=["/seek 1:30", "/seek 90"]),
            Command("replay", "Restart the current track from the beginning.",
                    usage="/replay", cooldown=2),
            Command("forward","Fast-forward by a given number of seconds.",
                    usage="/forward <seconds>", cooldown=1,
                    examples=["/forward 30"]),
            Command("rewind", "Rewind by a given number of seconds.",
                    usage="/rewind <seconds>", cooldown=1,
                    examples=["/rewind 15"]),
        ],
    ),
    Category(
        id="queue", name="Queue", icon="fa-list",
        color="blue",
        description="Manage the music queue",
        commands=[
            Command("queue",    "Display the current queue.",
                    usage="/queue [page]", aliases=["q"], cooldown=2),
            Command("shuffle",  "Shuffle the queue randomly.",
                    usage="/shuffle", aliases=["sh"], cooldown=2),
            Command("loop",     "Toggle loop mode (track / queue / off).",
                    usage="/loop [mode]", aliases=["l", "repeat"], cooldown=1,
                    examples=["/loop", "/loop track", "/loop queue"]),
            Command("remove",   "Remove a track from the queue by position.",
                    usage="/remove <position>", cooldown=1,
                    examples=["/remove 3"]),
            Command("move",     "Move a track to a different position.",
                    usage="/move <from> <to>", cooldown=1,
                    examples=["/move 2 5"]),
            Command("clear",    "Clear all tracks from the queue.",
                    usage="/clear", aliases=["cls"], cooldown=2, permissions="DJ"),
            Command("skipto",   "Skip to a specific position in the queue.",
                    usage="/skipto <position>", cooldown=1,
                    examples=["/skipto 5"]),
            Command("autoplay", "Enable/disable autoplay when queue ends.",
                    usage="/autoplay", new=True),
        ],
    ),
    Category(
        id="filters", name="Filters", icon="fa-sliders",
        color="purple",
        description="Apply audio filters to the current track",
        commands=[
            Command("filter",     "Apply or remove an audio filter.",
                    usage="/filter <name>", cooldown=3,
                    examples=["/filter bass_boost", "/filter nightcore"]),
            Command("bassboost",  "Toggle bass boost filter.",
                    usage="/bassboost [level]", aliases=["bass"], cooldown=3),
            Command("nightcore",  "Toggle nightcore (speed+pitch up) filter.",
                    usage="/nightcore", cooldown=3),
            Command("vaporwave",  "Toggle vaporwave (slow+reverb) filter.",
                    usage="/vaporwave", cooldown=3),
            Command("8d",         "Toggle 8D audio (rotating stereo) filter.",
                    usage="/8d", cooldown=3),
            Command("karaoke",    "Toggle karaoke (vocal remover) filter.",
                    usage="/karaoke", cooldown=3),
            Command("treble",     "Toggle treble boost filter.",
                    usage="/treble", cooldown=3),
            Command("equalizer",  "Open the equalizer settings.",
                    usage="/equalizer", aliases=["eq"], cooldown=2, new=True),
        ],
    ),
    Category(
        id="info", name="Info", icon="fa-circle-info",
        color="cyan",
        description="Get information about tracks and the bot",
        commands=[
            Command("nowplaying", "Show details about the current track.",
                    usage="/nowplaying", aliases=["np", "current"], cooldown=2),
            Command("lyrics",     "Fetch lyrics for the current track.",
                    usage="/lyrics [song]", aliases=["ly"], cooldown=5,
                    examples=["/lyrics", "/lyrics Blinding Lights The Weeknd"]),
            Command("history",    "Show recently played tracks.",
                    usage="/history", cooldown=3),
            Command("search",     "Search for a track and pick from results.",
                    usage="/search <query>", aliases=["find"], cooldown=3),
        ],
    ),
    Category(
        id="settings", name="Settings", icon="fa-gear",
        color="orange",
        description="Configure Voicelink for your server",
        commands=[
            Command("volume",       "Set the playback volume (0–100).",
                    usage="/volume <level>", aliases=["vol"], cooldown=1,
                    examples=["/volume 80"]),
            Command("prefix",       "Change the bot prefix (legacy).",
                    usage="/prefix <prefix>", cooldown=5, permissions="Administrator"),
            Command("djrole",       "Set or clear the DJ role.",
                    usage="/djrole [role]", cooldown=5, permissions="Administrator",
                    examples=["/djrole @DJ"]),
            Command("channel",      "Lock the bot to a specific text channel.",
                    usage="/channel [channel]", cooldown=5, permissions="Administrator"),
            Command("voteskip",     "Configure vote-skip threshold.",
                    usage="/voteskip <percentage>", cooldown=5, permissions="Administrator"),
            Command("defaultvolume","Set the default volume for new sessions.",
                    usage="/defaultvolume <level>", cooldown=5, permissions="Administrator"),
        ],
    ),
    Category(
        id="playlist", name="Playlists", icon="fa-bookmark",
        color="pink",
        description="Save and load personal playlists",
        commands=[
            Command("playlist create", "Create a new personal playlist.",
                    usage="/playlist create <name>", cooldown=3),
            Command("playlist add",    "Add the current track to a playlist.",
                    usage="/playlist add <name>", cooldown=2),
            Command("playlist load",   "Load a playlist into the queue.",
                    usage="/playlist load <name>", cooldown=3),
            Command("playlist list",   "List your saved playlists.",
                    usage="/playlist list", cooldown=2),
            Command("playlist delete", "Delete a playlist.",
                    usage="/playlist delete <name>", cooldown=3),
            Command("playlist view",   "View tracks in a playlist.",
                    usage="/playlist view <name>", cooldown=2),
        ],
    ),
]

FLAT_COMMANDS = [cmd for cat in CATEGORIES for cmd in cat.commands]


@router.get("/commands", response_class=HTMLResponse)
async def commands_page(request: Request):
    templates = request.app.state.templates
    ctx = request.app.state.base_context(request)
    ctx["categories"] = CATEGORIES
    ctx["commands"] = FLAT_COMMANDS
    return templates.TemplateResponse("commands.html", ctx)

