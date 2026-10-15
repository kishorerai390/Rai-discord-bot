import asyncio
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from music_bot.services.resolver_service import AudioResolver, get_active_cookie_file, _load_po_tokens_and_cookies

logging.basicConfig(level=logging.INFO)

async def main():
    cookie_file = get_active_cookie_file()
    print("Active cookie file:", cookie_file)
    health = await AudioResolver.probe_extractor_health()
    print("Health result:", health)

asyncio.run(main())
