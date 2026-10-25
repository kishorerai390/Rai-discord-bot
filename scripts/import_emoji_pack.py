"""Upload a locally downloaded emoji pack to a Discord guild you administer.

Usage (run locally, not on Render):
  set DISCORD_BOT_TOKEN=...
  python scripts/import_emoji_pack.py ./my-emoji-pack --guild-id YOUR_GUILD_ID

The bot needs Create Expressions permission in the target guild. Never commit the token.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

import aiohttp

# Support running this file directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_bot.emoji_pack import eligible_images, emoji_name, image_data_uri  # noqa: E402

API_BASE = "https://discord.com/api/v10"


async def upload_pack(folder: Path, guild_id: str, token: str) -> int:
    if not folder.is_dir():
        raise ValueError(f"Emoji folder does not exist: {folder}")
    images = eligible_images(folder.rglob("*"))
    if not images:
        raise ValueError("No PNG, JPEG, GIF, or WebP files found in the selected folder")

    headers = {"Authorization": f"Bot {token}", "User-Agent": "RaiEmojiPackImporter/1.0"}
    timeout = aiohttp.ClientTimeout(total=30)
    created = 0
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        for path in images:
            try:
                data_uri = image_data_uri(path.name, path.read_bytes())
            except ValueError as exc:
                print(f"SKIP {path.name}: {exc}")
                continue

            payload = {"name": emoji_name(path.name), "image": data_uri}
            url = f"{API_BASE}/guilds/{guild_id}/emojis"
            async with session.post(url, json=payload) as response:
                if response.status == 429:
                    result = await response.json()
                    wait = max(1.0, float(result.get("retry_after", 1)))
                    await asyncio.sleep(wait)
                    async with session.post(url, json=payload) as retry:
                        body = await retry.json(content_type=None)
                        status = retry.status
                else:
                    body = await response.json(content_type=None)
                    status = response.status

            if status in (200, 201) and isinstance(body, dict) and body.get("id"):
                name = body.get("name", payload["name"])
                emoji_id = body["id"]
                animated = bool(body.get("animated"))
                markup = f"<{'a' if animated else ''}:{name}:{emoji_id}>"
                env_key = name.upper()
                print(f"EMOJI_{env_key}={markup}")
                created += 1
            else:
                message = body.get("message", "unknown error") if isinstance(body, dict) else "unexpected response"
                print(f"SKIP {path.name}: Discord API HTTP {status}: {message}")
                if status in (401, 403, 404):
                    print("Stopping: check the bot token, guild ID, and Create Expressions permission.")
                    break
            await asyncio.sleep(0.35)
    print(f"\nUploaded {created} emoji(s). Copy the printed EMOJI_* mappings into the bot service environment.")
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a locally downloaded emoji pack to your Discord guild")
    parser.add_argument("folder", type=Path, help="Folder containing extracted emoji images")
    parser.add_argument("--guild-id", required=True, help="Discord server ID you administer")
    args = parser.parse_args()
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        parser.error("Set DISCORD_BOT_TOKEN in your local shell; do not put it in source code")
    try:
        asyncio.run(upload_pack(args.folder, args.guild_id, token))
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
