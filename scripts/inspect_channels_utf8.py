import asyncio, sys, os
sys.path.insert(0, ".")
import discord
from config import DISCORD_TOKEN

async def main():
    async with discord.Client(intents=discord.Intents.default()) as client:
        await client.login(DISCORD_TOKEN)
        guild = await client.fetch_guild(1457382179981099090)
        channels = await guild.fetch_channels()
        categories = [c for c in channels if isinstance(c, discord.CategoryChannel)]
        categories.sort(key=lambda c: c.position)
        
        with open("scripts/channels_structure.txt", "w", encoding="utf-8") as out:
            out.write(f"=== CATEGORIES IN {guild.name} ({len(categories)}) ===\n")
            for cat in categories:
                out.write(f"CAT [{cat.position:2d}] {cat.name} (ID: {cat.id})\n")
                ch_in_cat = [ch for ch in channels if ch.category_id == cat.id]
                ch_in_cat.sort(key=lambda c: c.position)
                for ch in ch_in_cat:
                    t = "VC" if isinstance(ch, discord.VoiceChannel) else "TEXT"
                    out.write(f"   {t:4s} [{ch.position:2d}] {ch.name} (ID: {ch.id})\n")
                    
            orphan_channels = [ch for ch in channels if not ch.category_id and not isinstance(ch, discord.CategoryChannel)]
            if orphan_channels:
                out.write("=== ORPHAN CHANNELS (No Category) ===\n")
                for ch in orphan_channels:
                    t = "VC" if isinstance(ch, discord.VoiceChannel) else "TEXT"
                    out.write(f"   {t:4s} [{ch.position:2d}] {ch.name} (ID: {ch.id})\n")

        print("Wrote scripts/channels_structure.txt successfully.")

if __name__ == "__main__":
    asyncio.run(main())
