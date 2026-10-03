"""
Single-instance process lock for Rai Discord Bot.
Prevents multiple instances from running concurrently, which causes duplicate
Discord gateway events, duplicate responses, and audit log spam.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("SentinelBot.InstanceLock")

DEFAULT_LOCK_PORT = 49451
LOCK_FILE_PATH = Path(".bot.lock")


class InstanceAlreadyRunningError(Exception):
    """Raised when another instance of the bot is already active."""
    pass


class SingleInstanceLock:
    """
    Enforces a single running instance of the bot using an OS-managed loopback socket
    and a PID tracker file.
    
    Why loopback socket:
    - Atomically enforced by the OS kernel.
    - If the process terminates, crashes, or is killed via taskkill/SIGKILL,
      the OS immediately releases the socket, guaranteeing zero stale lock issues.
    """

    def __init__(self, port: int = DEFAULT_LOCK_PORT, lock_file: Path = LOCK_FILE_PATH):
        self.port = port
        self.lock_file = lock_file
        self._sock: Optional[socket.socket] = None
        self._acquired = False

    def acquire(self) -> bool:
        """
        Attempts to acquire the single-instance lock.
        Raises InstanceAlreadyRunningError if another instance holds the lock.
        """
        if self._acquired:
            return True

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # We do NOT set SO_REUSEADDR on Windows loopback to guarantee exclusive bind
        try:
            self._sock.bind(("127.0.0.1", self.port))
            self._sock.listen(0)
            self._acquired = True
            
            # Record current PID in lockfile
            try:
                self.lock_file.write_text(f"{os.getpid()}", encoding="utf-8")
            except Exception as e:
                logger.debug(f"Could not write PID lockfile: {e}")

            logger.info(f"Single-instance lock acquired on 127.0.0.1:{self.port} (PID: {os.getpid()})")
            return True
        except (socket.error, OSError):
            existing_pid = "Unknown"
            if self.lock_file.exists():
                try:
                    existing_pid = self.lock_file.read_text(encoding="utf-8").strip()
                except Exception:
                    pass

            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None

            msg = (
                f"Another instance of Rai Bot is already running (PID: {existing_pid}, Port: {self.port}). "
                "Only one instance is permitted to run simultaneously to prevent duplicate messages and event spam."
            )
            logger.error(msg)
            raise InstanceAlreadyRunningError(msg)

    def release(self) -> None:
        """Releases the instance lock and cleans up."""
        if not self._acquired:
            return

        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

        if self.lock_file.exists():
            try:
                self.lock_file.unlink()
            except Exception:
                pass

        self._acquired = False
        logger.info("Single-instance lock released.")

    def __enter__(self) -> SingleInstanceLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
