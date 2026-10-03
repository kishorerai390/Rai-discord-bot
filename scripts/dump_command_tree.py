import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import discord
from core.bot import SentinelBot

async def dump_tree():
    bot = SentinelBot()
    await bot.setup_hook()

    print("=== REGISTERED COMMANDS IN BOT TREE ===")
    for cmd in sorted(bot.tree.get_commands(), key=lambda c: c.name):
        if isinstance(cmd, discord.app_commands.Group):
            print(f"📁 /{cmd.name}")
            for sub in sorted(cmd.commands, key=lambda s: s.name):
                if isinstance(sub, discord.app_commands.Group):
                    print(f"   📂 /{cmd.name} {sub.name}")
                    for sub2 in sorted(sub.commands, key=lambda s2: s2.name):
                        print(f"      • /{cmd.name} {sub.name} {sub2.name}")
                else:
                    print(f"   • /{cmd.name} {sub.name}")
        else:
            print(f"• /{cmd.name}")

if __name__ == "__main__":
    asyncio.run(dump_tree())
