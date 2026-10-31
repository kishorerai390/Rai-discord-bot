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
import asyncio
import discord
from pathlib import Path

MEMORY_FILE = Path("data/song_memories.json")


def load_memories() -> dict:
    """Load song memories from the JSON store."""
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_memories(data: dict):
    """Persist song memories to the JSON store."""
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_memory(guild_id: int, track_id: str) -> dict | None:
    """Return the memory dict for a given guild + track, or None if not stored."""
    data = load_memories()
    return data.get(str(guild_id), {}).get(track_id)


def set_memory(guild_id: int, track_id: str, user: str, memory: str):
    """Store a memory for a given guild + track."""
    import datetime
    data = load_memories()
    gid = str(guild_id)
    if gid not in data:
        data[gid] = {}
    data[gid][track_id] = {
        "user": user,
        "memory": memory,
        "date": datetime.datetime.utcnow().isoformat(),
    }
    save_memories(data)


async def ask_for_memory(channel: discord.TextChannel, guild_id: int, track_id: str, track_title: str, bot):
    """Ask users what this song means to them. Waits 60s for a reply."""
    ask_embed = discord.Embed(
        description=(
            f"🌸 **First time playing:** *{track_title}*\n\n"
            "What does this song mean to you?\n"
            "*(Reply in this channel within 60 seconds, or I'll skip asking)*"
        ),
        color=0xb3b3b3,
    )
    ask_embed.set_footer(text="Rem 🎧💜 • Song Memory")
    try:
        ask_msg = await channel.send(embed=ask_embed)

        def check(m):
            return m.channel == channel and not m.author.bot and len(m.content) > 2

        try:
            reply = await bot.wait_for("message", timeout=60.0, check=check)
            set_memory(guild_id, track_id, reply.author.display_name, reply.content[:200])
            confirm = discord.Embed(
                description=f"💜 Memory saved! Next time *{track_title}* plays, I'll remember what you said~",
                color=0xa855f7,
            )
            await channel.send(embed=confirm, delete_after=8)
        except asyncio.TimeoutError:
            await ask_msg.delete()
    except Exception:
        pass
