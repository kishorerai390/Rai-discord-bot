import discord
import voicelink
from discord.ext import commands

from voicelink.config import Config


class HomeSearchModal(discord.ui.Modal, title="Search for a song"):
    query = discord.ui.TextInput(label="Song name or URL", placeholder="e.g. Kalyani or a YouTube link", max_length=300)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        member = interaction.user
        if not interaction.guild or not getattr(member, "voice", None) or not member.voice.channel:
            return await interaction.followup.send("Join a voice channel first, then try searching again. 🎧", ephemeral=True)
        try:
            player = interaction.guild.voice_client
            if player is None:
                player = await voicelink.connect_channel(interaction, member.voice.channel)
            elif player.channel.id != member.voice.channel.id:
                return await interaction.followup.send(f"I'm already playing in {player.channel.mention}. Join that channel first. 💜", ephemeral=True)
            player.context = interaction
            tracks = await player.get_tracks(str(self.query.value).strip(), requester=member)
            if not tracks:
                return await interaction.followup.send("I couldn't find a playable match. Try another title or URL.", ephemeral=True)
            if isinstance(tracks, voicelink.Playlist):
                await player.add_track(tracks.tracks)
                result = f"Added {len(tracks.tracks)} tracks from {tracks.name} to the queue."
            else:
                await player.add_track(tracks[0])
                result = f"Added {tracks[0].title} to the queue."
            if not player.is_playing:
                await player.do_next()
            await interaction.followup.send(result, ephemeral=True)
        except Exception:
            await interaction.followup.send("I couldn't start that song right now. Please try /play or check the bot logs.", ephemeral=True)


class RemHomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Continue where I left off", emoji="▶️", style=discord.ButtonStyle.success)
    async def continue_playing(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message("Use this inside your server.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        player = interaction.guild.voice_client
        member = interaction.user
        if not getattr(member, "voice", None) or not member.voice.channel:
            return await interaction.followup.send("Join a voice channel first so I know where to play. 🎧", ephemeral=True)
        if player and player.channel.id != member.voice.channel.id:
            return await interaction.followup.send(f"I'm connected to {player.channel.mention}. Join that channel first, or ask me to move.", ephemeral=True)
        if player is None:
            return await interaction.followup.send("No saved session is active right now. Use Search for a song or /play to start music. 💜", ephemeral=True)
        if player.is_paused:
            await player.set_pause(False, member)
        elif not player.is_playing:
            await player.do_next()
        await player.invoke_controller()
        await interaction.followup.send("You're back in, let's play! 🎶", ephemeral=True)

    @discord.ui.button(label="Search for a song", emoji="🔎", style=discord.ButtonStyle.primary)
    async def search_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(HomeSearchModal())


class Home(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="home", description="Show Rem's music home card.")
    async def home(self, ctx: commands.Context):
        embed = discord.Embed(title="💜 Rem — Your Anime Music Companion", description="### Ready for music? (•ᴗ•) 🌸\nJump back into your session or search for a song below.\n\n🎧 Join a voice channel before starting a new track.", color=Config().embed_color)
        embed.set_thumbnail(url="https://rai-discord-bot.onrender.com/public/musicmaid_avatar.jpg")
        embed.set_footer(text="Rem 🎧💜 • Your Anime Music Companion", icon_url="https://rai-discord-bot.onrender.com/public/musicmaid_avatar.jpg")
        await ctx.send(embed=embed, view=RemHomeView())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Home(bot))
