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

from __future__ import annotations

import re
import discord

from discord.ext import commands
from typing import TYPE_CHECKING, List, Callable

from .config import Config
from .utils import format_ms

if TYPE_CHECKING:
    from .player import Player
    from .objects import Track
    from .pool import NodePool
    
def ensure_track(func) -> Callable:
    def wrapper(self: PlayerPlaceholder, *args, **kwargs):
        current = self.get_current()
        if not current:
            return "None"
        return func(self, current, *args, **kwargs)
    return wrapper

class PlayerPlaceholder:
    def __init__(self, bot: commands.Bot, player: Player = None) -> None:
        self.bot: commands.Bot = bot
        self.player: Player = player

        self.variables = {
            "channel_name": self.channel_name,
            "track_name": self.track_name,
            "track_url": self.track_url,
            "track_author": self.track_author,
            "track_duration": self.track_duration,
            "track_thumbnail": self.track_thumbnail,
            "track_color": self.track_color,
            "track_requester_id": self.track_requester_id,
            "track_requester_name": self.track_requester_name,
            "track_requester_mention": self.track_requester_mention,
            "track_requester_avatar": self.track_requester_avatar,
            "track_source_name": self.track_source_name,
            "track_source_emoji": self.track_source_emoji,
            "queue_length": self.queue_length,
            "volume": self.volume,
            "dj": self.dj,
            "loop_mode": self.loop_mode,
            "default_embed_color": self.default_embed_color,
            "bot_icon": self.bot_icon,
            "server_invite_link": Config().invite_link,
            "invite_link": f"https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&permissions=2184260928&scope=bot%20applications.commands"
        }

        self.regexes = {
            "@@t_(.*?)@@": self.translation
        }
        
    def get_current(self) -> Track:
        return self.player.current if self.player else None

    def channel_name(self) -> str:
        if not self.player:
            return "None"
        return self.player.channel.name if self.player.channel else "None"
    
    @ensure_track
    def track_name(self, track: Track) -> str:
        return track.title

    @ensure_track
    def track_url(self, track: Track) -> str:
        return track.uri
    
    @ensure_track
    def track_author(self, track: Track) -> str:
        return track.author

    @ensure_track
    def track_duration(self, track: Track) -> str:
        return self.player.get_msg("common.status.live") if track.is_stream else format_ms(track.length)
    
    @ensure_track
    def track_requester_id(self, track: Track) -> str:
        return str(track.requester.id if track.requester else self.bot.user.id)
    
    @ensure_track
    def track_requester_name(self, track: Track) -> str:
        return track.requester.name if track.requester else self.bot.user.display_name
    
    @ensure_track
    def track_requester_mention(self, track: Track) -> str:
        return f"<@{track.requester.id if track.requester else self.bot.user.id}>"
    
    @ensure_track
    def track_requester_avatar(self, track: Track) -> str:
        return track.requester.display_avatar.url if track.requester else self.bot.user.display_avatar.url
    
    @ensure_track
    def track_color(self, track: Track) -> int:
        try:
            color = Config().get_source_config(track.source, "color")
            return int(color, 16) if color else Config().embed_color
        except Exception:
            return Config().embed_color
    
    @ensure_track
    def track_source_name(self, track: Track) -> str:
        return track.source
    
    @ensure_track
    def track_source_emoji(self, track: Track) -> str:
        return track.emoji
    
    def track_thumbnail(self) -> str:
        if not self.player or not self.player.current:
            return (self.bot.user.display_avatar.url if self.bot and self.bot.user else "https://rai-discord-bot.onrender.com/public/rem_avatar_static.png")
        
        return self.player.current.thumbnail or "https://cdn.discordapp.com/attachments/674788144931012638/823086668445384704/eq-dribbble.gif"

    def queue_length(self) -> str:
        return str(self.player.queue.count) if self.player else "0"
    
    def dj(self) -> str:
        if not self.player:
            return self.bot.user.mention if self.bot and self.bot.user else "DJ"
        
        if dj_id := self.player.settings.get("dj"):
            return f"<@&{dj_id}>"
        
        if hasattr(self.player, "dj") and self.player.dj:
            return self.player.dj.mention
        return self.bot.user.mention if self.bot and self.bot.user else "DJ"

    def volume(self) -> int:
        return self.player.volume if self.player else 0

    def loop_mode(self) -> str:
        return self.player.queue.repeat if self.player else "Off"

    def default_embed_color(self) -> int:
        return Config().embed_color

    def bot_icon(self) -> str:
        return (self.bot.user.display_avatar.url if self.bot and self.bot.user else "https://rai-discord-bot.onrender.com/public/rem_avatar_static.png")
    
    def translation(self, text: str) -> str:
        return self.player.get_msg(text)
        
    def replace(self, text: str, variables: dict[str, str]) -> str:
        if not text or text.isspace(): return

        matches: list[str] = re.findall(r"\{\{(.*?)\}\}", text)

        for match in matches:
            parts: list[str] = match.split("??")
            expression = parts[0].strip()
            true_value, false_value = "", ""

            # Split the true and false values
            if "//" in parts[1]:
                true_value, false_value = [part.strip() for part in parts[1].split("//")]
            else:
                true_value = parts[1].strip()

            try:
                # Replace variable placeholders with their values
                expression = re.sub(r'@@(.*?)@@', lambda x: "'" + variables.get(x.group(1), '') + "'", expression)
                expression = re.sub(r"'(\d+)'", lambda x: str(int(x.group(1))), expression)
                expression = re.sub(r"'(\d+)'\s*([><=!]+)\s*(\d+)", lambda x: f"{int(x.group(1))} {x.group(2)} {int(x.group(3))}", expression)

                # Evaluate the expression
                result = eval(expression, {"__builtins__": None}, variables)

                # Replace the match with the true or false value based on the result
                replacement = true_value if result else false_value
                text = text.replace("{{" + match + "}}", replacement)

            except:
                text = text.replace("{{" + match + "}}", "")

        for regex_pattern, func in self.regexes.items():
            text = re.sub(regex_pattern, lambda m: func(m.group(1)), text)
        text = re.sub(r'@@(.*?)@@', lambda x: str(variables.get(x.group(1), '')), text)
        return text
    
    @classmethod
    def build_embed(cls, embed_form: dict[str, dict], placeholder: PlayerPlaceholder) -> discord.Embed:
        embed = discord.Embed()
        if not embed_form or not isinstance(embed_form, dict):
            return embed

        try:
            rv = {}
            if placeholder and hasattr(placeholder, "variables"):
                for key, func in placeholder.variables.items():
                    try:
                        rv[key] = func() if callable(func) else func
                    except Exception:
                        rv[key] = ""

            if author := embed_form.get("author"):
                name = placeholder.replace(author.get("name"), rv) if author.get("name") else None
                url = placeholder.replace(author.get("url"), rv) if author.get("url") else None
                icon_url = placeholder.replace(author.get("icon_url"), rv) if author.get("icon_url") else None
                if name:
                    embed.set_author(name=name, url=url, icon_url=icon_url)
            
            if title := embed_form.get("title"):
                name = placeholder.replace(title.get("name"), rv) if title.get("name") else None
                url = placeholder.replace(title.get("url"), rv) if title.get("url") else None
                if name:
                    embed.title = name
                    embed.url = url

            if fields := embed_form.get("fields", []):
                for f in fields:
                    f_name = placeholder.replace(f.get("name"), rv) if f.get("name") else None
                    f_val = placeholder.replace(f.get("value", ""), rv) if f.get("value") else None
                    if f_name and f_val:
                        embed.add_field(name=f_name, value=f_val, inline=f.get("inline", False))

            if footer := embed_form.get("footer"):
                f_text = placeholder.replace(footer.get("text"), rv) if footer.get("text") else None
                f_icon = placeholder.replace(footer.get("icon_url"), rv) if footer.get("icon_url") else None
                if f_text:
                    embed.set_footer(text=f_text, icon_url=f_icon) 

            if thumbnail := embed_form.get("thumbnail"):
                t_url = placeholder.replace(thumbnail, rv)
                if t_url:
                    embed.set_thumbnail(url=t_url)
            
            if image := embed_form.get("image"):
                i_url = placeholder.replace(image, rv)
                if i_url:
                    embed.set_image(url=i_url)

            if desc := embed_form.get("description"):
                embed.description = placeholder.replace(desc, rv)

            if color_val := embed_form.get("color"):
                parsed_color = placeholder.replace(str(color_val), rv)
                try:
                    embed.color = int(parsed_color)
                except (ValueError, TypeError):
                    embed.color = Config().embed_color
            else:
                embed.color = Config().embed_color

        except Exception:
            pass

        return embed

class BotPlaceholder:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.variables = {
            "guilds": self.guilds_count,
            "users": self.users_count,
            "players": self.players_count,
            "nodes": self.nodes_count
        }
    
    def guilds_count(self) -> int:
        return len(self.bot.guilds)
    
    def users_count(self) -> int:
        return len(self.bot.users)
    
    def players_count(self) -> int:
        count = 0
        for node in NodePool._nodes.values():
            count += len(node._players)

        return count
    
    def nodes_count(self):
        return len(NodePool._nodes)
    
    def replace(self, msg: str) -> str:
        keys: List[str] = re.findall(r'@@(.*?)@@', msg)

        for key in keys:
            value = self.variables.get(key.lower(), None)
            if value:
                msg = msg.replace(f"@@{key}@@", str(value()))

        return msg