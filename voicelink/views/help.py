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

import discord
from discord.ext import commands

from ..config import Config

class HelpDropdown(discord.ui.Select):
    def __init__(self, categories: list[str]) -> None:
        self.view: HelpView

        super().__init__(
            placeholder="Select Category!",
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(emoji="🆕", label="News", description="View new updates of Rem."),
                discord.SelectOption(emoji="🕹️", label="Tutorial", description="How to use Rem (Your Anime Music Companion)."),
            ] + [
                discord.SelectOption(emoji=emoji, label=f"{category} Commands", description=f"This is {category.lower()} Category.")
                for category, emoji in zip(categories, ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"])
            ],
            custom_id="select"
        )
    
    async def callback(self, interaction: discord.Interaction) -> None:
        embed = self.view.build_embed(self.values[0].split(" ")[0])
        await interaction.response.edit_message(embed=embed)

class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author: discord.Member) -> None:
        super().__init__(timeout=60)

        self.author: discord.Member = author
        self.bot: commands.Bot = bot
        self.response: discord.Message = None
        self.categories: list[str] = [ name.capitalize() for name, cog in bot.cogs.items() if len([c for c in cog.walk_commands()]) ]

        self.add_item(discord.ui.Button(label='Website', emoji='🌎', url='https://rai-music-rgpzau.v2.appdeploy.ai/'))
        self.add_item(discord.ui.Button(label='Github', emoji=':github:1098265017268322406', url='https://github.com/kishorerai390/Rai-discord-bot'))
        self.add_item(discord.ui.Button(label='Support Server', emoji='💬', url='https://discord.gg/wRCgB7vBQv'))
        self.add_item(HelpDropdown(self.categories))

    async def on_timeout(self) -> None:
        for child in self.children:
            if child.custom_id == "select":
                child.disabled = True
        try:
            await self.response.edit(view=self)
        except:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> None:
        return interaction.user == self.author

    def build_embed(self, category: str) -> discord.Embed:
        category = category.lower()
        if category == "news":
            embed = discord.Embed(title="🌸 Rem Help Menu | Your Anime Music Companion", url="https://github.com/kishorerai390/Rai-discord-bot", color=Config().embed_color)
            embed.add_field(
                name=f"Available Categories: [{2 + len(self.categories)}]",
                value="```py\n👉 News\n2. Tutorial\n{}```".format("".join(f"{i}. {c}\n" for i, c in enumerate(self.categories, start=3))),
                inline=True
            )

            update = "Rem is your adorable anime-inspired AI music companion with studio-grade playback, custom playlists, audio filters, and seamless queue management! 🎧💜"
            embed.add_field(name="📰 Information:", value=update, inline=True)
            embed.add_field(name="Get Started", value="```Join a voice channel and /play {Song/URL} a song. (Track names, search queries, YouTube, Spotify, and playlist links are fully supported)```", inline=False)
            
            embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else "https://rai-discord-bot.onrender.com/public/rem_avatar_static.png")
            embed.set_footer(text="Rem 🎧💜 • Your Anime Music Companion • /help", icon_url=self.bot.user.display_avatar.url if self.bot.user else None)
            return embed

        embed = discord.Embed(title=f"Category: {category.capitalize()}", color=Config().embed_color)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else "https://rai-discord-bot.onrender.com/public/rem_avatar_static.png")
        embed.set_footer(text="Rem 🎧💜 • Your Anime Music Companion • /help", icon_url=self.bot.user.display_avatar.url if self.bot.user else None)
        embed.add_field(name=f"Categories: [{2 + len(self.categories)}]", value="```py\n" + "\n".join(("👉 " if c == category.capitalize() else f"{i}. ") + c for i, c in enumerate(['News', 'Tutorial'] + self.categories, start=1)) + "```", inline=True)

        if category == 'tutorial':
            embed.description = "How to use Rem? Here are the essential commands and tutorials to get you started! 🎧💜"
            embed.set_image(url="https://cdn.discordapp.com/attachments/674788144931012638/917656288899514388/final_61aef3aa7836890135c6010c_669380.gif")
        else:
            cog = [c for _, c in self.bot.cogs.items() if _.lower() == category][0]

            commands = [command for command in cog.walk_commands()]
            embed.description = cog.description
            embed.add_field(
                name=f"{category} Commands: [{len(commands)}]",
                value="```{}```".format("".join(f"/{command.qualified_name}\n" for command in commands if not command.qualified_name == cog.qualified_name))
            )

        return embed