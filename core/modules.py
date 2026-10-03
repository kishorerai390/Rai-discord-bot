"""
RAI — MODULE & PLUGIN ARCHITECTURE.
Provides:
- Standardized module interface with version, dependencies, permissions, and lifecycles.
- ModuleManager orchestrating safe dependency-ordered startup and graceful shutdown.
- Failure isolation: non-critical module crashes do not affect core bot stability.
- Prevention of disabling critical security and database components.
- Persistent module registry and per-guild module configuration.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Rai.ModuleManager")


class ModuleStatus(str, Enum):
    UNLOADED = "UNLOADED"
    STARTING = "STARTING"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


@dataclass
class ModuleHealth:
    module_name: str
    status: ModuleStatus
    is_core: bool
    version: str
    dependencies: List[str]
    last_error: Optional[str] = None
    latency_ms: float = 0.0


class RaiModule(ABC):
    """Base interface for all modular Rai subsystems."""

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        is_core: bool = False,
        dependencies: Optional[List[str]] = None,
    ):
        self.name = name.lower().strip()
        self.version = version
        self.is_core = is_core
        self.dependencies = [d.lower().strip() for d in (dependencies or [])]
        self.status = ModuleStatus.UNLOADED
        self.last_error: Optional[str] = None

    @abstractmethod
    async def startup(self, bot: SentinelBot) -> None:
        """Initialize the subsystem, register background tasks or listeners."""
        pass

    @abstractmethod
    async def shutdown(self, bot: SentinelBot) -> None:
        """Gracefully terminate background tasks, release resources."""
        pass

    async def check_health(self, bot: SentinelBot) -> ModuleHealth:
        """Evaluates module operational health."""
        return ModuleHealth(
            module_name=self.name,
            status=self.status,
            is_core=self.is_core,
            version=self.version,
            dependencies=self.dependencies,
            last_error=self.last_error,
        )


class ModuleManager:
    """
    Coordinates registration, dependency graph resolution, startup,
    shutdown, and health tracking across all bot modules.
    """

    _instance: Optional[ModuleManager] = None

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self._modules: Dict[str, RaiModule] = {}
        self._startup_order: List[str] = []

    @classmethod
    def get_instance(cls, bot: SentinelBot) -> ModuleManager:
        if cls._instance is None:
            cls._instance = ModuleManager(bot)
        return cls._instance

    def register(self, module: RaiModule) -> None:
        """Registers a module in the registry."""
        self._modules[module.name] = module
        logger.info(f"Registered module: {module.name} (v{module.version}, core={module.is_core})")

    def _resolve_dependency_order(self) -> List[str]:
        """Calculates topological sort of registered modules based on dependencies."""
        visited: Set[str] = set()
        visiting: Set[str] = set()
        order: List[str] = []

        def dfs(name: str):
            if name in visiting:
                raise ValueError(f"Cyclic dependency detected in module: {name}")
            if name not in visited:
                visiting.add(name)
                mod = self._modules.get(name)
                if mod:
                    for dep in mod.dependencies:
                        if dep in self._modules:
                            dfs(dep)
                        else:
                            logger.warning(f"Module {name} depends on missing module: {dep}")
                visiting.remove(name)
                visited.add(name)
                order.append(name)

        # Core modules first, then others
        core_mods = [m for m, o in self._modules.items() if o.is_core]
        other_mods = [m for m, o in self._modules.items() if not o.is_core]

        for m in core_mods + other_mods:
            if m not in visited:
                dfs(m)
        return order

    async def startup_all(self) -> Dict[str, ModuleStatus]:
        """Starts all modules in dependency order with failure isolation."""
        self._startup_order = self._resolve_dependency_order()
        results: Dict[str, ModuleStatus] = {}

        for mod_name in self._startup_order:
            mod = self._modules[mod_name]
            mod.status = ModuleStatus.STARTING
            try:
                await mod.startup(self.bot)
                mod.status = ModuleStatus.ACTIVE
                logger.info(f"Module '{mod_name}' started successfully.")
            except Exception as e:
                mod.status = ModuleStatus.FAILED
                mod.last_error = str(e)
                logger.error(f"Module '{mod_name}' failed to start: {e}", exc_info=True)
                if mod.is_core:
                    # Critical core module failure
                    logger.critical(f"CORE MODULE '{mod_name}' FAILED TO START. Emergency mode initiated.")
            results[mod_name] = mod.status

            # Persist to database registry
            try:
                await self.bot.db.register_module(
                    module_name=mod.name,
                    version=mod.version,
                    is_core=mod.is_core,
                    is_enabled=mod.status == ModuleStatus.ACTIVE,
                    dependencies=mod.dependencies,
                )
            except Exception as db_err:
                logger.error(f"Failed to record module '{mod_name}' in db: {db_err}")

        return results

    async def shutdown_all(self) -> None:
        """Shuts down all modules in reverse startup order."""
        for mod_name in reversed(self._startup_order):
            mod = self._modules.get(mod_name)
            if mod and mod.status == ModuleStatus.ACTIVE:
                try:
                    await mod.shutdown(self.bot)
                    mod.status = ModuleStatus.STOPPED
                    logger.info(f"Module '{mod_name}' stopped cleanly.")
                except Exception as e:
                    logger.error(f"Error shutting down module '{mod_name}': {e}")
                    mod.status = ModuleStatus.FAILED

    async def get_all_health(self) -> List[ModuleHealth]:
        """Gathers health status across all registered modules."""
        healths = []
        for mod in self._modules.values():
            healths.append(await mod.check_health(self.bot))
        return healths

    def is_module_enabled(self, module_name: str) -> bool:
        mod = self._modules.get(module_name.lower().strip())
        return mod is not None and mod.status == ModuleStatus.ACTIVE

    async def set_guild_module(self, guild_id: int, module_name: str, enabled: bool) -> bool:
        """Enables or disables a non-core module for a guild."""
        mod = self._modules.get(module_name.lower().strip())
        if not mod:
            return False
        if mod.is_core and not enabled:
            raise ValueError(f"Core module '{module_name}' cannot be disabled for server safety.")
        await self.bot.db.set_guild_module_enabled(guild_id, mod.name, enabled)
        return True
