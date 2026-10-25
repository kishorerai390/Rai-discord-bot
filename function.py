"""MIT License

Copyright (c) 2023 - present MusicMaid Development

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import json
import os
import logging
import voicelink

from discord.ext import commands
from typing import Optional, Any

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

logger: logging.Logger = logging.getLogger("musicmaid")

def _clean_str(val: Any) -> str:
    if not val:
        return ""
    v = str(val).strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()
    return v

def resolve_token() -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    for key in ["MUSIC_BOT_TOKEN", "DISCORD_TOKEN", "NEKO_SONGS_BOT_TOKEN", "BOT_TOKEN", "TOKEN", "DISCORD_BOT_TOKEN", "MAIN_RAI_BOT_TOKEN"]:
        t = _clean_str(os.getenv(key))
        if len(t) > 20:
            return t
    return ""

def ensure_settings() -> dict:
    settings_file = os.path.join(ROOT_DIR, "settings.json")
    s = {}
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            s = {}

    changed = False
    token = resolve_token() or _clean_str(s.get("token"))
    if token and s.get("token") != token:
        s["token"] = token
        changed = True

    try:
        client_id = int(os.getenv("DISCORD_CLIENT_ID") or os.getenv("CLIENT_ID") or s.get("client_id") or 1556676516274905218)
    except Exception:
        client_id = 1556676516274905218
    if s.get("client_id") != client_id:
        s["client_id"] = client_id
        changed = True

    mongodb_url = os.getenv("MONGODB_URL") or s.get("mongodb_url") or "mongodb+srv://kishorerai390_db_user:MusicMaid1@musicmaid.8gj5cff.mongodb.net/?retryWrites=true&w=majority"
    if s.get("mongodb_url") != mongodb_url:
        s["mongodb_url"] = mongodb_url
        changed = True

    mongodb_name = os.getenv("MONGODB_NAME") or s.get("mongodb_name") or "MusicMaid"
    if s.get("mongodb_name") != mongodb_name:
        s["mongodb_name"] = mongodb_name
        changed = True

    desired_nodes = {
        "SERENETIA_V4": {
            "host": "lavalinkv4.serenetia.com",
            "port": 443,
            "password": "https://seretia.link/discord",
            "secure": True,
            "identifier": "SERENETIA_V4"
        },
        "MILLOHOST_V4": {
            "host": "lava-v4.millohost.my.id",
            "port": 443,
            "password": "https://discord.gg/mjS5J2K3ep",
            "secure": True,
            "identifier": "MILLOHOST_V4"
        },
        "LOCAL_LAVALINK": {
            "host": "127.0.0.1",
            "port": 2333,
            "password": "youshallnotpass",
            "secure": False,
            "identifier": "LOCAL_LAVALINK"
        }
    }
    if s.get("nodes") != desired_nodes:
        s["nodes"] = desired_nodes
        changed = True

    defaults = {
        "prefix": "?",
        "activity": [{"type": "listening", "name": "/help", "status": "online"}],
        "logging": {"file": {"path": "./logs", "enable": True}, "level": {"discord": "INFO", "musicmaid": "INFO", "ipc_client": "INFO"}, "max_history": 30},
        "bot_access_user": [],
        "embed_color": "0xa855f7",
        "default_max_queue": 1000,
        "default_search_platform": "youtube",
        "lyrics_platform": "lrclib",
        "ipc_client": {"host": "127.0.0.1", "port": 8000, "password": "YOUR_PASSWORD", "secure": False, "enable": False},
        "timer_settings": {"bot_activity_update": 600, "inactive_player_cleanup": 600, "cache_cleanup": 43200},
        "playlist_settings": {"max_playlists": 5, "max_tracks_per_playlist": 500, "default_playlist_name": "Favourite"},
        "sources_settings": {
            "youtube": {"emoji": "🔴", "color": "0xff0000"},
            "spotify": {"emoji": "🟢", "color": "0x1db954"},
            "soundcloud": {"emoji": "🟠", "color": "0xff5500"}
        },
        "cooldowns_settings": {}
    }
    for k, v in defaults.items():
        if k not in s:
            s[k] = v
            changed = True

    if not os.path.exists(settings_file) or changed:
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=4)
    return s

ensure_settings()

def open_json(path: str) -> dict:
    try:
        with open(os.path.join(ROOT_DIR, path), encoding="utf8") as json_file:
            return json.load(json_file)
    except:
        return {}

def update_json(path: str, new_data: dict) -> None:
    data = open_json(path)
    if not data:
        data = new_data
    else:
        data.update(new_data)

    with open(os.path.join(ROOT_DIR, path), "w") as json_file:
        json.dump(data, json_file, indent=4)

def cooldown_check(ctx: commands.Context) -> Optional[commands.Cooldown]:
    if ctx.author.id in voicelink.Config().bot_access_user:
        return None
    cooldown = voicelink.Config().cooldowns_settings.get(f"{ctx.command.parent.qualified_name} {ctx.command.name}" if ctx.command.parent else ctx.command.name)
    if not cooldown:
        return None
    return commands.Cooldown(cooldown[0], cooldown[1])

def get_aliases(name: str) -> list:
    return voicelink.Config().aliases_settings.get(name, [])