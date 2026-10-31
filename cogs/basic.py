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

import re
import asyncio
import discord
import voicelink

from io import StringIO
from validators import url
from discord import app_commands
from discord.ext import commands
from function import (
    cooldown_check,
    get_aliases,
    logger
)

from voicelink import MongoDBHandler, LangHandler, Config
from voicelink.views import SearchView, QueueView, LinkView, LyricsView, HelpView
from voicelink.utils import format_ms, format_to_ms, truncate_string, dispatch_message, send_localized_message

async def nowplay(ctx: commands.Context, player: voicelink.Player):
    track = player.current
    if not track:
        return await send_localized_message(ctx, 'player.errors.noTrackPlaying', ephemeral=True)

    texts = await LangHandler.get_lang(ctx.guild.id, "player.playback.nowplayingDesc", "player.playback.nowplayingField", "player.playback.nowplayingLink")
    upnext = "\n".join(f"`{index}.` `[{track.formatted_length}]` [{truncate_string(track.title)}]({track.uri})" for index, track in enumerate(player.queue.tracks()[:2], start=2))
    
    embed = discord.Embed(description=texts[0].format(track.title), color=Config().embed_color)
    embed.set_author(
        name=track.requester.display_name,
        icon_url=track.requester.display_avatar.url
    )
    embed.set_thumbnail(url=track.thumbnail)

    if upnext:
        embed.add_field(name=texts[1], value=upnext)

    if track.is_stream:
        pbar_str = "🔴 **LIVE STREAM**"
    else:
        total_blocks = 14
        progress_ratio = max(0.0, min(1.0, player.position / max(1, track.length)))
        filled = int(round(progress_ratio * total_blocks))
        pbar = "▰" * filled + "▱" * (total_blocks - filled)
        status_icon = "⏸️" if player.is_paused else "▶️"
        pbar_str = f"{status_icon} `{pbar}` **[{format_ms(player.position)} / {track.formatted_length}]**"

    embed.add_field(name="\u2800", value=pbar_str, inline=False)
    embed.set_footer(text="Rem 🎧💜 • Your Anime Music Companion", icon_url=ctx.bot.user.display_avatar.url if ctx.bot.user else None)

    return await dispatch_message(ctx, embed, view=LinkView(texts[2].format(track.source.title()), track.emoji, track.uri))

async def announce_track(ctx, track: voicelink.Track, *, queued: bool = False):
    """Announce queued tracks now; for immediate playback, confirm start so interaction acknowledges cleanly."""
    if not queued:
        return await dispatch_message(
            ctx,
            f"🎶 **Playing:** [{track.title}]({track.uri}) — **{track.author}** (`{track.formatted_length}`)"
        )
    return await dispatch_message(
        ctx,
        f"🎵 **Up Next:** [{track.title}]({track.uri}) — **{track.author}** "
        f"(`{track.formatted_length}`)"
    )


class Basic(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.description = "This category is available to anyone on this server. Voting is required in certain commands."
        self.ctx_menu = app_commands.ContextMenu(
            name="play",
            callback=self._play
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def help_autocomplete(self, interaction: discord.Interaction, current: str) -> list:
        return [app_commands.Choice(name=c.capitalize(), value=c) for c in self.bot.cogs if c not in ["Nodes", "Task"] and current in c]

    async def play_autocomplete(self, interaction: discord.Interaction, current: str) -> list:
        if voicelink.pool.URL_REGEX.match(current):
            return []

        if current:
            node = voicelink.NodePool.get_node()
            if not node:
                return []
            
            tracks: list[voicelink.Track] = await node.get_tracks(current, requester=interaction.user)
            if not tracks:
                return []
            
            if isinstance(tracks, voicelink.Playlist):
                tracks = tracks.tracks

            return [app_commands.Choice(name=truncate_string(f"🎵 [{track.formatted_length}] {track.author} - {track.title}", 100), value=track.uri) for track in tracks]
        
        history = {track["identifier"]: track for track_id in reversed(await MongoDBHandler.get_user(interaction.user.id, d_type="history")) if (track := voicelink.Track.decode(track_id))["uri"]}
        return [app_commands.Choice(name=truncate_string(f"🕒 [{format_ms(track['length'])}] {track['author']} - {track['title']}", 100), value=track['uri']) for track in history.values() if len(track['uri']) <= 100][:25]
            
    @commands.hybrid_command(name="connect", aliases=get_aliases("connect"))
    @app_commands.describe(channel="Provide a channel to connect.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def connect(self, ctx: commands.Context, channel: discord.VoiceChannel = None) -> None:
        "Connect to a voice channel."
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.defer()
            except Exception:
                pass

        # Identify requested or member voice channel
        member = ctx.author
        target_channel = channel or getattr(getattr(member, "voice", None), "channel", None)
        if not target_channel:
            return await send_localized_message(ctx, "voice.connection.noChannel")

        try:
            player = await voicelink.connect_channel(ctx, target_channel)
            await send_localized_message(ctx, "voice.connection.connect", player.channel)
        except discord.errors.ClientException as exc:
            guild = ctx.guild
            bot_member = guild.me
            actual_voice_channel = getattr(getattr(bot_member, "voice", None), "channel", None)
            stale_player = guild.voice_client

            if actual_voice_channel is None and stale_player is not None:
                logger.warning(
                    "[Voice] Stale voice client detected in guild %s; attempting one cleanup/reconnect.",
                    guild.id,
                    exc_info=exc,
                )
                try:
                    teardown = getattr(stale_player, "teardown", None)
                    if callable(teardown):
                        await teardown()
                    else:
                        await stale_player.disconnect(force=True)
                except Exception:
                    logger.exception(
                        "[Voice] Stale voice client cleanup failed in guild %s.",
                        guild.id,
                    )

                # Retry exactly once; never loop or destroy a confirmed live connection.
                try:
                    player = await voicelink.connect_channel(ctx, target_channel)
                    await send_localized_message(ctx, "voice.connection.connect", player.channel)
                except Exception:
                    logger.exception(
                        "[Voice] Reconnect after stale-client cleanup failed in guild %s.",
                        guild.id,
                    )
                    return await send_localized_message(
                        ctx, "voice.connection.alreadyConnected"
                    )
            else:
                logger.info(
                    "[Voice] Connect requested while bot is already in channel %s (guild %s).",
                    getattr(actual_voice_channel, "id", None),
                    guild.id,
                )
                return await send_localized_message(
                    ctx, "voice.connection.alreadyConnected"
                )
        except voicelink.VoicelinkException as vle:
            return await dispatch_message(ctx, str(vle))
        except Exception as e:
            logger.exception("[Voice] Unexpected error connecting in guild %s: %s", ctx.guild.id, e)
            return await dispatch_message(ctx, f"⚠️ Unable to connect to voice channel: {e}")
                
    @commands.hybrid_command(name="play", aliases=get_aliases("play"))
    @app_commands.describe(
        query="Input a query or a searchable link.",
        start="Specify a time you would like to start, e.g. 1:00",
        end="Specify a time you would like to end, e.g. 4:00"
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def play(self, ctx: commands.Context, *, query: str, start: str = "0", end: str = "0") -> None:
        "Loads your input into the queue."
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.defer()
            
        guild = ctx.guild
        bot_member = guild.me
        actual_voice_channel = getattr(getattr(bot_member, "voice", None), "channel", None)
        player: voicelink.Player = guild.voice_client

        # Clean up stale VoiceClient if Discord confirms bot is not in a voice channel
        if actual_voice_channel is None and player is not None:
            logger.warning("[Voice] Stale voice client detected in guild %s during play; tearing down.", guild.id)
            try:
                teardown = getattr(player, "teardown", None)
                if callable(teardown):
                    await teardown()
                else:
                    await player.disconnect(force=True)
            except Exception:
                logger.exception("[Voice] Cleanup of stale player failed in guild %s.", guild.id)
            player = None

        if not player:
            player = await voicelink.connect_channel(ctx)
        else:
            player.context = ctx

        # Auto-relocate if bot is sitting alone in an empty channel and user is in another VC
        user_voice = getattr(getattr(ctx.author, "voice", None), "channel", None)
        if user_voice and actual_voice_channel and user_voice != actual_voice_channel:
            human_listeners = [m for m in actual_voice_channel.members if not m.bot]
            if len(human_listeners) == 0:
                logger.info("[Voice] Moving idle bot from empty channel %s to user channel %s", actual_voice_channel.id, user_voice.id)
                try:
                    await player.move_to(user_voice)
                    player.channel = user_voice
                except Exception:
                    logger.exception("[Voice] Auto-relocation failed from channel %s to %s", actual_voice_channel.id, user_voice.id)

        if not player.is_user_join(ctx.author):
            return await send_localized_message(ctx, "voice.connection.notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        tracks = await player.get_tracks(query, requester=ctx.author)
        if not tracks:
            return await send_localized_message(ctx, "player.errors.noTrackFound")

        try:
            if isinstance(tracks, voicelink.Playlist):
                index = await player.add_track(tracks.tracks, start_time=format_to_ms(start), end_time=format_to_ms(end))
                await send_localized_message(ctx, "player.playback.playlistLoad", tracks.name, index)
            else:
                position = await player.add_track(tracks[0], start_time=format_to_ms(start), end_time=format_to_ms(end))
                await announce_track(ctx, tracks[0], queued=position >= 1 and player.is_playing)
        finally:
            if not player.is_playing:
                await player.do_next()
    
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def _play(self, interaction: discord.Interaction, message: discord.Message):
        query = ""

        if message.content:
            url = re.findall(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", message.content)
            if url:
                query = url[0]

        elif message.attachments:
            query = message.attachments[0].url

        if not query:
            return await send_localized_message(interaction, "player.errors.noPlaySource", ephemeral=True)

        guild = interaction.guild
        bot_member = guild.me
        actual_voice_channel = getattr(getattr(bot_member, "voice", None), "channel", None)
        player: voicelink.Player = guild.voice_client

        if actual_voice_channel is None and player is not None:
            logger.warning("[Voice] Stale voice client detected in guild %s during context play; tearing down.", guild.id)
            try:
                teardown = getattr(player, "teardown", None)
                if callable(teardown):
                    await teardown()
                else:
                    await player.disconnect(force=True)
            except Exception:
                logger.exception("[Voice] Cleanup of stale player failed in guild %s.", guild.id)
            player = None

        if not player:
            player = await voicelink.connect_channel(interaction)
        else:
            player.context = interaction

        user_voice = getattr(getattr(interaction.user, "voice", None), "channel", None)
        if user_voice and actual_voice_channel and user_voice != actual_voice_channel:
            human_listeners = [m for m in actual_voice_channel.members if not m.bot]
            if len(human_listeners) == 0:
                logger.info("[Voice] Moving idle bot from empty channel %s to user channel %s", actual_voice_channel.id, user_voice.id)
                try:
                    await player.move_to(user_voice)
                    player.channel = user_voice
                except Exception:
                    logger.exception("[Voice] Auto-relocation failed from channel %s to %s", actual_voice_channel.id, user_voice.id)

        if not player.is_user_join(interaction.user):
            return await send_localized_message(interaction, "voice.connection.notInChannel", interaction.user.mention, player.channel.mention, ephemeral=True)

        await interaction.response.defer()
        tracks = await player.get_tracks(query, requester=interaction.user)
        if not tracks:
            return await send_localized_message(interaction, "player.errors.noTrackFound")

        try:
            if isinstance(tracks, voicelink.Playlist):
                index = await player.add_track(tracks.tracks)
                await send_localized_message(interaction, "player.playback.playlistLoad", tracks.name, index)
            else:
                position = await player.add_track(tracks[0])
                await announce_track(interaction, tracks[0], queued=position >= 1 and player.is_playing)
        finally:
            if not player.is_playing:
                await player.do_next()

    @commands.hybrid_command(name="search", aliases=get_aliases("search"))
    @app_commands.describe(
        query="Input the name of the song.",
        platform="Select the platform you want to search."
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name=search_type.display_name, value=search_type.name)
        for search_type in voicelink.SearchType
    ])
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def search(self, ctx: commands.Context, *, query: str, platform: str = Config().search_platform.name):
        "Searches your query and displays the results."
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.defer()
            
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        if not player.is_user_join(ctx.author):
            return await send_localized_message(ctx, "voice.connection.notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        if url(query):
            return await send_localized_message(ctx, "search.noLinkSupport", ephemeral=True)
        
        search_type: voicelink.SearchType = voicelink.SearchType.from_platform(platform) or Config().search_platform
        tracks = await player.get_tracks(query=query, requester=ctx.author, search_type=search_type)
        if not tracks:
            return await send_localized_message(ctx, "player.errors.noTrackFound")

        texts = await LangHandler.get_lang(ctx.guild.id, "search.title", "search.desc", "common.status.live", "player.playback.trackLoadPos", "player.playback.trackLoad", "search.wait", "search.success")
        query_track = "\n".join(f"`{index}.` `[{track.formatted_length}]` **{track.title[:35]}**" for index, track in enumerate(tracks[0:10], start=1))
        embed = discord.Embed(title=texts[0].format(query), description=texts[1].format(Config().get_source_config(search_type.display_name, "emoji"), search_type.display_name, len(tracks[0:10]), query_track), color=Config().embed_color)
        view = SearchView(tracks=tracks[0:10], texts=[texts[5], texts[6]])
        view.response = await dispatch_message(ctx, embed, view=view, ephemeral=True)

        await view.wait()
        if view.values is not None:
            already_playing = player.is_playing
            for index, value in enumerate(view.values):
                track = tracks[int(value.split(". ")[0]) - 1]
                position = await player.add_track(track)
                await announce_track(ctx, track, queued=already_playing or index > 0 or (position >= 1 and player.is_playing))

            if not player.is_playing:
                await player.do_next()

    @commands.hybrid_command(name="playtop", aliases=get_aliases("playtop"))
    @app_commands.describe(
        query="Input a query or a searchable link.",
        start="Specify a time you would like to start, e.g. 1:00",
        end="Specify a time you would like to end, e.g. 4:00"
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def playtop(self, ctx: commands.Context, *, query: str, start: str = "0", end: str = "0"):
        "Adds a song with the given url or query on the top of the queue."
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.defer()
        
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        if not player.is_user_join(ctx.author):
            return await send_localized_message(ctx, "voice.connection.notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        tracks = await player.get_tracks(query, requester=ctx.author)
        if not tracks:
            return await send_localized_message(ctx, "player.errors.noTrackFound")
        
        try:
            if isinstance(tracks, voicelink.Playlist):
                index = await player.add_track(tracks.tracks, start_time=format_to_ms(start), end_time=format_to_ms(end), at_front=True)
                await send_localized_message(ctx, "player.playback.playlistLoad", tracks.name, index)
            else:
                position = await player.add_track(tracks[0], start_time=format_to_ms(start), end_time=format_to_ms(end), at_front=True)
                await announce_track(ctx, tracks[0], queued=position >= 1 and player.is_playing)
        finally:
            if not player.is_playing:
                await player.do_next()

    @commands.hybrid_command(name="forceplay", aliases=get_aliases("forceplay"))
    @app_commands.describe(
        query="Input a query or a searchable link.",
        start="Specify a time you would like to start, e.g. 1:00",
        end="Specify a time you would like to end, e.g. 4:00"
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def forceplay(self, ctx: commands.Context, *, query: str, start: str = "0", end: str = "0"):
        "Enforce playback using the given URL or query."
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.defer()
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.missingFunction", ephemeral=True)
        
            
        tracks = await player.get_tracks(query, requester=ctx.author)
        if not tracks:
            return await send_localized_message(ctx, "player.errors.noTrackFound")
        
        try:
            if isinstance(tracks, voicelink.Playlist):
                index = await player.add_track(tracks.tracks, start_time=format_to_ms(start), end_time=format_to_ms(end), at_front=True)
                await send_localized_message(ctx, "player.playback.playlistLoad", tracks.name, index)
            else:
                texts = await LangHandler.get_lang(ctx.guild.id, "common.status.live", "player.playback.trackLoad")
                await player.add_track(tracks[0], start_time=format_to_ms(start), end_time=format_to_ms(end), at_front=True)

                stream_content = f"`{texts[0]}`" if tracks[0].is_stream else ""

                await dispatch_message(
                    ctx,
                    stream_content + texts[1],
                    tracks[0].title, tracks[0].uri, tracks[0].author, tracks[0].formatted_length,
                )
        finally:
            if player.queue._repeat.mode == voicelink.LoopType.TRACK:
                await player.set_repeat(voicelink.LoopType.OFF)
                
            await player.stop() if player.is_playing else await player.do_next()

    @commands.hybrid_command(name="pause", aliases=get_aliases("pause"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def pause(self, ctx: commands.Context):
        "Pause the music."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if player.is_paused:
            return await send_localized_message(ctx, "player.controls.pause.error", ephemeral=True)

        if not player.is_privileged(ctx.author):
            if ctx.author in player.pause_votes:
                return await send_localized_message(ctx, "voting.voted", ephemeral=True)
            
            player.pause_votes.add(ctx.author)
            if len(player.pause_votes) < (required := player.required()):
                return await send_localized_message(ctx, "player.controls.pause.vote", ctx.author, len(player.pause_votes), required)

        await player.set_pause(True, ctx.author)
        await send_localized_message(ctx, player.controls.pause.success, ctx.author)

    @commands.hybrid_command(name="resume", aliases=get_aliases("resume"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def resume(self, ctx: commands.Context):
        "Resume the music."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_paused:
            return await send_localized_message(ctx, "player.controls.resume.error")

        if not player.is_privileged(ctx.author):
            if ctx.author in player.resume_votes:
                return await send_localized_message(ctx, "voting.voted", ephemeral=True)
            
            player.resume_votes.add(ctx.author)
            if len(player.resume_votes) < (required := player.required()):
                return await send_localized_message(ctx, "player.controls.resume.vote", ctx.author, len(player.resume_votes), required)

        await player.set_pause(False, ctx.author)
        await send_localized_message(ctx, "player.controls.resume.success", ctx.author)

    @commands.hybrid_command(name="skip", aliases=get_aliases("skip"))
    @app_commands.describe(index="Enter a index that you want to skip to.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def skip(self, ctx: commands.Context, index: int = 0):
        "Skips to the next song or skips to the specified song."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.node._available:
            return await send_localized_message(ctx, "player.errors.nodeReconnect")
        
        if not player.is_playing:
            return await send_localized_message(ctx, "player.controls.skip.error", ephemeral=True)

        if not player.is_privileged(ctx.author):
            if ctx.author == player.current.requester:
                pass
            elif ctx.author in player.skip_votes:
                return await send_localized_message(ctx, "voting.voted", ephemeral=True)
            else:
                player.skip_votes.add(ctx.author)
                if len(player.skip_votes) < (required := player.required()):
                    return await send_localized_message(ctx, "player.controls.skip.vote", ctx.author, len(player.skip_votes), required)

        if index:
            player.queue.skipto(index)

        await send_localized_message(ctx, "player.controls.skip.success", ctx.author)
        if player.queue._repeat.mode == voicelink.LoopType.TRACK:
            await player.set_repeat(voicelink.LoopType.OFF)
            
        await player.stop()

    @commands.hybrid_command(name="back", aliases=get_aliases("back"))
    @app_commands.describe(index="Enter a index that you want to skip back to.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def back(self, ctx: commands.Context, index: int = 1):
        "Skips back to the previous song or skips to the specified previous song."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.node._available:
            return await send_localized_message(ctx, "player.errors.nodeReconnectode")
        
        if not player.is_privileged(ctx.author):
            if ctx.author in player.previous_votes:
                return await send_localized_message(ctx, "voting.voted", ephemeral=True)
            
            player.previous_votes.add(ctx.author)
            if len(player.previous_votes) < (required := player.required()):
                return await send_localized_message(ctx, "player.controls.back.vote", ctx.author, len(player.previous_votes), required)

        if not player.is_playing:
            player.queue.backto(index)
            await player.do_next()
        else:
            player.queue.backto(index + 1)
            await player.stop()

        await send_localized_message(ctx, "player.controls.back.success", ctx.author)
        if player.queue._repeat.mode == voicelink.LoopType.TRACK:
            await player.set_repeat(voicelink.LoopType.OFF)

    @commands.hybrid_command(name="seek", aliases=get_aliases("seek"))
    @app_commands.describe(position="Input position. Exmaple: 1:20.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def seek(self, ctx: commands.Context, position: str):
        "Change the player position."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.missingPosition", ephemeral=True)

        if not player.current or player.position == 0:
            return await send_localized_message(ctx, "player.errors.noTrackPlaying", ephemeral=True)

        if not (num := format_to_ms(position)):
            return await send_localized_message(ctx, "time.formatError", ephemeral=True)

        await player.seek(num, ctx.author)
        await send_localized_message(ctx, "player.controls.seek", position)

    @commands.hybrid_group(
        name="queue", 
        aliases=get_aliases("queue"),
        fallback="list",
        invoke_without_command=True
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def queue(self, ctx: commands.Context):
        "Display the players queue songs in your queue."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_user_join(ctx.author):
            return await send_localized_message(ctx, "voice.connection.notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        if player.queue.is_empty:
            return await nowplay(ctx, player)
        view = QueueView(player=player, author=ctx.author)
        view.response = await dispatch_message(ctx, await view.build_embed(), view=view)

    @queue.command(name="export", aliases=get_aliases("export"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def export(self, ctx: commands.Context):
        "Exports the entire queue to a text file"
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)
        
        if not player.is_user_join(ctx.author):
            return await send_localized_message(ctx, "voice.connection.notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)
        
        if player.queue.is_empty and not player.current:
            return await send_localized_message(ctx, "player.errors.noTrackPlaying", ephemeral=True)

        await ctx.defer()

        tracks = player.queue.tracks(True)
        temp = ""
        raw = "----------->Raw Info<-----------\n"

        total_length = 0
        for index, track in enumerate(tracks, start=1):
            temp += f"{index}. {track.title} [{format_ms(track.length)}]\n"
            raw += track.track_id
            if index != len(tracks):
                raw += ","
            total_length += track.length

        temp = "!Remember do not change this file!\n------------->Info<-------------\nGuild: {} ({})\nRequester: {} ({})\nTracks: {} - {}\n------------>Tracks<------------\n".format(
            ctx.guild.name, ctx.guild.id,
            ctx.author.display_name, ctx.author.id,
            len(tracks), format_ms(total_length)
        ) + temp
        temp += raw

        await ctx.reply(content="", file=discord.File(StringIO(temp), filename=f"{ctx.guild.id}_Full_Queue.txt"))

    @queue.command(name="import", aliases=get_aliases("import"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def _import(self, ctx: commands.Context, attachment: discord.Attachment):
        "Imports the text file and adds the track to the current queue."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            player = await voicelink.connect_channel(ctx)

        if not player.is_user_join(ctx.author):
            return await send_localized_message(ctx, "voice.connection.notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        try:
            bytes = await attachment.read()
            track_ids = bytes.split(b"\n")[-1]
            track_ids = track_ids.decode().split(",")
            
            tracks = [voicelink.Track(track_id=track_id, info=voicelink.Track.decode(track_id), requester=ctx.author) for track_id in track_ids]
            if not tracks:
                return await send_localized_message(ctx, "player.errors.noTrackFound")

            index = await player.add_track(tracks)
            await send_localized_message(ctx, "player.playback.playlistLoad", attachment.filename, index)
        except Exception as e:
            logger.error("error", exc_info=e)
            raise e

        finally:
            if not player.is_playing:
                await player.do_next()

    @commands.hybrid_command(name="history", aliases=get_aliases("history"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def history(self, ctx: commands.Context):
        "Display the players queue songs in your history queue."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_user_join(ctx.author):
            return await send_localized_message(ctx, "voice.connection.notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        if not player.queue.history():
            return await nowplay(ctx, player)

        view = QueueView(player=player, author=ctx.author, is_queue=False)
        view.response = await dispatch_message(ctx, await view.build_embed(), view=view)

    @commands.hybrid_command(name="leave", aliases=get_aliases("leave"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def leave(self, ctx: commands.Context):
        "Disconnects the bot from your voice channel and chears the queue."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            if ctx.author in player.stop_votes:
                return await send_localized_message(ctx, "voting.voted", ephemeral=True)
            else:
                player.stop_votes.add(ctx.author)
                if len(player.stop_votes) >= (required := player.required(leave=True)):
                    pass
                else:
                    return await send_localized_message(ctx, "player.controls.leave.vote", ctx.author, len(player.stop_votes), required)

        await send_localized_message(ctx, "player.controls.leave.success", ctx.author)
        await player.teardown()

    @commands.hybrid_command(name="nowplaying", aliases=get_aliases("nowplaying"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def nowplaying(self, ctx: commands.Context):
        "Shows details of the current track."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_user_join(ctx.author):
            return await send_localized_message(ctx, "voice.connection.notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        await nowplay(ctx, player)

    @commands.hybrid_command(name="loop", aliases=get_aliases("loop"))
    @app_commands.describe(mode="Choose a looping mode.")
    @app_commands.choices(mode=[
        app_commands.Choice(name=loop_type.name.title(), value=loop_type.name)
        for loop_type in voicelink.LoopType
    ])
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def loop(self, ctx: commands.Context, mode: str):
        "Changes Loop mode."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.missingMode", ephemeral=True)

        await player.set_repeat(voicelink.LoopType[mode] if mode in voicelink.LoopType.__members__ else voicelink.LoopType.OFF, ctx.author)
        await send_localized_message(ctx, "player.controls.repeat", mode.capitalize())

    @commands.hybrid_command(name="clear", aliases=get_aliases("clear"))
    @app_commands.describe(queue="Choose a queue that you want to clear.")
    @app_commands.choices(queue=[
        app_commands.Choice(name='Queue', value='queue'),
        app_commands.Choice(name='History', value='history')
    ])
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def clear(self, ctx: commands.Context, queue: str = "queue"):
        "Remove all the tracks in your queue or history queue."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.missingQueue", ephemeral=True)

        await player.clear_queue(queue, ctx.author)
        await send_localized_message(ctx, "queue.management.cleared", queue.capitalize())

    @commands.hybrid_command(name="remove", aliases=get_aliases("remove"))
    @app_commands.describe(
        position1="Input a position from the queue to be removed.",
        position2="Set the range of the queue to be removed.",
        member="Remove tracks requested by a specific member."
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def remove(self, ctx: commands.Context, position1: int, position2: int = None, member: discord.Member = None):
        "Removes specified track or a range of tracks from the queue."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.missingQueue", ephemeral=True)

        removed_tracks = await player.remove_track(position1, position2, remove_target=member, requester=ctx.author)
        await send_localized_message(ctx, "queue.management.removed", len(removed_tracks.keys()))

    @commands.hybrid_command(name="forward", aliases=get_aliases("forward"))
    @app_commands.describe(position="Input an amount that you to forward to. Exmaple: 1:20")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def forward(self, ctx: commands.Context, position: str = "10"):
        "Forwards by a certain amount of time in the current track. The default is 10 seconds."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.missingPosition", ephemeral=True)

        if not player.current:
            return await send_localized_message(ctx, "player.errors.noTrackPlaying", ephemeral=True)

        if not (num := format_to_ms(position)):
            return await send_localized_message(ctx, "time.formatError", ephemeral=True)

        await player.seek(int(player.position + num))
        await send_localized_message(ctx, "player.controls.forward", format_ms(player.position + num))

    @commands.hybrid_command(name="rewind", aliases=get_aliases("rewind"))
    @app_commands.describe(position="Input an amount that you to rewind to. Exmaple: 1:20")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def rewind(self, ctx: commands.Context, position: str = "10"):
        "Rewind by a certain amount of time in the current track. The default is 10 seconds."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.missingPosition", ephemeral=True)

        if not player.current:
            return await send_localized_message(ctx, "player.errors.noTrackPlaying", ephemeral=True)
        
        if not (num := format_to_ms(position)):
            return await send_localized_message(ctx, "time.formatError", ephemeral=True)

        await player.seek(int(player.position - num))
        await send_localized_message(ctx, "player.controls.rewind", format_ms(player.position - num))

    @commands.hybrid_command(name="replay", aliases=get_aliases("replay"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def replay(self, ctx: commands.Context):
        "Reset the progress of the current song."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.missingPosition", ephemeral=True)

        if not player.current:
            return await send_localized_message(ctx, "player.errors.noTrackPlaying", ephemeral=True)
        
        await player.seek(0)
        await send_localized_message(ctx, "player.controls.replay")

    @commands.hybrid_command(name="shuffle", aliases=get_aliases("shuffle"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def shuffle(self, ctx: commands.Context):
        "Randomizes the tracks in the queue."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            if ctx.author in player.shuffle_votes:
                return await send_localized_message(ctx, "voting.voted", ephemeral=True)
            
            player.shuffle_votes.add(ctx.author)
            if len(player.shuffle_votes) < (required := player.required()):
                return await send_localized_message(ctx, "player.controls.shuffle.vote", ctx.author, len(player.shuffle_votes), required)
        
        await player.shuffle("queue", ctx.author)
        await send_localized_message(ctx, "player.controls.shuffle.success")

    @commands.hybrid_command(name="swap", aliases=get_aliases("swap"))
    @app_commands.describe(
        position1="The track to swap. Example: 2",
        position2="The track to swap with position1. Exmaple: 1"
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def swap(self, ctx: commands.Context, position1: int, position2: int):
        "Swaps the specified song to the specified song."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.missingPosition", ephemeral=True)

        track1, track2 = await player.swap_track(position1, position2, ctx.author)        
        await send_localized_message(ctx, "queue.management.swapped", track1.title, track2.title)

    @commands.hybrid_command(name="move", aliases=get_aliases("move"))
    @app_commands.describe(
        target="The track to move. Example: 2",
        to="The new position to move the track to. Exmaple: 1"
    )
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def move(self, ctx: commands.Context, target: int, to: int):
        "Moves the specified song to the specified position."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)
        
        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.missingPosition", ephemeral=True)

        moved_track = await player.move_track(target, to, ctx.author)
        await send_localized_message(ctx, "queue.management.moved", moved_track, to)

    @commands.hybrid_command(name="lyrics", aliases=get_aliases("lyrics"))
    @app_commands.describe(title="Searches for your query and displays the reutned lyrics.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def lyrics(self, ctx: commands.Context, *, title: str = "", artist: str = ""):
        "Displays lyrics for the playing track."
        if not title:
            player: voicelink.Player = ctx.guild.voice_client
            if not player or not player.is_playing:
                return await send_localized_message(ctx, "player.errors.noTrackPlaying", ephemeral=True)
            
            title = player.current.title
            artist = player.current.author
        
        await ctx.defer()
        lyrics_platform = voicelink.LYRICS_PLATFORMS.get(Config().lyrics_platform)
        if lyrics_platform:
            lyrics = await lyrics_platform().get_lyrics(title, artist)
            if not lyrics:
                return await send_localized_message(ctx, "lyrics.notFound", ephemeral=True)
            
            view = LyricsView(name=title, source={_: re.findall(r'.*\n(?:.*\n){,22}', v or "") for _, v in lyrics.items()}, author=ctx.author)
            view.response = await dispatch_message(ctx, await view.build_embed(), view=view)

    @commands.hybrid_command(name="swapdj", aliases=get_aliases("swapdj"))
    @app_commands.describe(member="Choose a member to transfer the dj role.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def swapdj(self, ctx: commands.Context, member: discord.Member):
        "Transfer dj to another."
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_user_join(ctx.author):
            return await send_localized_message(ctx, "voice.connection.notInChannel", ctx.author.mention, player.channel.mention, ephemeral=True)

        if player.dj.id != ctx.author.id or player.settings.get('dj', False):
            return await send_localized_message(ctx, "permissions.notDj", f"<@&{player.settings['dj']}>" if player.settings.get('dj') else player.dj.mention, ephemeral=True)

        if player.dj.id == member.id or member.bot:
            return await send_localized_message(ctx, "permissions.djToSelf", ephemeral=True)

        if member not in player.channel.members:
            return await send_localized_message(ctx, "permissions.djNotInChannel", member, ephemeral=True)

        player.dj = member
        await send_localized_message(ctx, "permissions.djSwapped", member)

    @commands.hybrid_command(name="autoplay", aliases=["auto", "autodj", *get_aliases("autoplay")])
    @app_commands.describe(mode="Optional: 'on' or 'off' to enable or disable autoplay.")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def autoplay(self, ctx: commands.Context, mode: str = None):
        "Toggles or sets autoplay mode, it will automatically queue the best songs to play."
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.defer()

        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.missingAutoPlay", ephemeral=True)

        curr = bool(player.settings.get("autoplay", False))
        if mode:
            mode_clean = mode.strip().lower()
            if mode_clean in ("on", "enable", "enabled", "true", "yes", "1"):
                check = True
            elif mode_clean in ("off", "disable", "disabled", "false", "no", "0"):
                check = False
            else:
                check = not curr
        else:
            check = not curr

        player.settings['autoplay'] = check
        try:
            await MongoDBHandler.update_settings(ctx.guild.id, {"$set": {"autoplay": check}})
        except Exception:
            pass

        # Real-time WebSocket broadcast to website
        try:
            from web.realtime import RealtimeGateway
            rt = RealtimeGateway.get_instance()
            if rt:
                self.bot.loop.create_task(rt.broadcast("MUSIC_UPDATED", {
                    "guild_id": str(ctx.guild.id),
                    "action": "AUTODJ_TOGGLED",
                    "autoplay": check,
                }))
        except Exception:
            pass

        status_text = await LangHandler.get_lang(ctx.guild.id, "common.status.enabled" if check else "common.status.disabled")
        await send_localized_message(ctx, "player.controls.autoplay", status_text)

        if check and not player.is_playing:
            await player.do_next()
        
        if player.is_ipc_connected:
            await player.send_ws({"op": "toggleAutoplay", "status": check})

    @commands.hybrid_command(name="volume", aliases=["vol", "v", *get_aliases("volume")])
    @app_commands.describe(value="Input a volume percentage between 1 and 150 (leave empty to view current volume).")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def volume(self, ctx: commands.Context, value: commands.Range[int, 1, 150] = None) -> None:
        "View or set the player volume (1-150%)."
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.defer()

        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await send_localized_message(ctx, "player.errors.noPlayer", ephemeral=True)

        if value is None:
            curr_vol = getattr(player, "volume", 100)
            return await dispatch_message(ctx, f"🔊 **Current Volume:** `{curr_vol}%`")

        if not player.is_privileged(ctx.author):
            return await send_localized_message(ctx, "permissions.notDj", ephemeral=True)

        await player.set_volume(value, ctx.author)
        try:
            await MongoDBHandler.update_settings(ctx.guild.id, {"$set": {"volume": value}})
        except Exception:
            pass

        # Real-time WebSocket broadcast to website
        try:
            from web.realtime import RealtimeGateway
            rt = RealtimeGateway.get_instance()
            if rt:
                self.bot.loop.create_task(rt.broadcast("MUSIC_UPDATED", {
                    "guild_id": str(ctx.guild.id),
                    "action": "VOLUME",
                    "volume": value,
                }))
        except Exception:
            pass

        await send_localized_message(ctx, 'settings.actions.volumeSet', value)

    @commands.hybrid_command(name="help", aliases=get_aliases("help"))
    @app_commands.autocomplete(category=help_autocomplete)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def help(self, ctx: commands.Context, category: str = "News") -> None:
        "Lists all the commands in Rem (Your Anime Music Companion)."
        if category not in self.bot.cogs:
            category = "News"
        view = HelpView(self.bot, ctx.author)
        embed = view.build_embed(category)
        view.response = await dispatch_message(ctx, embed, view=view)

    @commands.hybrid_command(name="ping", aliases=get_aliases("ping"))
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def ping(self, ctx: commands.Context):
        "Test if the bot is alive, and see the delay between your commands and my response."
        player: voicelink.Player = ctx.guild.voice_client

        value = await LangHandler.get_lang(ctx.guild.id, "ping.title1", "ping.field1", "ping.title2", "ping.field2")
        
        embed = discord.Embed(color=Config().embed_color)
        embed.add_field(
            name=value[0],
            value=value[1].format(
                "0", "0", self.bot.latency, '😭' if self.bot.latency > 5 else ('😨' if self.bot.latency > 1 else '👌'), "St Louis, MO, United States"
        ))

        if player:
            embed.add_field(
                name=value[2],
                value=value[3].format(
                    player.node._identifier, player.ping, player.node.player_count, player.channel.rtc_region),
                    inline=False
            )

        await dispatch_message(ctx, embed)

    @commands.hybrid_command(name="soundboard", aliases=["sfx", "sb"])
    @app_commands.describe(sound="Select an anime or meme sound effect to play.")
    @app_commands.choices(sound=[
        app_commands.Choice(name="Airhorn 📯", value="airhorn"),
        app_commands.Choice(name="Bruh 🗿", value="bruh"),
        app_commands.Choice(name="Anime Wow ✨", value="anime_wow"),
        app_commands.Choice(name="Tuturu~ 🌸", value="tuturu"),
        app_commands.Choice(name="Nani?! ⚡", value="nani"),
        app_commands.Choice(name="Vine Boom 💥", value="vineboom"),
        app_commands.Choice(name="FBI Open Up 🚨", value="fbi"),
        app_commands.Choice(name="Sheesh 🥶", value="sheesh"),
        app_commands.Choice(name="Roblox OOF 💀", value="oof"),
        app_commands.Choice(name="Victory Fanfare 🏆", value="victory"),
        app_commands.Choice(name="Sad Trombone 🎺", value="sadtrombone"),
        app_commands.Choice(name="Ba-Dum Tss 🥁", value="badumtss"),
    ])
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def soundboard(self, ctx: commands.Context, sound: str = "airhorn") -> None:
        "Plays an instant sound effect into the voice channel."
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.defer()
            except Exception:
                pass

        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            try:
                player = await voicelink.connect_channel(ctx)
            except Exception:
                return await dispatch_message(ctx, "⚠️ Please join a voice channel first!")

        sfx_queries = {
            "airhorn": ("Airhorn 📯", "airhorn sound effect"),
            "bruh": ("Bruh 🗿", "bruh sound effect"),
            "anime_wow": ("Anime Wow ✨", "anime wow sound"),
            "tuturu": ("Tuturu~ 🌸", "steins gate tuturu sound"),
            "nani": ("Nani?! ⚡", "anime nani sound effect"),
            "vineboom": ("Vine Boom 💥", "vine boom sound effect"),
            "fbi": ("FBI Open Up 🚨", "fbi open up sound effect"),
            "sheesh": ("Sheesh 🥶", "sheesh sound effect"),
            "oof": ("Roblox OOF 💀", "roblox oof death sound"),
            "victory": ("Victory 🏆", "final fantasy victory fanfare"),
            "sadtrombone": ("Sad Trombone 🎺", "sad trombone wah wah sound"),
            "badumtss": ("Ba-Dum Tss 🥁", "badum tss joke drum")
        }

        info = sfx_queries.get(sound.lower(), ("Sound Effect 🔊", f"{sound} sound effect"))
        tracks = await player.get_tracks(info[1], requester=ctx.author)
        if not tracks:
            return await dispatch_message(ctx, f"⚠️ Could not load sound effect `{info[0]}`.")

        track = tracks[0] if isinstance(tracks, list) else tracks
        await player.add_track(track, at_front=True)
        if not player.is_playing:
            await player.do_next()

        await dispatch_message(ctx, f"🔊 **Rem** triggered **{info[0]}** in {player.channel.mention}! ✨")

    @commands.hybrid_command(name="aidj", aliases=["remdj", "animedj"])
    @app_commands.describe(mode="Enable or disable Rem's AI Anime DJ commentary announcements ('on' or 'off')")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def aidj(self, ctx: commands.Context, mode: str = None) -> None:
        "Toggles Rem's AI Anime DJ companion mode with voice line announcements."
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.defer()
            except Exception:
                pass

        player: voicelink.Player = ctx.guild.voice_client
        current_val = False
        if player:
            current_val = getattr(player, "ai_dj", False)

        if mode is None:
            new_val = not current_val
        elif mode.lower() in ["on", "enable", "true", "yes"]:
            new_val = True
        else:
            new_val = False

        if player:
            player.ai_dj = new_val

        status_str = "ENABLED 🌸" if new_val else "DISABLED 💤"
        bot_avatar = self.bot.user.display_avatar.url if self.bot and self.bot.user else "https://rai-discord-bot.onrender.com/public/rem_avatar_static.png"
        embed = discord.Embed(
            title=f"🎧 Rem AI Anime DJ — {status_str}",
            description=(
                "🌸 **Rem is now your live AI Anime DJ Companion!**\n"
                "I will introduce songs, share track moods, and announce party updates in chat!"
                if new_val else
                "💤 **AI Anime DJ mode is now paused.** Music will stream quietly without DJ speech bubbles."
            ),
            color=Config().embed_color
        )
        embed.set_thumbnail(url=bot_avatar)
        embed.set_footer(text="Rem 🎧💜 • Your Anime Music Companion", icon_url=bot_avatar)
        await dispatch_message(ctx, embed)

    @commands.hybrid_command(name="radio", aliases=["station", "live"])
    @app_commands.describe(station="Choose a 24/7 anime or lofi radio stream station.")
    @app_commands.choices(station=[
        app_commands.Choice(name="Lofi Girl Chill Beats ☕", value="lofi"),
        app_commands.Choice(name="Tokyo Night Citypop 🌃", value="citypop"),
        app_commands.Choice(name="Top Anime Openings & J-Rock 🌸", value="anime"),
        app_commands.Choice(name="Synthwave & Retrowave 80s 🏎️", value="synthwave"),
        app_commands.Choice(name="Piano & Ghibli Peace 🎹", value="piano"),
    ])
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def radio(self, ctx: commands.Context, station: str = "lofi") -> None:
        "Stream continuous 24/7 anime and lofi radio stations."
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.defer()
            except Exception:
                pass

        stations = {
            "lofi": ("Lofi Girl Chill Beats ☕", "https://www.youtube.com/watch?v=jfKfPfyJRdk"),
            "citypop": ("Tokyo Night Citypop 🌃", "japanese city pop 80s radio live stream"),
            "anime": ("Top Anime Openings & J-Rock 🌸", "anime openings radio live 24/7"),
            "synthwave": ("Synthwave & Retrowave 80s 🏎️", "synthwave radio live 24/7"),
            "piano": ("Piano & Ghibli Peace 🎹", "ghibli piano relaxing music live 24/7")
        }

        info = stations.get(station.lower(), stations["lofi"])
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            try:
                player = await voicelink.connect_channel(ctx)
            except Exception:
                return await dispatch_message(ctx, "⚠️ Please join a voice channel first!")

        tracks = await player.get_tracks(info[1], requester=ctx.author)
        if not tracks:
            tracks = await player.get_tracks(f"{station} radio stream live", requester=ctx.author)

        if not tracks:
            return await dispatch_message(ctx, f"⚠️ Unable to connect to radio station `{info[0]}`.")

        track = tracks[0] if isinstance(tracks, list) else tracks
        await player.add_track(track, at_front=True)
        if not player.is_playing:
            await player.do_next()

        await dispatch_message(ctx, f"📻 **Rem Radio**: Now tuning into **{info[0]}** in {player.channel.mention}! 🌸")

    @commands.hybrid_command(name="sleep", aliases=["timer", "bedtime"])
    @app_commands.describe(minutes="Minutes until Rem automatically stops playback (e.g. 15, 30, 60).")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def sleep(self, ctx: commands.Context, minutes: commands.Range[int, 1, 300] = 30) -> None:
        "Sets a sleep timer to stop playback and disconnect with a gentle fade-out."
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.defer()
            except Exception:
                pass

        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            return await dispatch_message(ctx, "⚠️ Rem is not currently playing in any voice channel!")

        async def _sleep_worker(pl: voicelink.Player, duration: int):
            await asyncio.sleep(max(1, (duration * 60) - 30))
            for _ in range(3):
                if not pl or not pl.is_connected:
                    return
                current_vol = getattr(pl, "volume", 100)
                await pl.set_volume(max(10, current_vol - 25))
                await asyncio.sleep(10)
            if pl and pl.is_connected:
                await pl.teardown()

        asyncio.create_task(_sleep_worker(player, minutes))
        await dispatch_message(ctx, f"🌙 **Bedtime Sleep Timer Active**: Rem will gently fade out and stop in **{minutes} minutes**. Sweet dreams! 🌸")

    @commands.hybrid_command(name="vibe", aliases=["mood"])
    @app_commands.describe(mood="Select or type a mood to auto-generate a queue (e.g. chill, phonk, gym, study, anime).")
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def vibe(self, ctx: commands.Context, mood: str = "anime") -> None:
        "Auto-generates a tailored queue matching your vibe or mood."
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.defer()
            except Exception:
                pass

        mood_queries = {
            "anime": "Top Anime Openings J-Rock Hits playlist",
            "chill": "Lofi Chill Hip Hop Study Beats mix",
            "phonk": "Aggressive Brazilian Phonk Drift playlist",
            "gym": "High Energy Phonk Hardstyle Workout mix",
            "study": "Chilled Cow Lofi Study Session beats",
            "night": "Japanese City Pop 80s Retro Night Drive",
            "gaming": "Electronic High Energy Gaming Bass Boost mix"
        }

        query = mood_queries.get(mood.lower(), f"{mood} music mix playlist")
        player: voicelink.Player = ctx.guild.voice_client
        if not player:
            try:
                player = await voicelink.connect_channel(ctx)
            except Exception:
                return await dispatch_message(ctx, "⚠️ Please join a voice channel first!")

        tracks = await player.get_tracks(query, requester=ctx.author)
        if not tracks:
            return await dispatch_message(ctx, f"⚠️ Could not find tracks for vibe `{mood}`.")

        if isinstance(tracks, list):
            for t in tracks[:10]:
                await player.add_track(t)
            added_count = min(10, len(tracks))
        else:
            await player.add_track(tracks)
            added_count = 1

        if not player.is_playing:
            await player.do_next()

        await dispatch_message(ctx, f"🔮 **Rem Vibe Matcher**: Loaded **{added_count} tracks** for **'{mood.capitalize()}'** vibe in {player.channel.mention}! ✨")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Basic(bot))