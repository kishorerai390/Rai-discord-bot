import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import discord
from discord.ext import commands
from music_bot.commands.music_cog import MusicCog
from music_bot.commands.session_cog import MusicSessionCog


async def dump_tree():
    bot = commands.Bot(command_prefix="m!", intents=discord.Intents.default(), help_command=None)
    bot.db = MagicMock()
    bot.session_manager = MagicMock()

    await bot.add_cog(MusicCog(bot))
    try:
        await bot.add_cog(MusicSessionCog(bot))
    except Exception as e:
        print(f"Notice: MusicSessionCog load note: {e}")

    commands_list = sorted(bot.tree.get_commands(), key=lambda c: c.name)
    print(f"\n=== REGISTERED COMMANDS IN MUSICMAID BOT TREE ({len(commands_list)} root items) ===")
    for cmd in commands_list:
        if isinstance(cmd, discord.app_commands.Group):
            print(f"📁 /{cmd.name} (Group)")
            for sub in sorted(cmd.commands, key=lambda s: s.name):
                if isinstance(sub, discord.app_commands.Group):
                    print(f"   📂 /{cmd.name} {sub.name}")
                    for sub2 in sorted(sub.commands, key=lambda s2: s2.name):
                        print(f"      • /{cmd.name} {sub.name} {sub2.name}")
                else:
                    print(f"   • /{cmd.name} {sub.name} - {sub.description}")
        else:
            print(f"• /{cmd.name} - {cmd.description}")

    prefix_cmds = sorted(bot.commands, key=lambda c: c.name)
    print(f"\n=== REGISTERED PREFIX COMMANDS ({len(prefix_cmds)} items) ===")
    for pcmd in prefix_cmds:
        aliases_str = f" (aliases: {', '.join(pcmd.aliases)})" if pcmd.aliases else ""
        print(f"• m!{pcmd.name}{aliases_str}")


if __name__ == "__main__":
    asyncio.run(dump_tree())

