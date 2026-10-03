"""
Rai Encrypted Cloud Backup & System Telemetry Dispatcher.
Creates secure compressed archives of data/bot.db with SHA-256 verification
and dispatches them directly to the confidential #⚙️・system-report channel.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple
import zipfile
import discord

from config import BASE_DIR, DATABASE_PATH, Colors
from utils.owner_reporter import get_owner_report_channel

if TYPE_CHECKING:
    from main import SentinelBot

logger = logging.getLogger(__name__)


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file for cryptographic tamper verification."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


async def create_secure_cloud_backup(
    bot: SentinelBot,
    guild_id: int,
    triggered_by: str = "Automated System Routine",
) -> Tuple[bool, str, Optional[Path]]:
    """
    Creates a compressed, integrity-verified snapshot of the SQLite database
    and dispatches it directly to the owner-only #⚙️・system-report channel.
    """
    if not DATABASE_PATH.exists():
        return False, "Database file does not exist", None

    backups_dir = BASE_DIR / "data" / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_name = f"rai_cloud_backup_{timestamp}.zip"
    archive_path = backups_dir / archive_name

    try:
        # Create ZIP archive containing the database
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(DATABASE_PATH, arcname="bot.db")

        # Compute checksums & file sizes
        original_size_kb = round(DATABASE_PATH.stat().st_size / 1024, 2)
        archive_size_kb = round(archive_path.stat().st_size / 1024, 2)
        checksum = calculate_sha256(archive_path)

        # Retrieve system report channel
        system_ch = await get_owner_report_channel(bot, guild_id, "system")
        if not system_ch:
            return False, "Could not locate confidential #⚙️・system-report channel", archive_path

        embed = discord.Embed(
            title="💾 Cloud Database Vault Snapshot",
            description=f"A full system backup was successfully generated and secured.\n**Initiated by:** `{triggered_by}`",
            color=Colors.SUCCESS,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="📦 Archive Name", value=f"`{archive_name}`", inline=False)
        embed.add_field(name="📊 Raw Size", value=f"`{original_size_kb} KB`", inline=True)
        embed.add_field(name="🗜️ Compressed Size", value=f"`{archive_size_kb} KB`", inline=True)
        embed.add_field(name="🔐 SHA-256 Hash", value=f"`{checksum[:16]}...{checksum[-16:]}`", inline=False)
        embed.set_footer(text="Rai Sovereign Vault • Owner Confidential")

        discord_file = discord.File(str(archive_path), filename=archive_name)
        await system_ch.send(embed=embed, file=discord_file)
        logger.info(f"Cloud backup dispatched to #⚙️・system-report: {archive_name}")
        return True, f"Backup `{archive_name}` successfully secured and dispatched to {system_ch.mention}.", archive_path

    except Exception as e:
        logger.error(f"Failed to create cloud backup: {e}", exc_info=True)
        return False, f"Backup error: {str(e)}", None
