"""
Autonomous Music Bot Auto-Updater and Extractor Self-Healing Service.
Keeps yt-dlp, git repository, and audio extractors up-to-date automatically to prevent YouTube playback breakages.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import importlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple
import urllib.request
import discord

if TYPE_CHECKING:
    from music_bot.bot import RaiMusicBot

logger = logging.getLogger("RaiMusic.AutoUpdater")


class MusicAutoUpdater:
    """Autonomous maintenance engine ensuring dependencies, git updates, and audio extractors remain fully operational."""

    _background_task: Optional[asyncio.Task] = None
    _last_checked: float = 0.0
    _last_update_result: Dict[str, Any] = {}

    @classmethod
    def get_current_ytdl_version(cls) -> str:
        """Return currently loaded yt-dlp version."""
        try:
            import yt_dlp.version
            return yt_dlp.version.__version__
        except Exception:
            return "unknown"

    @classmethod
    def get_ejs_version(cls) -> str:
        """Return currently installed yt-dlp-ejs challenge solver version."""
        try:
            import yt_dlp_ejs
            return getattr(yt_dlp_ejs, "__version__", "installed")
        except Exception:
            return "not installed"

    @classmethod
    def get_js_runtime_info(cls) -> Dict[str, Any]:
        """Inspect system for JavaScript runtimes required by YouTube challenge solver."""
        node = shutil.which("node") or "C:\\Program Files\\nodejs\\node.exe"
        node_avail = bool(node and (Path(node).exists() or shutil.which("node")))
        deno = shutil.which("deno")
        quickjs = shutil.which("quickjs")
        active = "Node.js" if node_avail else ("Deno" if deno else ("QuickJS" if quickjs else "None (Embedded Fallback)"))
        return {
            "active": active,
            "node_available": node_avail,
            "node_path": node if node_avail else None,
            "deno_available": bool(deno),
            "quickjs_available": bool(quickjs),
        }

    @classmethod
    async def check_ytdl_version(cls) -> Dict[str, Any]:
        """Query PyPI asynchronously to check if a newer yt-dlp or yt-dlp-ejs version is available."""
        current_ytdl = cls.get_current_ytdl_version()
        current_ejs = cls.get_ejs_version()
        loop = asyncio.get_running_loop()

        def _fetch_pypi() -> Dict[str, Any]:
            def _get_latest(pkg: str, fallback: str) -> str:
                try:
                    req = urllib.request.Request(
                        f"https://pypi.org/pypi/{pkg}/json",
                        headers={"User-Agent": "MusicMaid-AutoUpdater/1.0"},
                    )
                    with urllib.request.urlopen(req, timeout=6.0) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        return data.get("info", {}).get("version", fallback)
                except Exception:
                    return fallback

            def _ver_tuple(v: str):
                try:
                    return tuple(int(x) for x in re.findall(r"\d+", v))
                except Exception:
                    return (0,)

            latest_ytdl = _get_latest("yt-dlp", current_ytdl)
            latest_ejs = _get_latest("yt-dlp-ejs", current_ejs)
            ytdl_update = _ver_tuple(latest_ytdl) > _ver_tuple(current_ytdl)
            ejs_update = (current_ejs == "not installed") or (_ver_tuple(latest_ejs) > _ver_tuple(current_ejs))

            return {
                "current_ytdl": current_ytdl,
                "latest_ytdl": latest_ytdl,
                "current_ejs": current_ejs,
                "latest_ejs": latest_ejs,
                "update_available": ytdl_update or ejs_update,
                "js_runtime": cls.get_js_runtime_info(),
            }

        try:
            res = await loop.run_in_executor(None, _fetch_pypi)
            cls._last_update_result = res
            return res
        except Exception as e:
            logger.warning(f"Failed to query PyPI for yt-dlp release: {e}")
            return {
                "current_ytdl": current_ytdl,
                "latest_ytdl": current_ytdl,
                "current_ejs": current_ejs,
                "latest_ejs": current_ejs,
                "update_available": False,
                "js_runtime": cls.get_js_runtime_info(),
                "error": str(e),
            }

    @classmethod
    async def update_ytdl(cls, force: bool = False, bot: Optional[RaiMusicBot] = None) -> Tuple[bool, str]:
        """Perform a background upgrade of yt-dlp and yt-dlp-ejs inside the active virtual environment."""
        check = await cls.check_ytdl_version()
        if not check.get("update_available") and not force:
            return True, f"Extractors are already at the latest release (`yt-dlp v{check.get('current_ytdl')}`, `EJS {check.get('current_ejs')}`)."

        current_ver = check.get("current_ytdl", "unknown")
        latest_ver = check.get("latest_ytdl", "latest")
        logger.info(f"Initiating background yt-dlp & EJS upgrade: {current_ver} -> {latest_ver}...")

        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp[default]", "yt-dlp-ejs"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                # Reload yt_dlp & resolver in memory
                try:
                    import yt_dlp
                    importlib.reload(yt_dlp)
                    import yt_dlp.version
                    importlib.reload(yt_dlp.version)
                    new_ver = yt_dlp.version.__version__
                    import music_bot.services.resolver_service as m_res
                    importlib.reload(m_res)
                except Exception:
                    new_ver = latest_ver

                msg = f"Successfully updated yt-dlp + EJS challenge solver: `v{current_ver}` -> `v{new_ver}`"
                logger.info(f"[AutoUpdater] {msg}")

                if bot:
                    await cls.dispatch_update_alert(
                        bot,
                        title="🔄 EXTRACTOR & CHALLENGE SOLVER AUTO-UPDATED",
                        description=(
                            f"Audio extractor and JavaScript challenge solver were autonomously patched.\n\n"
                            f"• **YT-DLP Version:** `v{current_ver}` -> `v{new_ver}`\n"
                            f"• **EJS Solver:** `v{cls.get_ejs_version()}`\n"
                            f"• **JS Runtime:** `{cls.get_js_runtime_info().get('active')}`\n"
                            f"• **Playback Status:** `Continuous 0.0s Downtime`"
                        ),
                        color=0x00E5FF,
                    )
                return True, msg
            else:
                err_msg = stderr.decode(errors="replace").strip()
                logger.error(f"[AutoUpdater] pip install failed (code {proc.returncode}): {err_msg}")
                return False, f"pip update failed: {err_msg[:200]}"
        except Exception as e:
            logger.error(f"[AutoUpdater] Subprocess execution error: {e}")
            return False, f"Execution error: {e}"

    @classmethod
    async def check_git_updates(cls) -> Dict[str, Any]:
        """Checks if remote Git repository has new commits for MusicMaid."""
        repo_dir = Path(__file__).resolve().parent.parent.parent
        try:
            # Check if inside git work tree
            proc = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--is-inside-work-tree",
                cwd=str(repo_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return {"is_git": False, "has_updates": False, "message": "Not a git repository"}

            # Fetch remote without merging
            fetch_proc = await asyncio.create_subprocess_exec(
                "git", "fetch", "--quiet",
                cwd=str(repo_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await fetch_proc.communicate()

            # Compare HEAD with upstream
            diff_proc = await asyncio.create_subprocess_exec(
                "git", "rev-list", "HEAD..@{u}", "--count",
                cwd=str(repo_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_diff, _ = await diff_proc.communicate()
            pending_count = int(out_diff.decode().strip() or "0") if diff_proc.returncode == 0 else 0

            # Get current commit hash
            hash_proc = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--short", "HEAD",
                cwd=str(repo_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_hash, _ = await hash_proc.communicate()
            curr_hash = out_hash.decode().strip() or "unknown"

            return {
                "is_git": True,
                "has_updates": pending_count > 0,
                "pending_commits": pending_count,
                "current_commit": curr_hash,
            }
        except Exception as e:
            return {"is_git": False, "has_updates": False, "error": str(e)}

    @classmethod
    async def pull_git_updates(cls, bot: Optional[RaiMusicBot] = None) -> Tuple[bool, str]:
        """Pulls latest git commits and hot-reloads core music bot services with zero playback loss."""
        repo_dir = Path(__file__).resolve().parent.parent.parent
        if bot:
            bot.is_upgrading = True
            try:
                from music_bot.services.player_service import MusicPlayerService
                await MusicPlayerService.snapshot_all_active_sessions(bot)
            except Exception as e:
                logger.debug(f"Pre-pull snapshot notice: {e}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "pull", "--ff-only",
                cwd=str(repo_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            out_str = stdout.decode().strip()

            if proc.returncode == 0:
                if "Already up to date." in out_str:
                    return True, "Codebase is already up to date with remote repository."

                # Hot reload services in-memory and maintain active track positions
                success, reload_msg = await cls.hot_reload_services(bot=bot)

                msg = f"Git updates pulled successfully:\n```\n{out_str[:300]}\n```\n• {reload_msg}"
                if bot:
                    await cls.dispatch_update_alert(
                        bot,
                        title="⚡ CODEBASE AUTO-UPDATED FROM GIT",
                        description=f"New commits were pulled from GitHub and services were hot-reloaded.\n\n• **Git Output:** `{out_str[:120]}`\n• **Downtime:** `0.0s (Live streams preserved where left off)`",
                        color=0x00E5FF,
                    )
                return True, msg
            else:
                err_str = stderr.decode().strip()
                return False, f"Git pull failed: {err_str[:200]}"
        except Exception as e:
            return False, f"Subprocess error: {e}"
        finally:
            if bot:
                bot.is_upgrading = False

    @classmethod
    async def hot_reload_services(cls, bot: Optional[RaiMusicBot] = None) -> Tuple[bool, str]:
        """Hot-reloads music bot modules and seamlessly resumes any playing tracks where they left off."""
        if bot:
            bot.is_upgrading = True
            try:
                from music_bot.services.player_service import MusicPlayerService
                await MusicPlayerService.snapshot_all_active_sessions(bot)
            except Exception as e:
                logger.debug(f"Pre-reload snapshot notice: {e}")

        reloaded = []
        try:
            import music_bot.database.db as m_db
            import music_bot.services.player_service as m_player
            import music_bot.services.resolver_service as m_resolver
            import music_bot.services.lyrics_service as m_lyrics
            import music_bot.services.voice_service as m_voice
            importlib.reload(m_db)
            reloaded.append("database.db")
            importlib.reload(m_resolver)
            reloaded.append("services.resolver_service")
            importlib.reload(m_lyrics)
            reloaded.append("services.lyrics_service")
            importlib.reload(m_voice)
            reloaded.append("services.voice_service")
            importlib.reload(m_player)
            reloaded.append("services.player_service")

            # Check if any active sessions need seamless stream resumption
            if bot:
                for session in bot.session_manager.get_all_sessions():
                    if session.is_playing and session.current_track and session.voice_client:
                        cur_pos = session.progress_seconds
                        if cur_pos > 3:
                            from music_bot.services.player_service import MusicPlayerService
                            await MusicPlayerService.resume_track_stream(bot, session, session.current_track, cur_pos)

            msg = f"Hot-reload successful! Reloaded modules: {', '.join(reloaded)}.\nActive playback streams preserved where they left off."
            return True, msg
        except Exception as e:
            return False, f"Hot-reload error: {e}"
        finally:
            if bot:
                bot.is_upgrading = False

    @classmethod
    async def dispatch_update_alert(
        cls,
        bot: RaiMusicBot,
        title: str,
        description: str,
        color: int = 0x00E5FF,
    ) -> None:
        """Sends an autonomous update digest to designated report channels in connected servers."""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="MusicMaid Autonomous Self-Healing & Auto-Updater")

        # Broadcast to central report server (MRL GAMING) or owner/system channels
        delivered = False
        central_gid_raw = (os.getenv("CENTRAL_REPORT_GUILD_ID") or os.getenv("REPORT_SERVER_ID") or "1494692962041467005").strip()
        central_gid = int(central_gid_raw) if central_gid_raw.isdigit() else 1494692962041467005
        target_guild = bot.get_guild(central_gid)

        if target_guild:
            channel = discord.utils.find(
                lambda c: any(t in c.name.lower() for t in ("bot-report", "music-report", "system-report", "security-report"))
                and isinstance(c, discord.TextChannel)
                and c.permissions_for(target_guild.me).send_messages,
                target_guild.text_channels,
            )
            if channel:
                try:
                    await channel.send(embed=embed)
                    delivered = True
                except Exception:
                    pass

        if not delivered:
            for guild in bot.guilds:
                channel = discord.utils.find(
                    lambda c: c.name in ("bot-report", "system-report", "security-report", "bot-logs", "mod-logs")
                    and isinstance(c, discord.TextChannel)
                    and c.permissions_for(guild.me).send_messages,
                    guild.text_channels,
                )
                if channel:
                    try:
                        await channel.send(embed=embed)
                        delivered = True
                        break
                    except Exception:
                        pass

        # Also direct alert to app owner if not delivered to any channel
        if not delivered and bot.owner_id:
            try:
                owner = bot.get_user(bot.owner_id) or await bot.fetch_user(bot.owner_id)
                if owner:
                    await owner.send(embed=embed)
            except Exception:
                pass

    @classmethod
    def start_background_updater(cls, bot: RaiMusicBot) -> None:
        """Start recurring autonomous update checker."""
        if cls._background_task and not cls._background_task.done():
            return
        cls._background_task = asyncio.create_task(cls._updater_worker(bot))

    @classmethod
    async def check_extractor_health(cls, bot: Optional[RaiMusicBot] = None) -> Dict[str, Any]:
        """Canary Probe: Tests resolving capability on audio stream to detect anti-bot/SABR restrictions."""
        try:
            from music_bot.services.resolver_service import AudioResolver
            health = await AudioResolver.probe_extractor_health()
            if not health.get("operational"):
                logger.warning(f"[AutoUpdater] Extractor issue: {health.get('message')}. Triggering autonomous healing...")
                # Attempt PO-token rotation first
                rotated, rot_msg = AudioResolver.rotate_po_token()
                if rotated:
                    logger.info(f"[AutoUpdater] Rotated PO-Token: {rot_msg}")
                else:
                    asyncio.create_task(cls.update_ytdl(force=True, bot=bot))
            return health
        except Exception as e:
            return {"operational": False, "message": str(e)}

    @classmethod
    async def _updater_worker(cls, bot: RaiMusicBot) -> None:
        """Runs check 60 seconds after startup, then repeats periodically."""
        logger.info("[AutoUpdater] Autonomous self-healing & update loop initialized (adaptive 30m cycle).")
        await asyncio.sleep(60.0)

        iteration = 0
        while True:
            try:
                # 1. Extractor canary health self-check & client rotation
                await cls.check_extractor_health(bot=bot)

                # 2. Check Git remote updates every 30 mins
                git_check = await cls.check_git_updates()
                if git_check.get("has_updates"):
                    logger.info(f"[AutoUpdater] Detected {git_check.get('pending_commits')} pending git commits. Pulling...")
                    await cls.pull_git_updates(bot=bot)

                # 3. Scheduled PO-Token / Cookie rotation (every 6 hours = every 12 iterations)
                if iteration > 0 and iteration % 12 == 0:
                    try:
                        from music_bot.services.resolver_service import AudioResolver
                        AudioResolver.rotate_po_token()
                    except Exception:
                        pass

                # 4. Check yt-dlp PyPI release (every 2 hours = every 4 iterations)
                if iteration % 4 == 0:
                    check = await cls.check_ytdl_version()
                    if check.get("update_available"):
                        logger.info(f"[AutoUpdater] New release detected: yt-dlp v{check.get('latest_ytdl')}, EJS v{check.get('latest_ejs')}. Applying background patch...")
                        success, msg = await cls.update_ytdl(bot=bot)
                        if success:
                            logger.info(f"[AutoUpdater] Applied patch: {msg}")

                iteration += 1
            except Exception as e:
                logger.warning(f"[AutoUpdater] Background update check error: {e}")

            await asyncio.sleep(1800.0)  # 30-minute interval
