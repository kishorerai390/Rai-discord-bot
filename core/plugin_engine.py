"""
Security Plugin Engine for Rai SentinelBot.
Provides isolated, hot-reloadable modular security extensions with lifecycle hooks.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

import discord

if TYPE_CHECKING:
    from core.bot import SentinelBot

logger = logging.getLogger("Sentinel.PluginEngine")


class BaseSecurityPlugin(ABC):
    """Abstract base class for all native Sentinel security plugins."""

    name: str = "BasePlugin"
    version: str = "1.0.0"
    author: str = "Sentinel Team"
    description: str = "Base security plugin"

    def __init__(self, bot: SentinelBot):
        self.bot = bot
        self.enabled: bool = True
        self.loaded_at: float = time.time()
        self.intercept_count: int = 0
        self.events_processed: int = 0
        self.error_count: int = 0

    async def on_load(self) -> None:
        """Called immediately after plugin instantiation."""
        pass

    async def on_unload(self) -> None:
        """Called before plugin is removed or reloaded."""
        pass

    async def on_message(self, message: discord.Message) -> Optional[bool]:
        """
        Intercept incoming message.
        Return False to block/veto further message processing.
        Return True or None to allow.
        """
        return True

    async def on_member_join(self, member: discord.Member) -> Optional[bool]:
        """
        Intercept new member join.
        Return False to flag or trigger quarantine.
        Return True or None to allow.
        """
        return True

    def get_metrics(self) -> Dict[str, Any]:
        """Return diagnostic metrics for reporting."""
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "enabled": self.enabled,
            "events_processed": self.events_processed,
            "intercept_count": self.intercept_count,
            "error_count": self.error_count,
            "uptime_seconds": int(time.time() - self.loaded_at),
        }


class SecurityPluginEngine:
    """Manages discovery, loading, unloading, and lifecycle hooks for security plugins."""

    def __init__(self, bot: SentinelBot, plugins_dir: Optional[Path] = None):
        self.bot = bot
        self.plugins_dir = plugins_dir or Path("security_plugins")
        self.plugins: Dict[str, BaseSecurityPlugin] = {}
        self._modules: Dict[str, Any] = {}

    async def load_all(self) -> int:
        """Discover and load all plugins in the plugins directory."""
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        count = 0

        for file_path in self.plugins_dir.glob("*.py"):
            if file_path.name.startswith("__"):
                continue
            plugin_name = file_path.stem
            try:
                success = await self.load_plugin(plugin_name)
                if success:
                    count += 1
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_name}: {e}", exc_info=True)

        logger.info(f"Security Plugin Engine initialized: {count} active plugins.")
        return count

    async def load_plugin(self, plugin_name: str) -> bool:
        """Dynamically load or instantiate a security plugin."""
        module_path = f"security_plugins.{plugin_name}"
        try:
            if module_path in sys.modules:
                mod = importlib.reload(sys.modules[module_path])
            else:
                mod = importlib.import_module(module_path)

            self._modules[plugin_name] = mod

            # Locate BaseSecurityPlugin subclass
            plugin_cls: Optional[Type[BaseSecurityPlugin]] = None
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    inspect.isclass(attr)
                    and issubclass(attr, BaseSecurityPlugin)
                    and attr is not BaseSecurityPlugin
                ):
                    plugin_cls = attr
                    break

            if not plugin_cls:
                logger.warning(f"No BaseSecurityPlugin subclass found in {module_path}")
                return False

            instance = plugin_cls(self.bot)
            await instance.on_load()
            self.plugins[plugin_name] = instance
            logger.info(f"Loaded security plugin: '{instance.name}' v{instance.version} [{plugin_name}]")
            return True

        except Exception as e:
            logger.error(f"Error loading plugin {plugin_name}: {e}", exc_info=True)
            return False

    async def unload_plugin(self, plugin_name: str) -> bool:
        """Gracefully unload a security plugin."""
        plugin = self.plugins.get(plugin_name)
        if not plugin:
            return False

        try:
            await plugin.on_unload()
        except Exception as e:
            logger.error(f"Error during on_unload for plugin {plugin_name}: {e}")

        self.plugins.pop(plugin_name, None)
        logger.info(f"Unloaded security plugin: {plugin_name}")
        return True

    async def reload_plugin(self, plugin_name: str) -> bool:
        """Hot-reload a security plugin from disk."""
        await self.unload_plugin(plugin_name)
        return await self.load_plugin(plugin_name)

    async def dispatch_message(self, message: discord.Message) -> bool:
        """
        Dispatch message to all active plugins.
        Returns False if ANY plugin vetos/blocks the message.
        """
        allow = True
        for name, plugin in list(self.plugins.items()):
            if not plugin.enabled:
                continue
            try:
                plugin.events_processed += 1
                res = await plugin.on_message(message)
                if res is False:
                    plugin.intercept_count += 1
                    allow = False
            except Exception as e:
                plugin.error_count += 1
                logger.error(f"Plugin '{name}' raised error on message: {e}", exc_info=True)
        return allow

    async def dispatch_member_join(self, member: discord.Member) -> bool:
        """
        Dispatch member join to all active plugins.
        Returns False if ANY plugin flags the member.
        """
        allow = True
        for name, plugin in list(self.plugins.items()):
            if not plugin.enabled:
                continue
            try:
                plugin.events_processed += 1
                res = await plugin.on_member_join(member)
                if res is False:
                    plugin.intercept_count += 1
                    allow = False
            except Exception as e:
                plugin.error_count += 1
                logger.error(f"Plugin '{name}' raised error on member_join: {e}", exc_info=True)
        return allow

    def get_all_metrics(self) -> List[Dict[str, Any]]:
        """Return metrics for all registered plugins."""
        return [p.get_metrics() for p in self.plugins.values()]
