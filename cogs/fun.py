"""
Advanced Fun, Games & Entertainment Cog.
Features:
- /8ball with varied responses & cooldowns
- /coinflip with betting choice, UI buttons & database win tracking
- /dice rolling with custom faces & "Roll Again" interactive button
- /meme with high quality curated memes & "Next Meme" button
- /joke (Dad jokes, Programming, Puns) with "Another Joke" button
- /trivia interactive quiz with buttons (A, B, C, D) & leaderboard score tracking
- /rps (Rock Paper Scissors) interactive buttons & win counter
- /ship affinity scoring with visual progress bars
- /poll interactive polls with real-time upvote/downvote buttons
- /fun leaderboard displaying top gamers in the server
- /fun config to enable/disable or toggle family-friendly mode
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, List, Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Colors
from utils.cooldowns import CooldownScope
from utils.embeds import create_embed, error_embed, info_embed, success_embed, warning_embed
from utils.permissions import is_admin_or_owner

if TYPE_CHECKING:
    from main import SentinelBot

# ==========================================
# CONSTANTS & CONTENT DATA
# ==========================================

EIGHT_BALL_ANSWERS = [
    "It is certain.",
    "It is decidedly so.",
    "Without a doubt.",
    "Yes definitely.",
    "You may rely on it.",
    "As I see it, yes.",
    "Most likely.",
    "Outlook good.",
    "Yes.",
    "Signs point to yes.",
    "Reply hazy, try again.",
    "Ask again later.",
    "Better not tell you now.",
    "Cannot predict now.",
    "Concentrate and ask again.",
    "Don't count on it.",
    "My reply is no.",
    "My sources say no.",
    "Outlook not so good.",
    "Very doubtful.",
]

JOKES = {
    "programming": [
        ("Why do programmers prefer dark mode?", "Because light attracts bugs."),
        ("How many programmers does it take to change a light bulb?", "None. It's a hardware problem."),
        ("There are 10 types of people in the world:", "Those who understand binary, and those who don't."),
        ("Why did the programmer quit his job?", "Because he didn't get arrays."),
        ("A SQL query walks into a bar, walks up to two tables and asks...", "'Can I join you?'"),
        ("Why do Java developers wear glasses?", "Because they don't C#."),
        ("What is the programmer's favorite hangout place?", "Foo Bar."),
    ],
    "dad": [
        ("Why don't skeletons fight each other?", "They don't have the guts."),
        ("What do you call a fake noodle?", "An impasta."),
        ("Why did the scarecrow win an award?", "Because he was outstanding in his field."),
        ("What do you call cheese that isn't yours?", "Nacho cheese."),
        ("Why can't a bicycle stand on its own?", "It's two-tired."),
        ("How does a penguin build its house?", "Igloos it together."),
    ],
    "puns": [
        ("I'm reading a book on anti-gravity.", "I just can't put it down."),
        ("I told my doctor that I broke my arm in two places.", "He told me to stop going to those places."),
        ("Time flies like an arrow.", "Fruit flies like a banana."),
        ("I used to play piano by ear...", "Now I use my hands."),
        ("I was going to tell a time travel joke...", "But you didn't like it."),
    ],
}

MEMES = [
    {
        "title": "When the code compiles on the first try",
        "url": "https://images.unsplash.com/photo-1534972195531-a756b1126f24?auto=format&fit=crop&w=800&q=80",
        "caption": "Wait... something must be terribly wrong.",
    },
    {
        "title": "Git push --force on Friday at 5 PM",
        "url": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=800&q=80",
        "caption": "Some men just want to watch the server burn.",
    },
    {
        "title": "Bug in Production vs Bug in Local Dev",
        "url": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=800&q=80",
        "caption": "Works on my machine! ¯\\_(ツ)_/¯",
    },
    {
        "title": "Closing 47 StackOverflow tabs after finding the semicolon",
        "url": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=800&q=80",
        "caption": "Inner peace achieved.",
    },
]

TRIVIA_QUESTIONS = [
    {
        "question": "What is the primary language used to build Discord bots?",
        "options": ["Python", "HTML", "CSS", "SQL"],
        "answer": 0,
        "explanation": "Python (discord.py) and JavaScript (discord.js) are the most popular!",
    },
    {
        "question": "In computer science, what does 'API' stand for?",
        "options": [
            "Application Programming Interface",
            "Advanced Protocol Integration",
            "Automated Program Instruction",
            "Apple Private Identifier",
        ],
        "answer": 0,
        "explanation": "API stands for Application Programming Interface.",
    },
    {
        "question": "Which company originally created the Python programming language?",
        "options": ["Guido van Rossum (Individual)", "Microsoft", "Google", "Sun Microsystems"],
        "answer": 0,
        "explanation": "Python was created by Dutch programmer Guido van Rossum in 1991.",
    },
    {
        "question": "What is the maximum message length for a regular Discord user?",
        "options": ["2,000 characters", "1,000 characters", "4,000 characters", "500 characters"],
        "answer": 0,
        "explanation": "Regular users have a 2,000 character limit; Nitro users have 4,000.",
    },
    {
        "question": "Which port does HTTPS default to?",
        "options": ["443", "80", "8080", "22"],
        "answer": 0,
        "explanation": "Port 443 is the standard port for secure web traffic (HTTPS).",
    },
    {
        "question": "What does SQLite's WAL mode stand for?",
        "options": ["Write-Ahead Logging", "Wide Access Lock", "Window Allocation Layer", "Web App Link"],
        "answer": 0,
        "explanation": "WAL stands for Write-Ahead Logging, providing superior concurrency and speed.",
    },
]


# ==========================================
# INTERACTIVE UI VIEWS
# ==========================================

class NextMemeView(discord.ui.View):
    """Interactive button to roll another meme."""

    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id

    @discord.ui.button(label="Next Meme 🔁", style=discord.ButtonStyle.primary)
    async def next_meme(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command user can request the next meme.", ephemeral=True)
            return

        meme = random.choice(MEMES)
        embed = create_embed(
            title=f"😂 {meme['title']}",
            description=f"*{meme['caption']}*",
            color=Colors.PRIMARY,
            image_url=meme["url"],
        )
        await interaction.response.edit_message(embed=embed, view=self)


class NextJokeView(discord.ui.View):
    """Interactive button to fetch another joke."""

    def __init__(self, author_id: int, category: str):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.category = category

    @discord.ui.button(label="Another Joke 🃏", style=discord.ButtonStyle.secondary)
    async def another_joke(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command runner can fetch another joke.", ephemeral=True)
            return

        cat_list = JOKES.get(self.category, JOKES["programming"])
        setup, punchline = random.choice(cat_list)
        embed = create_embed(
            title=f"🤣 {self.category.capitalize()} Joke",
            description=f"**{setup}**\n\n||{punchline}||",
            color=Colors.PRIMARY,
        )
        embed.set_footer(text="Click the spoiler to reveal punchline!")
        await interaction.response.edit_message(embed=embed, view=self)


class TriviaView(discord.ui.View):
    """Multiple choice trivia buttons (A, B, C, D)."""

    def __init__(self, bot: SentinelBot, author_id: int, question_data: dict):
        super().__init__(timeout=30)
        self.bot = bot
        self.author_id = author_id
        self.q = question_data
        self.answered = False

    async def _handle_answer(self, interaction: discord.Interaction, chosen_idx: int):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This trivia question is for someone else!", ephemeral=True)
            return

        if self.answered:
            return
        self.answered = True

        for child in self.children:
            child.disabled = True

        correct_idx = self.q["answer"]
        if chosen_idx == correct_idx:
            await self.bot.db.record_fun_win(interaction.guild.id, interaction.user.id, "trivia")
            embed = success_embed(
                "Correct Answer! 🎉",
                f"**Question:** {self.q['question']}\n\n"
                f"✅ **{self.q['options'][correct_idx]}**\n\n"
                f"*{self.q['explanation']}*\n\n"
                f"+1 win added to your server leaderboard profile!",
            )
        else:
            embed = error_embed(
                "Incorrect! ❌",
                f"**Question:** {self.q['question']}\n\n"
                f"Your Answer: ~~{self.q['options'][chosen_idx]}~~\n"
                f"Correct Answer: **{self.q['options'][correct_idx]}**\n\n"
                f"*{self.q['explanation']}*",
            )

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary)
    async def btn_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_answer(interaction, 0)

    @discord.ui.button(label="B", style=discord.ButtonStyle.primary)
    async def btn_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_answer(interaction, 1)

    @discord.ui.button(label="C", style=discord.ButtonStyle.primary)
    async def btn_c(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_answer(interaction, 2)

    @discord.ui.button(label="D", style=discord.ButtonStyle.primary)
    async def btn_d(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_answer(interaction, 3)


class RPSView(discord.ui.View):
    """Rock Paper Scissors interactive button view."""

    def __init__(self, bot: SentinelBot, author_id: int):
        super().__init__(timeout=30)
        self.bot = bot
        self.author_id = author_id

    async def _play(self, interaction: discord.Interaction, user_choice: str):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command runner can choose.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True

        bot_choice = random.choice(["rock", "paper", "scissors"])
        emojis = {"rock": "🪨 Rock", "paper": "📰 Paper", "scissors": "✂️ Scissors"}

        if user_choice == bot_choice:
            outcome = "It's a Tie! 🤝"
            embed = info_embed(outcome, f"You chose **{emojis[user_choice]}**\nBot chose **{emojis[bot_choice]}**")
        elif (
            (user_choice == "rock" and bot_choice == "scissors")
            or (user_choice == "paper" and bot_choice == "rock")
            or (user_choice == "scissors" and bot_choice == "paper")
        ):
            outcome = "You Won! 🏆"
            await self.bot.db.record_fun_win(interaction.guild.id, interaction.user.id, "rps")
            embed = success_embed(
                outcome,
                f"You chose **{emojis[user_choice]}**\nBot chose **{emojis[bot_choice]}**\n\n+1 RPS win recorded!",
            )
        else:
            outcome = "Bot Won! 🤖"
            embed = error_embed(
                outcome,
                f"You chose **{emojis[user_choice]}**\nBot chose **{emojis[bot_choice]}**\n\nBetter luck next time!",
            )

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Rock", emoji="🪨", style=discord.ButtonStyle.secondary)
    async def rock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "rock")

    @discord.ui.button(label="Paper", emoji="📰", style=discord.ButtonStyle.secondary)
    async def paper_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "paper")

    @discord.ui.button(label="Scissors", emoji="✂️", style=discord.ButtonStyle.secondary)
    async def scissors_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "scissors")


class ReRollDiceView(discord.ui.View):
    """Button to roll the dice again."""

    def __init__(self, author_id: int, sides: int, count: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.sides = sides
        self.count = count

    @discord.ui.button(label="Roll Again 🎲", style=discord.ButtonStyle.primary)
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command runner can re-roll.", ephemeral=True)
            return

        rolls = [random.randint(1, self.sides) for _ in range(self.count)]
        total = sum(rolls)
        embed = create_embed(
            title="🎲 Dice Roll",
            description=f"Rolled **{self.count}d{self.sides}**:\nResults: `{' + '.join(map(str, rolls))}` = **{total}**",
            color=Colors.INFO,
        )
        await interaction.response.edit_message(embed=embed, view=self)


class PollView(discord.ui.View):
    """Interactive voting view for polls with real-time counters."""

    def __init__(self, author_id: int):
        super().__init__(timeout=86400)
        self.author_id = author_id
        self.yes_votes: set[int] = set()
        self.no_votes: set[int] = set()

    def _update_labels(self):
        self.yes_button.label = f"👍 Yes ({len(self.yes_votes)})"
        self.no_button.label = f"👎 No ({len(self.no_votes)})"

    @discord.ui.button(label="👍 Yes (0)", style=discord.ButtonStyle.success)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        self.no_votes.discard(uid)
        if uid in self.yes_votes:
            self.yes_votes.remove(uid)
        else:
            self.yes_votes.add(uid)
        self._update_labels()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="👎 No (0)", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        self.yes_votes.discard(uid)
        if uid in self.no_votes:
            self.no_votes.remove(uid)
        else:
            self.no_votes.add(uid)
        self._update_labels()
        await interaction.response.edit_message(view=self)


# ==========================================
# MAIN FUN COG
# ==========================================

class FunCog(commands.Cog, name="Fun"):
    """Fun & Community Entertainment Commands."""

    def __init__(self, bot: SentinelBot):
        self.bot = bot

    async def _check_cooldown_and_enabled(
        self, interaction: discord.Interaction, cmd_name: str, cooldown_sec: float = 3.0
    ) -> bool:
        """Check if fun module is enabled and applies rate limiting."""
        guild_id = interaction.guild.id
        fun_cfg = await self.bot.db.get_fun_config(guild_id)
        if not fun_cfg.fun_enabled:
            await interaction.response.send_message(
                embed=warning_embed("Fun Module Disabled", "Fun commands have been disabled on this server by staff."),
                ephemeral=True,
            )
            return False

        limited, retry_after = await self.bot.cooldowns.check_and_reserve(
            scope=CooldownScope.USER_GUILD_CMD,
            command=f"fun_{cmd_name}",
            user_id=interaction.user.id,
            guild_id=guild_id,
            cooldown_seconds=cooldown_sec,
        )
        if limited:
            await interaction.response.send_message(
                f"⏳ Please wait `{retry_after}s` before running `/{cmd_name}` again.",
                ephemeral=True,
            )
            return False
        return True

    # ==========================================
    # COMMANDS
    # ==========================================

    @app_commands.command(name="8ball", description="Ask the Magic 8-Ball a question")
    @app_commands.describe(question="The question you want answered")
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        if not await self._check_cooldown_and_enabled(interaction, "8ball", 3.0):
            return

        answer = random.choice(EIGHT_BALL_ANSWERS)
        embed = create_embed(
            title="🎱 Magic 8-Ball",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=f"*{answer}*", inline=False)
        embed.set_footer(text=f"Asked by {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip", description="Flip a coin with an optional bet")
    @app_commands.describe(choice="Call Heads or Tails before flipping")
    @app_commands.choices(
        choice=[
            app_commands.Choice(name="Heads", value="heads"),
            app_commands.Choice(name="Tails", value="tails"),
        ]
    )
    async def coinflip(self, interaction: discord.Interaction, choice: Optional[app_commands.Choice[str]] = None):
        if not await self._check_cooldown_and_enabled(interaction, "coinflip", 3.0):
            return

        result = random.choice(["heads", "tails"])
        title = "🪙 Coin Flip"

        if choice:
            user_pick = choice.value
            if user_pick == result:
                await self.bot.db.record_fun_win(interaction.guild.id, interaction.user.id, "coinflip")
                desc = f"The coin landed on **{result.upper()}**!\n\n🎉 **You guessed correctly!** (+1 coinflip win recorded)"
                color = Colors.SUCCESS
            else:
                desc = f"The coin landed on **{result.upper()}**.\n\n❌ You called {user_pick.capitalize()}. Better luck next time!"
                color = Colors.ERROR
        else:
            desc = f"The coin landed on **{result.upper()}**!"
            color = Colors.GOLD

        embed = create_embed(title=title, description=desc, color=color)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="dice", description="Roll dice with custom sides and counts")
    @app_commands.describe(sides="Number of sides per die (default: 6)", count="Number of dice to roll (default: 1)")
    async def dice(self, interaction: discord.Interaction, sides: Optional[int] = 6, count: Optional[int] = 1):
        if not await self._check_cooldown_and_enabled(interaction, "dice", 2.0):
            return

        valid_sides = max(2, min(sides or 6, 100))
        valid_count = max(1, min(count or 1, 10))

        rolls = [random.randint(1, valid_sides) for _ in range(valid_count)]
        total = sum(rolls)

        embed = create_embed(
            title="🎲 Dice Roll",
            description=f"Rolled **{valid_count}d{valid_sides}**:\nResults: `{' + '.join(map(str, rolls))}` = **{total}**",
            color=Colors.INFO,
        )
        embed.set_footer(text=f"Rolled by {interaction.user.display_name}")
        view = ReRollDiceView(interaction.user.id, valid_sides, valid_count)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="meme", description="Display a gaming, tech, or wholesome meme")
    async def meme(self, interaction: discord.Interaction):
        if not await self._check_cooldown_and_enabled(interaction, "meme", 4.0):
            return

        meme_data = random.choice(MEMES)
        embed = create_embed(
            title=f"😂 {meme_data['title']}",
            description=f"*{meme_data['caption']}*",
            color=Colors.PRIMARY,
            image_url=meme_data["url"],
        )
        view = NextMemeView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="joke", description="Hear a joke (programming, dad jokes, or puns)")
    @app_commands.describe(category="Choose a joke category")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Programming", value="programming"),
            app_commands.Choice(name="Dad Jokes", value="dad"),
            app_commands.Choice(name="Puns", value="puns"),
        ]
    )
    async def joke(self, interaction: discord.Interaction, category: Optional[app_commands.Choice[str]] = None):
        if not await self._check_cooldown_and_enabled(interaction, "joke", 3.0):
            return

        cat_key = category.value if category else "programming"
        cat_jokes = JOKES.get(cat_key, JOKES["programming"])
        setup, punchline = random.choice(cat_jokes)

        embed = create_embed(
            title=f"🤣 {cat_key.capitalize()} Joke",
            description=f"**{setup}**\n\n||{punchline}||",
            color=Colors.PRIMARY,
        )
        embed.set_footer(text="Click the spoiler to reveal punchline!")
        view = NextJokeView(interaction.user.id, cat_key)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="trivia", description="Answer a trivia question and climb the server leaderboard")
    async def trivia(self, interaction: discord.Interaction):
        if not await self._check_cooldown_and_enabled(interaction, "trivia", 5.0):
            return

        q = random.choice(TRIVIA_QUESTIONS)
        options_text = "\n".join([f"**{chr(65 + i)}.** {opt}" for i, opt in enumerate(q["options"])])

        embed = create_embed(
            title="🧠 Tech & Discord Trivia Quiz",
            description=f"### {q['question']}\n\n{options_text}\n\n*Click your answer below within 30 seconds!*",
            color=Colors.INFO,
        )
        embed.set_footer(text="Earn points on the server /fun leaderboard!")
        view = TriviaView(self.bot, interaction.user.id, q)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="rps", description="Play Rock, Paper, Scissors against Sentinel Bot")
    async def rps(self, interaction: discord.Interaction):
        if not await self._check_cooldown_and_enabled(interaction, "rps", 3.0):
            return

        embed = create_embed(
            title="✂️ Rock, Paper, Scissors",
            description="Choose your move by clicking a button below!",
            color=Colors.PRIMARY,
        )
        view = RPSView(self.bot, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="ship", description="Calculate the love / compatibility percentage between two users")
    @app_commands.describe(user1="First user", user2="Second user")
    async def ship(self, interaction: discord.Interaction, user1: discord.Member, user2: discord.Member):
        if not await self._check_cooldown_and_enabled(interaction, "ship", 3.0):
            return

        seed = user1.id + user2.id
        rng = random.Random(seed)
        percentage = rng.randint(0, 100)

        filled = percentage // 10
        empty = 10 - filled
        bar = "❤️" * filled + "🖤" * empty

        if percentage >= 85:
            verdict = "💖 A match made in heaven!"
        elif percentage >= 60:
            verdict = "😍 Strong sparks are flying!"
        elif percentage >= 40:
            verdict = "🙂 There is potential here."
        else:
            verdict = "💔 Better off as friends."

        embed = create_embed(
            title="💘 Compatibility Matchmaker",
            description=f"**{user1.display_name}** + **{user2.display_name}**\n\n**{percentage}%** {bar}\n\n*{verdict}*",
            color=Colors.SECURITY,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="poll", description="Create an interactive community poll with voting buttons")
    @app_commands.describe(question="The question for members to vote on")
    async def poll(self, interaction: discord.Interaction, question: str):
        if not await self._check_cooldown_and_enabled(interaction, "poll", 10.0):
            return

        embed = create_embed(
            title="📊 Community Poll",
            description=f"**{question}**\n\nClick the buttons below to cast your vote!",
            color=Colors.PRIMARY,
        )
        embed.set_footer(text=f"Poll created by {interaction.user.name}")
        view = PollView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    # ==========================================
    # FUN LEADERBOARD & CONFIGURATION
    # ==========================================

    fun_group = app_commands.Group(
        name="fun",
        description="Fun module settings and leaderboard",
    )

    @fun_group.command(name="leaderboard", description="Display the top mini-game and trivia champions in this server")
    async def leaderboard(self, interaction: discord.Interaction):
        stats = await self.bot.db.get_fun_leaderboard(interaction.guild.id, limit=10)
        if not stats:
            await interaction.response.send_message(
                embed=info_embed("Leaderboard Empty", "No one has played trivia, coinflip, or RPS yet! Be the first by running `/trivia`."),
                ephemeral=True,
            )
            return

        lines = []
        for rank, s in enumerate(stats, 1):
            total_wins = s.trivia_wins + s.coinflip_wins + s.rps_wins
            member = interaction.guild.get_member(s.user_id)
            name = member.display_name if member else f"User {s.user_id}"
            lines.append(
                f"`{rank}.` **{name}** — **{total_wins} Wins** "
                f"*(Trivia: {s.trivia_wins} | RPS: {s.rps_wins} | Coinflip: {s.coinflip_wins})*"
            )

        embed = create_embed(
            title=f"🏆 Mini-Game Champions — {interaction.guild.name}",
            description="\n".join(lines),
            color=Colors.GOLD,
        )
        await interaction.response.send_message(embed=embed)

    @fun_group.command(name="config", description="Configure fun module availability and family-friendly settings")
    @is_admin_or_owner()
    @app_commands.describe(
        enabled="Enable or disable fun commands in this server",
        family_friendly="Enforce family-friendly mode",
    )
    async def fun_config_cmd(
        self,
        interaction: discord.Interaction,
        enabled: Optional[bool] = None,
        family_friendly: Optional[bool] = None,
    ):
        updates = {}
        if enabled is not None:
            updates["fun_enabled"] = int(enabled)
        if family_friendly is not None:
            updates["family_friendly"] = int(family_friendly)

        if not updates:
            cfg = await self.bot.db.get_fun_config(interaction.guild.id)
            embed = info_embed(
                "Fun Module Configuration",
                f"**Fun Enabled:** {'🟢 Yes' if cfg.fun_enabled else '🔴 No'}\n"
                f"**Family-Friendly Mode:** {'🟢 Yes' if cfg.family_friendly else '🔴 No'}",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await self.bot.db.update_fun_config(interaction.guild.id, **updates)
        await interaction.response.send_message(
            embed=success_embed("Configuration Updated", "Fun module settings have been saved successfully."),
            ephemeral=True,
        )


async def setup(bot: SentinelBot):
    await bot.add_cog(FunCog(bot))
