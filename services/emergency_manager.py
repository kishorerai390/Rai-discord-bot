"""
RAI — EMERGENCY CONTROLS & SAFE MODE CONTROLLER
Provides administrator emergency interventions, module-level maintenance locks,
and global Safe Mode isolation.

In Safe Mode:
1. Commands continue.
2. Database continues.
3. Diagnostics continue.
4. Basic moderation continues.
5. High-risk automation pauses.
6. Scheduled jobs pause.
7. External providers pause.
8. Report spam is fully blocked.
9. Dynamic VC cleanup remains safe.
10. Music can be paused.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("Rai.Emergency")


class EmergencyManager:
    """Singleton managing global and guild-level emergency safe mode and module maintenance."""

    _instance: Optional[EmergencyManager] = None

    def __init__(self) -> None:
        self.global_safe_mode: bool = False
        self.safe_mode_started_at: Optional[float] = None
        self.safe_mode_actor: Optional[str] = None
        self.module_maintenance: Dict[str, Dict[str, Any]] = {}
        self.paused_workers: Set[str] = set()

    @classmethod
    def get_instance(cls) -> EmergencyManager:
        if cls._instance is None:
            cls._instance = EmergencyManager()
        return cls._instance

    def is_safe_mode_active(self) -> bool:
        return self.global_safe_mode

    def toggle_safe_mode(self, enabled: bool, actor: str = "Admin") -> bool:
        self.global_safe_mode = enabled
        if enabled:
            self.safe_mode_started_at = time.time()
            self.safe_mode_actor = actor
            logger.warning(f"[EMERGENCY] Global Safe Mode ACTIVATED by {actor}")
        else:
            self.safe_mode_started_at = None
            self.safe_mode_actor = None
            logger.info(f"[EMERGENCY] Global Safe Mode DEACTIVATED by {actor}")
        return self.global_safe_mode

    def is_module_under_maintenance(self, module_name: str) -> bool:
        norm = module_name.strip().lower()
        if self.global_safe_mode and norm in ("automation", "workflow", "backups", "music"):
            return True
        info = self.module_maintenance.get(norm)
        return bool(info and info.get("enabled", False))

    def set_module_maintenance(self, module_name: str, enabled: bool, actor: str = "Admin", reason: Optional[str] = None) -> bool:
        norm = module_name.strip().lower()
        self.module_maintenance[norm] = {
            "enabled": enabled,
            "actor": actor,
            "reason": reason or ("Manual maintenance" if enabled else "Restored to service"),
            "updated_at": time.time(),
        }
        logger.warning(f"[MAINTENANCE] Module '{norm}' maintenance set to {enabled} by {actor}")
        return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "safe_mode": self.global_safe_mode,
            "safe_mode_started_at": self.safe_mode_started_at,
            "safe_mode_actor": self.safe_mode_actor,
            "module_maintenance": self.module_maintenance,
            "paused_workers": list(self.paused_workers),
        }
