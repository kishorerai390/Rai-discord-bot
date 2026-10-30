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

import time, logging, asyncio

from math import ceil
from random import shuffle, choice
from typing import Any, Dict, List, Optional, Union, Tuple, TYPE_CHECKING

from discord import (
    Client,
    Guild,
    VoiceChannel,
    VoiceProtocol,
    Member,
    Message,
    PartialMessage,
    Interaction,
    errors,
    ChannelType
)

from discord.ext import commands

from . import events
from .config import Config
from .pool import Node, NodePool
from .objects import Track, Playlist
from .filters import Filter, Filters
from .enums import SearchType, LoopType, RequestMethod
from .events import VoicelinkEvent, TrackEndEvent, TrackStartEvent, TrackExceptionEvent
from .exceptions import VoicelinkException, FilterInvalidArgument, TrackInvalidPosition, FilterTagAlreadyInUse, DuplicateTrack
from .placeholders import PlayerPlaceholder
from .queue import Queue, QUEUE_TYPES
from .mongodb import MongoDBHandler
from .language import LangHandler
from .views import InteractiveController
from .utils import format_ms, dispatch_message

if TYPE_CHECKING:
    from .ipc import IPCClient

def _resolve_requested_voice_channel(
    ctx: Union[commands.Context, Interaction],
    channel: Optional[VoiceChannel] = None
) -> Optional[VoiceChannel]:
    if channel is not None:
        return channel
    voice_state = getattr(ctx, "author", None)
    if voice_state is not None:
        voice_state = getattr(voice_state, "voice", None)
    else:
        user = getattr(ctx, "user", None)
        voice_state = getattr(user, "voice", None) if user else None

    return getattr(voice_state, "channel", None) if voice_state else None


async def connect_channel(ctx: Union[commands.Context, Interaction], channel: VoiceChannel = None):
    texts = await LangHandler.get_lang(ctx.guild.id, "voice.connection.noChannel", "voice.connection.noPermission")
    channel = _resolve_requested_voice_channel(ctx, channel)
    if not channel:
        raise VoicelinkException(texts[0])

    check = channel.permissions_for(ctx.guild.me)
    if check.connect == False or check.speak == False:
        raise VoicelinkException(texts[1])

    settings = await MongoDBHandler.get_settings(channel.guild.id)
    player: Player = await channel.connect(
        cls=Player(
            ctx.bot if isinstance(ctx, commands.Context) else ctx.client,
            channel, ctx, settings
        ))

    if player.volume != 100:
        await player.set_volume(player.volume)

    if player.is_ipc_connected:
        await player.send_ws({"op": "createPlayer", "memberIds": [str(member.id) for member in channel.members]})

    return player

DEFAULT_CONTROLLER = {
    "embeds": {
        "active": {
            "title": {
                "name": "🎵 Now Playing in @@channel_name@@",
                "url": "@@track_url@@"
            },
            "description": "### [@@track_name@@](@@track_url@@)\n> 👤 **Artist:** `@@track_author@@`\n> 🎧 **Requester:** @@track_requester_mention@@\n> 🎚️ **Volume:** `@@volume@@%` • 🔁 **Loop:** `@@loop_mode@@`",
            "thumbnail": "@@track_thumbnail@@",
            "footer": {
                "text": "Queue: @@queue_length@@ tracks • Rem 🎧💜",
                "icon_url": "https://rai-discord-bot.onrender.com/public/rem_avatar_static.png"
            }
        },
        "inactive": {
            "title": {
                "name": "💜 Rem — Your Anime Music Companion",
                "url": "https://rai-discord-bot.onrender.com"
            },
            "description": "### Ready for music! (•ᴗ•) 🌸\nJoin a voice channel and type `/play <song name or link>` to stream with Rem!",
            "thumbnail": "https://rai-discord-bot.onrender.com/public/rem_avatar_static.png",
            "footer": {
                "text": "Rem 🎧💜 • Your Anime Music Companion",
                "icon_url": "@@bot_icon@@"
            }
        }
    }
}

class Player(VoiceProtocol):
    """The base player class for Voicelink.
       In order to initiate a player, you must pass it in as a cls when you connect to a channel.
       i.e: ```py
       await ctx.author.voice.channel.connect(cls=voicelink.Player)
       ```
    """

    def __call__(self, client: Client, channel: VoiceChannel):
        self.client: Client = client
        self.channel: VoiceChannel = channel

        return self

    def __init__(
        self, 
        client: Optional[Client] = None, 
        channel: Optional[VoiceChannel] = None, 
        ctx: Union[commands.Context, Interaction] = None,
        settings: dict[str, Any] = None
    ):
        self.client: Client = client
        self._bot: Client = client
        self._ipc_client: IPCClient = self._bot.ipc_client
        self._ipc_connection: bool = False
        
        self.context = ctx
        self.dj: Member = ctx.user if isinstance(ctx, Interaction) else ctx.author
        self.channel: VoiceChannel = channel
        self._guild = channel.guild if channel else None

        self.settings: dict = settings
        self.joinTime: float = round(time.time())
        self._volume: int = self.settings.get('volume', 100)
        self.queue: Queue = QUEUE_TYPES.get(self.settings.get("queue_type", "queue").lower())(
            self.settings.get("max_queue", Config().max_queue),
            self.settings.get("duplicate_track", True), self.get_msg
        )

        self._node = NodePool.get_node()
        self._current: Optional[Track] = None
        self._filters: Filters = Filters()
        self._paused: bool = False
        self._is_connected: bool = False
        self._ping: float = 0.0
        self._track_is_stuck = False

        self._position: int = 0
        self._last_position: int = 0
        self._last_update: int = 0
        self._ending_track: Optional[Track] = None

        self._voice_state: dict = {}

        self.controller: Union[Message, PartialMessage] = None
        self._updating: bool = False
        self._pending_controller_track = None
        self._pending_controller_repost: bool = False

        self.pause_votes = set()
        self.resume_votes = set()
        self.skip_votes = set()
        self.previous_votes = set()
        self.shuffle_votes = set()
        self.stop_votes = set()

        self._ph = PlayerPlaceholder(client, self)
        self._logger: Optional[logging.Logger] = self._node._logger
        self._inactive_cleanup_task: Optional[asyncio.Task[None]] = None

    def __repr__(self):
        return (
            f"<Voicelink.player bot={self.bot} guildId={self.guild.id} "
            f"is_connected={self.is_connected} is_playing={self.is_playing}>"
        )

    @property
    def position(self) -> float:
        """Property which returns the player's position in a track in milliseconds"""
        if not self.is_playing or not self._current:
            return 0

        if self.is_paused:
            return min(self._last_position, self._current.length)

        difference = (time.time() * 1000) - self._last_update
        position = self._last_position + difference

        if position > self._current.length:
            return 0

        return min(position, self._current.length)

    @property
    def is_playing(self) -> bool:
        """Property which returns whether or not the player is actively playing a track."""
        return self._is_connected and self._current is not None

    @property
    def is_connected(self) -> bool:
        """Property which returns whether or not the player is connected"""
        return self._is_connected

    @property
    def is_paused(self) -> bool:
        """Property which returns whether or not the player has a track which is paused or not."""
        return self._is_connected and self._paused

    @property
    def current(self) -> Optional[Track]:
        """Property which returns the currently playing track"""
        return self._current

    @property
    def node(self) -> Node:
        """Property which returns the node the player is connected to"""
        return self._node

    @property
    def guild(self) -> Guild:
        """Property which returns the guild associated with the player"""
        return self._guild

    @property
    def volume(self) -> int:
        """Property which returns the players current volume"""
        return self._volume

    @property
    def filters(self) -> Filters:
        """Property which returns the helper class for interacting with filters"""
        return self._filters

    @property
    def bot(self) -> Client:
        """Property which returns the bot associated with this player instance"""
        return self._bot

    @property
    def is_dead(self) -> bool:
        """Returns a bool representing whether the player is dead or not.
           A player is considered dead if it has been destroyed and removed from stored players.
        """
        return self.guild.id not in self._node._players

    @property
    def ping(self) -> float:
        """Calculates and returns the player's current ping in seconds."""
        return round(self._ping / 1000, 2)
    
    @property
    def autoplay(self) -> bool:
        """Indicates whether the player is set to autoplay."""
        return self.settings.get("autoplay", False)
    
    @property
    def data(self) -> dict:
        """Returns a dictionary containing the player's data."""
        return {
            "guild_id": self._guild.id,
            "channel_id": self.channel.id,
            "queue": {
                "tracks": [track.data for track in self.queue._queue],
                "position": self.queue._position,
                "repeat_mode": self.queue._repeat.current.name,
                "repeat_position": self.queue._repeat_position
            },
            "dj": self.dj.id,
            "is_paused": self.is_paused,
            "position": self.position,
            "autoplay": self.autoplay
        }
    
    @property
    def is_ipc_connected(self) -> bool:
        """Indicates whether the Inter-Process Communication (IPC) connection is active."""
        return self._ipc_client._is_connected and self._ipc_connection
        
    def get_msg(self, *keys) -> Union[list[str], str]:
        """Retrieves a localized message or list of messages based on the given keys
           for the guild associated with this player.
        """
        return LangHandler._get_lang(self.settings.get("lang"), *keys)

    def required(self, leave: bool = False):
        """
        Calculates the number of votes required for a specific action in the voice channel.

        If `leave` is True and the channel has three members, the requirement adjusts to 2 votes.
        """
        if self.settings.get('disabled_vote'):
            return 0

        required = ceil((len(self.channel.members) - 1) / 2.5)
        if leave:
            required += 1
        
        return required
    
    def is_user_join(self, user: Member):
        """Checks if a user is present in the voice channel or has 'Manage Server' permission."""
        if not self.channel:
            return bool(user.guild_permissions.manage_guild)
        if user not in self.channel.members:
            if not user.guild_permissions.manage_guild:
                return False        
        return True
    
    def is_privileged(self, user: Member, check_user_join: bool = True) -> bool:
        """
        Determines if a user has privileged access.

        Privileged access is granted if the user is in the bot access list, 
        has 'Manage Server' permission, or meets the DJ role criteria in the settings.
        Raises an exception if `check_user_join` is True and the user is not in the channel.
        """
        if user.id in Config().bot_access_user:
            return True
        
        manage_perm = user.guild_permissions.manage_guild
        if check_user_join and not self.is_user_join(user):
            raise VoicelinkException(self.get_msg('voice.connection.notInChannel').format(user.mention, self.channel.mention))
            
        if 'dj' in self.settings and self.settings['dj']:
            return manage_perm or (self.settings['dj'] in [role.id for role in user.roles])
        return self.dj.id == user.id or manage_perm
    
    def build_embed(self, current_track: Track = None):
        """Builds an embed based on the current track state."""
        ctrl = self.settings.get("default_controller") or Config().controller or DEFAULT_CONTROLLER
        if not isinstance(ctrl, dict) or not ctrl.get("embeds"):
            ctrl = DEFAULT_CONTROLLER
        
        embeds = ctrl.get("embeds") or DEFAULT_CONTROLLER["embeds"]
        mode = "active" if current_track else "inactive"
        embed_form = embeds.get(mode) or DEFAULT_CONTROLLER["embeds"][mode]
        
        embed = PlayerPlaceholder.build_embed(embed_form, self._ph)
        if not embed.title and not embed.description:
            if current_track:
                embed.title = f"🎵 Now Playing: {current_track.title[:100]}"
                embed.description = f"**Artist:** `{current_track.author}` • **Duration:** `{current_track.formatted_length}`"
            else:
                embed.title = "💜 Rem — Your Anime Music Companion"
                embed.description = "Ready to play! (•ᴗ•) Connect to a voice channel and use `/play`."
        if not embed.color:
            embed.color = Config().embed_color

        # Authoritatively enforce the live Rem bot avatar for controller branding
        bot_avatar = self.bot.user.display_avatar.url if self.bot and self.bot.user else "https://rai-discord-bot.onrender.com/public/rem_avatar_static.png"
        if not current_track:
            embed.set_thumbnail(url=bot_avatar)
            if embed.footer:
                embed.set_footer(text=embed.footer.text, icon_url=bot_avatar)
        else:
            if not embed.thumbnail or not embed.thumbnail.url or 'dIFBwU7' in str(embed.thumbnail.url):
                embed.set_thumbnail(url=bot_avatar)
            if embed.footer and (not embed.footer.icon_url or 'dIFBwU7' in str(embed.footer.icon_url)):
                embed.set_footer(text=embed.footer.text, icon_url=bot_avatar)

        return embed

    async def send(self, method: RequestMethod, query: str = None, data: Union[Dict, str] = {}) -> Dict:
        """Sends an HTTP request to the node with the given method, query, and data."""
        uri: str = f"sessions/{self._node._session_id}/players/{self._guild.id}" + (f"?{query}" if query else "")
        return await self._node.send(method, query=uri, data=data)
        
    async def _update_state(self, data: dict) -> None:
        """Updates the player's state based on the provided data."""
        state: dict = data.get("state")
        self._last_update = time.time() * 1000
        self._is_connected = state.get("connected")
        self._last_position = state.get("position")
        self._ping = state.get("ping")
        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) update state with data {data}")

        if self.is_ipc_connected:
            await self.send_ws({
                "op": "playerUpdate",
                "lastUpdate": self._last_update,
                "isConnected": self._is_connected,
                "lastPosition": self._last_position
            })

    async def _dispatch_voice_update(self, voice_data: Dict[str, Any] = None):
        """Dispatches a voice update to the node."""
        state = voice_data or self._voice_state
        session_id = state.get("sessionId")
        event = state.get("event")
        if not session_id or not event:
            return

        token = event.get("token")
        endpoint = event.get("endpoint")
        if not token or not endpoint:
            return

        channel_id = str(self.channel.id) if self.channel else (str(self.guild.me.voice.channel.id) if self.guild.me and self.guild.me.voice and self.guild.me.voice.channel else None)
        data = {
            "token": token,
            "endpoint": endpoint,
            "sessionId": session_id,
        }
        if channel_id:
            data["channelId"] = channel_id
        
        await self.send(method=RequestMethod.PATCH, data={"voice": data})
        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) dispatched voice update to {endpoint}")

    async def on_voice_server_update(self, data: dict):
        """Handles a voice server update event."""
        self._voice_state["event"] = data
        await self._dispatch_voice_update()

    async def on_voice_state_update(self, data: dict):
        """Handles a voice state update event."""
        if not (channel_id := data.get("channel_id")):
            await self.teardown()
            self._voice_state.clear()
            return

        self.channel = self.guild.get_channel(int(channel_id))
        if session_id := data.get("session_id"):
            self._voice_state["sessionId"] = session_id
        await self._dispatch_voice_update()

    async def _dispatch_event(self, data: dict):
        """Dispatches an event based on the type of event data received."""
        event_type = data.get("type")
        event: VoicelinkEvent = getattr(events, event_type)(data, self)

        if isinstance(event, TrackEndEvent) and event.reason != "replaced":
            self._current = None
        
        if isinstance(event, TrackExceptionEvent) and event.exception["message"] == "This content isn’t available.":
            if self._node.yt_ratelimit:
                await self._node.yt_ratelimit.flag_active_token()

        event.dispatch(self._bot)

        if isinstance(event, TrackStartEvent):
            self._ending_track = self._current

        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) dispatched event {event_type}.")

    async def do_next(self):
        """Processes the next track in the queue."""
        if self._current or self.is_playing or not self.channel:
            return
        
        if self._paused:
            self._paused = False

        if self._track_is_stuck:
            await asyncio.sleep(10)
            self._track_is_stuck = False

        if not self.guild.me.voice:
            await self.connect(timeout=0.0, reconnect=True)
        
        self.pause_votes.clear()
        self.resume_votes.clear()
        self.skip_votes.clear()
        self.previous_votes.clear()
        self.shuffle_votes.clear()
        self.stop_votes.clear()

        track = self.queue.get()

        if not track:
            if self.autoplay and await self.get_recommendations():
                return await self.do_next()
            if self.queue.is_empty:
                self._schedule_inactive_cleanup_timer()
        else:
            try:
                await self.play(track, start=track.position)
            except Exception as e:
                self._logger.error(f"Something went wrong while playing music in {self.guild.name}({self.guild.id})", exc_info=e)
                await asyncio.sleep(5)
                return await self.do_next()

            if not track.requester.bot:
                self._bot.loop.create_task(MongoDBHandler.update_user(track.requester.id, {
                    "$push": {"history": {"$each": [track.track_id], "$slice": -25}}
                }))

        await self.invoke_controller()
        await self.update_voice_status()

        # Realtime Gateway telemetry broadcast to connected Web Dashboard & Frontends
        try:
            from web.realtime import RealtimeGateway
            rt = RealtimeGateway.get_instance()
            if rt:
                self._bot.loop.create_task(rt.broadcast("MUSIC_UPDATED", {
                    "guild_id": str(self.guild.id),
                    "track": getattr(track, "title", None) if track else None,
                    "action": "TRACK_START" if track else "IDLE",
                }))
        except Exception:
            pass

        if self.is_ipc_connected:
            await self.send_ws({
                "op": "trackUpdate", 
                "currentQueuePosition": self.queue._position if track else self.queue._position + 1,
                "trackId": track.track_id if track else None,
                "isPaused": self._paused
            })

    async def invoke_controller(self, current_track=None, *, repost: bool = False):
        """Sends or updates the music controller message in the designated channel."""
        voice_ch = self.channel or (self.guild.me.voice.channel if self.guild and self.guild.me and self.guild.me.voice else None)
        if not self.settings.get('controller', True) or not voice_ch:
            return

        # Do not drop a track-start refresh when another controller edit is in flight.
        # Keep only the newest requested track state; it will be applied immediately
        # after the current Discord message operation completes.
        if self._updating:
            self._pending_controller_track = current_track if current_track is not None else self.current
            self._pending_controller_repost = self._pending_controller_repost or repost
            return

        self._updating = True

        try:
            if current_track is None:
                current_track = self.current
            if repost and self.controller:
                try:
                    await self.controller.edit(view=None)
                except errors.NotFound:
                    pass
                except Exception as e:
                    self._logger.debug(f"Could not retire previous music controller: {e}")
                self.controller = None

            embed, view = self.build_embed(current_track), InteractiveController(self)
            if not embed.color:
                embed.color = Config().embed_color

            target_ctx = self.context
            text_channel = getattr(target_ctx, "channel", None)
            if not text_channel and self.guild:
                text_channel = self.guild.system_channel or next((c for c in self.guild.text_channels if c.permissions_for(self.guild.me).send_messages), None)

            if not self.controller:
                if request_channel_data := self.settings.get("music_request_channel"):
                    if channel := self.bot.get_channel(request_channel_data.get("text_channel_id")):
                        try:
                            self.controller = await channel.fetch_message(request_channel_data.get("controller_msg_id"))
                            await self.controller.edit(embed=embed, view=view)
                        except errors.NotFound:
                            self.controller = None
                
                # Send a new controller message if none exists
                if not self.controller:
                    try:
                        self.controller = await dispatch_message(target_ctx, content=embed, view=view, delete_after=None, requires_fetch=True)
                    except Exception as e:
                        self._logger.warning(f"dispatch_message via target_ctx failed ({e}), falling back to direct channel send")

                    if not self.controller and text_channel:
                        self.controller = await text_channel.send(embed=embed, view=view)

            elif not await self.is_position_fresh():
                try:
                    await self.controller.delete()
                except errors.NotFound:
                    self.controller = None
                    
                try:
                    self.controller = await dispatch_message(target_ctx, content=embed, view=view, delete_after=None, requires_fetch=True)
                except Exception as e:
                    self._logger.warning(f"dispatch_message via target_ctx failed ({e}), falling back to direct channel send")

                if not self.controller and text_channel:
                    self.controller = await text_channel.send(embed=embed, view=view)

            else:
                await self.controller.edit(embed=embed, view=view)

            if self.controller:
                self._logger.info(f"Music controller active for {self.guild.name} in #{getattr(self.controller.channel, 'name', 'unknown')}")
        
        except errors.Forbidden:
            self._logger.warning(f"Missing permission to update the music controller on {self.guild.name}({self.guild.id})")

        except Exception as e:
            self._logger.error(f"Something went wrong while sending music controller to {self.guild.name}({self.guild.id})", exc_info=e)
        
        finally:
            self._updating = False
            pending_track = self._pending_controller_track
            pending_repost = self._pending_controller_repost
            self._pending_controller_track = None
            self._pending_controller_repost = False
            if pending_track is not None:
                await self.invoke_controller(current_track=pending_track, repost=pending_repost)

    async def is_position_fresh(self):
        """Checks if the current controller message is among the most recent messages."""
        try:
            channel = getattr(self.context, "channel", None) or getattr(self.controller, "channel", None)
            if not channel or not self.controller:
                return False
            async for message in channel.history(limit=5):
                if message.id == self.controller.id:
                    return True
        except:
            pass

        return False
    
    async def teardown(self):
        """Cleans up the player and associated resources."""
        try:
            await MongoDBHandler.update_settings(self.guild.id, {"$set": {
                "last_active": (timeNow := round(time.time())), 
                "played_time": round(self.settings.get("played_time", 0) + ((timeNow - self.joinTime) / 60), 2)
            }})
            
            if self.is_ipc_connected:
                await self.send_ws({"op": "playerClose"})
        except:
            pass

        try:
            await self.update_voice_status(remove_status=True)
            self._cancel_inactive_cleanup_timer()
            if self.controller:
                if self.controller.id == self.settings.get("music_request_channel", {}).get("controller_msg_id"):
                    await self.controller.edit(embed=self.build_embed(), view=None)
                else: 
                    await self.controller.delete()
        except:
            pass

        try:
            await self.destroy()
        except:
            pass

    async def get_tracks(
        self,
        query: str,
        *,
        requester: Member,
        search_type: SearchType = None
    ) -> Union[List[Track], Playlist]:
        """Fetches tracks from the node's REST api to parse into Lavalink.

        You can also pass in a discord.py Context object to get a
        Context object on any track you search.
        """
        if not search_type:
            search_type = Config().search_platform
            
        return await self._node.get_tracks(query, requester=requester, search_type=search_type)

    async def connect(self, *, timeout: float, reconnect: bool, self_deaf: bool = False, self_mute: bool = False):
        """Connects the player to a voice channel."""
        self._node._players[self.guild.id] = self
        self._is_connected = True
        await self.guild.change_voice_state(channel=self.channel, self_deaf=self_deaf, self_mute=self_mute)

        if self.channel:
            self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) has been connected to {self.channel.name}({self.channel.id}).")
            
    async def stop(self):
        """Stops the currently playing track."""
        self._current = None
        await self.send(method=RequestMethod.PATCH, data={'encodedTrack': None})

    async def disconnect(self, *, force: bool = False):
        """Disconnects the player from voice."""
        try:
            await self.guild.change_voice_state(channel=None)
        finally:
            self.cleanup()
            self._is_connected = False
            self.channel = None
        
        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) has been disconnected from a voice channel.")

    async def destroy(self):
        """Disconnects and destroys the player, and runs internal cleanup."""
        
        try:
            await self.disconnect()
        except:
            # 'NoneType' has no attribute '_get_voice_client_key' raised by self.cleanup() ->
            # assume we're already disconnected and cleaned up
            assert self.channel is None and not self.is_connected
        
        self._node._players.pop(self.guild.id, None)
        await self.send(method=RequestMethod.DELETE)
    
    async def play(
        self,
        track: Track,
        *,
        start: int = 0,
        end: int = 0,
        ignore_if_playing: bool = False
    ) -> Track:
        """Plays a track."""
        if not self._node:
            return track

        data = {
            "encodedTrack": track.track_id,
            "position": int(start or 0)
        }

        if end or track.end_time:
            data["endTime"] = int(end or track.end_time)

        if self._voice_state.get("sessionId") and self._voice_state.get("event"):
            evt = self._voice_state["event"]
            if evt.get("token") and evt.get("endpoint"):
                channel_id = str(self.channel.id) if self.channel else (str(self.guild.me.voice.channel.id) if self.guild.me and self.guild.me.voice and self.guild.me.voice.channel else None)
                voice_payload = {
                    "token": evt["token"],
                    "endpoint": evt["endpoint"],
                    "sessionId": self._voice_state["sessionId"],
                }
                if channel_id:
                    voice_payload["channelId"] = channel_id
                data["voice"] = voice_payload
        
        await self.send(method=RequestMethod.PATCH, query=f"noReplace={ignore_if_playing}", data=data)
        if self._node.yt_ratelimit:
            await self._node.yt_ratelimit.handle_request()

        self._current = track

        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) playing {track.title} from uri {track.uri} with a length of {track.length}")
        return self._current

    def _validate_time(self, track: Track, start_time: int, end_time: int) -> None:
        """Validates the start and end times for a track."""
        if start_time or end_time:
            if not end_time:
                end_time = track.length

            if start_time >= end_time:
                raise VoicelinkException(self.get_msg("time.invalidStartTime"))

            track_length = track.length
            if not 0 <= start_time <= track_length:
                raise VoicelinkException(self.get_msg("time.invalidStartTime", format_ms(track_length)))
            if not 0 <= end_time <= track_length:
                raise VoicelinkException(self.get_msg("time.invalidEndTime", format_ms(track_length)))

            track.position = start_time
            track.end_time = end_time

    def _cancel_inactive_cleanup_timer(self) -> None:
        """Cancels the per-player inactivity cleanup timer (if any)."""
        task: Optional[asyncio.Task] = getattr(self, "_inactive_cleanup_task", None)
        if task and not task.done():
            task.cancel()
        self._inactive_cleanup_task = None

    def _schedule_inactive_cleanup_timer(self) -> None:
        """Schedules per-player cleanup after inactivity."""
        self._cancel_inactive_cleanup_timer()
        seconds = Config().timer_settings.get("inactive_player_cleanup", 600)
        self._inactive_cleanup_task = self.bot.loop.create_task(
            self._inactive_cleanup_timer_worker(seconds)
        )
        
    async def add_track(self, raw_tracks: Union[Track, List[Track]], *, start_time: int = 0, end_time: int = 0, at_front: bool = False, duplicate: bool = False) -> int:
        """Adds tracks while preventing duplicates in the current track and pending queue."""
        tracks: List[Track] = []
        raw_tracks = raw_tracks[0] if isinstance(raw_tracks, List) and len(raw_tracks) == 1 else raw_tracks
        is_list = isinstance(raw_tracks, List)

        # Always include the currently playing track: it is not stored in Queue._queue's
        # pending section, so checking only queued URIs allowed immediate re-requests.
        duplicate_uris = {
            track.uri
            for track in ([self._current] if self._current else []) + list(self.queue._queue)
            if track and getattr(track, "uri", None)
        }

        position = 0
        if is_list:
            for track in raw_tracks:
                uri = getattr(track, "uri", None)
                if uri and uri in duplicate_uris:
                    continue
                self._validate_time(track, start_time, end_time)
                self.queue.put_at_front(track) if at_front else self.queue.put(track)
                tracks.append(track)
                if uri:
                    duplicate_uris.add(uri)
        else:
            uri = getattr(raw_tracks, "uri", None)
            if uri and uri in duplicate_uris:
                raise DuplicateTrack(self.get_msg("queue.errors.duplicateTrack"))

            self._validate_time(raw_tracks, start_time, end_time)
            position = self.queue.put_at_front(raw_tracks) if at_front else self.queue.put(raw_tracks)
            tracks.append(raw_tracks)

        if tracks:
            if self.channel.members and any(not member.bot for member in self.channel.members):
                self._cancel_inactive_cleanup_timer()
            if self.is_ipc_connected:
                await self.send_ws(
                    {"op": "addTrack", "tracks": [track.track_id for track in tracks], "position": -1 if is_list else position},
                    tracks[0].requester,
                )
            self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) added {len(tracks)} track(s) to the queue.")

        return len(tracks) if is_list else position
    
    async def remove_track(self, index: int, index2: int = None, remove_target: Member = None, requester: Member = None) -> Dict[int, Track]:
        """Removes one or more tracks from the queue."""
        removed_tracks = self.queue.remove(index, index2, remove_target)
        if removed_tracks and self.is_ipc_connected:
            await self.send_ws({
                "op": "removeTrack",
                "indexes": list(removed_tracks.keys()),
                "firstTrackId": list(removed_tracks.values())[0].track_id
            }, requester=requester)

        return removed_tracks
    
    async def seek(self, position: float, requester: Member = None) -> float:
        """Seeks to a position in the currently playing track milliseconds"""
        if not self._current:
            raise VoicelinkException("Nothing is playing right now")
        
        if position < 0 or position > self._current.length:
            raise TrackInvalidPosition("Seek position must be between 0 and the track length")

        await self.send(method=RequestMethod.PATCH, data={"position": position})
        if self.is_ipc_connected:
            await self.send_ws({"op": "updatePosition", "position": position}, requester)
        
        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) has been seeking to {position}.")
        return self._position

    async def set_pause(self, pause: bool, requester: Member = None) -> bool:
        """Sets the pause state of the currently playing track."""

        self._paused = pause
        self.pause_votes.clear() if pause else self.resume_votes.clear()
        await self.send(method=RequestMethod.PATCH, data={"paused": pause})

        if self.is_ipc_connected:
            await self.send_ws({"op": "updatePause", "pause": pause}, requester)
        
        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) has been {'paused' if pause else 'resumed'}.")
        return self._paused

    async def set_volume(self, volume: int, requester: Member = None) -> int:
        """Sets the volume of the player as an integer. Lavalink accepts values from 0 to 500."""
        await self.send(method=RequestMethod.PATCH, data={"volume": volume})
        self._volume = volume

        # Realtime Gateway telemetry broadcast to connected Web Dashboard & Frontends
        try:
            from web.realtime import RealtimeGateway
            rt = RealtimeGateway.get_instance()
            if rt:
                self._bot.loop.create_task(rt.broadcast("MUSIC_UPDATED", {
                    "guild_id": str(self.guild.id),
                    "action": "VOLUME",
                    "volume": volume,
                }))
        except Exception:
            pass

        if self.is_ipc_connected:
            await self.send_ws({"op": "updateVolume", "volume": volume}, requester)

        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) has been update the volume to {volume}.")
        return self._volume

    async def shuffle(self, queue_type: str, requester: Member = None) -> None:
        """Shuffles the tracks in the specified queue or history."""
        replacement = self.queue.tracks() if queue_type == "queue" else self.queue.history()
        if len(replacement) < 3:
            raise VoicelinkException(self.get_msg('player.controls.shuffle.error'))
        
        shuffle(replacement)
        self.queue.replace(queue_type, replacement)
        self.shuffle_votes.clear()
        if self.is_ipc_connected:
            await self.send_ws({
                "op": "shuffleTrack",
                "tracks": [{"trackId": track.track_id, "requesterId": str(track.requester.id)} for track in replacement],
                "queue_type": queue_type
            }, requester)
        
        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) has been shuffled the queue.")

    async def swap_track(self, index1: int, index2: int, requester: Member = None) -> Tuple[Track, Track]:
       """Swaps two tracks in the queue at the specified indices."""
       track1, track2 = self.queue.swap(index1, index2)
       if self.is_ipc_connected:
           await self.send_ws({
                "op": "swapTrack",
                "index1": {"index": index1, "trackId": track1.track_id},
                "index2": {"index": index2, "trackId": track2.track_id}
            }, requester)
       return track1, track2

    async def move_track(self, index: int, new_index: int, requester: Member = None) -> Optional[Track]:
        """Moves a track from its current position to a new position in the queue."""
        moved_track = self.queue.move(index, new_index)

        if self.is_ipc_connected:
            await self.send_ws({"op": "moveTrack", "movedTrack": {"index": index, "trackId": moved_track.track_id}, "newIndex": new_index}, requester)

        return moved_track
    
    async def set_repeat(self, mode: LoopType = None, requester: Member = None) -> LoopType:
        """Sets the repeat mode for the queue."""
        if not mode:
            mode = self.queue._repeat.next()
        
        if not isinstance(mode, LoopType):
            raise VoicelinkException("Invalid repeat mode.")
        
        self.queue._repeat.set_mode(mode)
        
        if self.is_ipc_connected:
            await self.send_ws({"op": "repeatTrack", "repeatMode": mode.name.lower()}, requester)

        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) has been update the repeat mode to {mode.name.lower()}.")
        return mode
    
    async def add_filter(self, filter: Filter, requester: Member = None, fast_apply: bool = False) -> Filters:
        """Adds a filter to the player's audio stream."""
        try:
            self._filters.add_filter(filter=filter)
        except FilterTagAlreadyInUse:
            raise FilterTagAlreadyInUse(self.get_msg("effects.tagInUse"))
        
        payload = self._filters.get_all_payloads()
        await self.send(method=RequestMethod.PATCH, data={"filters": payload})
        if fast_apply:
            await self.seek(self.position)
        
        if self.is_ipc_connected:
            await self.send_ws({
                "op": "updateFilter",
                "filter": {"tag": filter.tag, "scope": filter.scope, "payload": filter.payload},
                "type": "add"
            }, requester)

        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) has been applied a {filter.tag} filter.")
        return self._filters

    async def clear_queue(self, queue_type: str, requester: Member = None) -> None:
        """Clears the queue or the history of tracks."""
        queue_type = queue_type.lower()
        if queue_type == 'history':
            self.queue.history_clear(self.is_playing)
        elif queue_type == "queue":
            self.queue.clear()
        
        if self.is_ipc_connected:
            await self.send_ws({
                "op": "clearQueue",
                "queueType": queue_type
            }, requester)

    async def remove_filter(self, filter_tag: str, requester: Member = None, fast_apply: bool = False) -> Filters:
        self._filters.remove_filter(filter_tag=filter_tag)
        payload = self._filters.get_all_payloads()
        await self.send(method=RequestMethod.PATCH, data={"filters": payload})
        if fast_apply:
            await self.seek(self.position)
        
        if self.is_ipc_connected:
            await self.send_ws({
                "op": "updateFilter",
                "filter": {"tag": filter_tag},
                "type": "remove"
            }, requester)

        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) has been removed a {filter_tag} filter.")
        return self._filters
    
    async def reset_filter(self, *, requester: Member = None, fast_apply=False) -> None:
        """Resets all filters applied to the player's audio stream."""
        if not self._filters:
            raise FilterInvalidArgument("You must have filters applied first in order to use this method.")
        
        self._filters.reset_filters()
        await self.send(method=RequestMethod.PATCH, data={"filters": {}})
        if fast_apply:
            await self.seek(self.position)

        if self.is_ipc_connected:
            await self.send_ws({
                "op": "updateFilter",
                "type": "reset"
            }, requester)

        self._logger.debug(f"Player in {self.guild.name}({self.guild.id}) has been removed all filters.")

    async def change_node(self, identifier: str = None) -> None:
        """Changes the audio processing node for the guild.."""
        try:
            node = NodePool.get_node(identifier=identifier)
        except:
            return await self.teardown()

        self._node._players.pop(self.guild.id)
        self._node = node
        self._node._players[self.guild.id] = self

        await self._dispatch_voice_update(self._voice_state)

        if self.current:
            await self.play(self.current, start=self.position)
            self._last_update = time.time() * 1000

            if self.is_paused:
                await self.set_pause(True)
    
    async def get_recommendations(self, *, track: Optional[Track] = None) -> bool:
        """Fetches and adds recommended tracks based on the provided track or recent history."""
        if not track:
            # Base discovery on the most recently played track so autoplay
            # stays musically related instead of jumping randomly across history.
            history = self.queue.history(incTrack=True)
            if not history:
                return False
            track = history[-1]

        tracks = await track.get_recommendations(self._node)
        if tracks:
            # Autoplay is a one-song-at-a-time discovery feature. Keep manual
            # queue priority intact and avoid dumping an entire recommendation
            # result set into the queue.
            candidate = next(
                (item for item in tracks if item.uri != track.uri),
                None,
            )
            if not candidate:
                return False

            # Keep a marker on the Track object so the start listener can
            # distinguish an autoplay pick from a manually requested song.
            candidate._is_autoplay_recommendation = True
            try:
                await self.add_track(candidate, duplicate=False)
            except DuplicateTrack:
                self._logger.debug(
                    "Skipping duplicate autoplay recommendation in guild %s",
                    self.guild.id,
                )
                return False

            self._logger.info(
                "Autoplay queued recommendation '%s' for guild %s",
                candidate.title,
                self.guild.id,
            )
            return True
        return False
    
    async def update_voice_status(self, remove_status: bool = False) -> None:
        """Updates the voice status of the channel based on the specified template."""
        template = self.settings.get("stage_announce_template", Config().voice_status_template)
        if not template or not self.channel:
            return
        
        try:
            rv = {key: func() if callable(func) else func for key, func in self._ph.variables.items()}
            status = None if remove_status else self._ph.replace(text=template, variables=rv)
            # if self.channel.status != status:
            if self.channel.type == ChannelType.voice:
                await self.channel.edit(status=status)

        except Exception as e:
            self._logger.error(
                f"Failed to update voice status in channel '{self.channel.name}' "
                f"({self.channel.id}) for guild '{self.channel.guild}' "
                f"({self.channel.guild.id})", 
                exc_info=e
            )

    async def send_ws(self, payload, requester: Member = None):
        """Sends a WebSocket payload to the bot's IPC (Inter-Process Communication) system."""
        payload['guildId'] = str(self.guild.id)
        if requester:
            payload['requesterId'] = str(requester.id)
        await self._ipc_client.send(payload)

    async def _inactive_cleanup_timer_worker(self, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
            if not self._guild or not self._node:
                return
            if self._guild.id not in self._node._players:
                return

            members = self.channel.members if self.channel else []
            has_non_bot = any(not m.bot or not m.voice.self_deaf for m in members)
            # Empty channel: always pause/teardown. If people remain: only when idle (not playing + empty queue).
            if has_non_bot and (self.is_playing or not self.queue.is_empty):
                return

            self._inactive_cleanup_task = None

            if self.settings.get("24/7", False):
                if not self.is_paused:
                    await self.set_pause(True)
            else:
                await self.teardown()
        except asyncio.CancelledError:
            return
        except Exception as e:
            # Logger is best-effort; timer cleanup should never crash the loop.
            try:
                guild_id = self._guild.id if self._guild else "unknown"
            except Exception:
                guild_id = "unknown"
            if self._logger:
                self._logger.error(
                    f"Inactive cleanup timer failed for guild {guild_id}",
                    exc_info=e
                )