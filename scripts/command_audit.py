import sys
import os
import inspect
import asyncio
import json

# Ensure root in sys.path
sys.path.insert(0, os.path.abspath("."))

from core.bot import SentinelBot
import discord
from discord.ext import commands

async def audit_commands():
    bot = SentinelBot()
    # Discover and load cogs to find all commands
    from core.bot import COGS_LIST
    cog_modules = COGS_LIST
    
    loaded_cogs = []
    failed_cogs = []
    
    for mod in sorted(cog_modules):
        try:
            await bot.load_extension(mod)
            loaded_cogs.append(mod)
        except Exception as e:
            failed_cogs.append((mod, str(e)))
            
    print(f"Loaded cogs: {len(loaded_cogs)}, Failed cogs: {len(failed_cogs)}")
    if failed_cogs:
        print("Failed cogs:", failed_cogs)
        
    commands_inventory = []
    
    # 1. Prefix commands
    for cmd in bot.commands:
        module = getattr(cmd.callback, "__module__", "unknown")
        handler = getattr(cmd.callback, "__qualname__", cmd.name)
        checks = [getattr(c, "__qualname__", str(c)) for c in getattr(cmd, "checks", [])]
        cooldown = str(getattr(cmd, "_buckets", None))
        
        # Check source for DB, Discord API, Premium
        try:
            src = inspect.getsource(cmd.callback)
        except Exception:
            src = ""
            
        uses_db = "db" in src or "database" in src
        uses_api = "await ctx." in src or "await interaction." in src or "await channel." in src
        is_premium = "premium" in src.lower() or "entitlement" in src.lower()
        has_error_handling = "try:" in src or hasattr(cmd, "on_error")
        
        status = "WORKING"
        if getattr(cmd, "enabled", True) is False:
            status = "UNUSED"
            
        commands_inventory.append({
            "name": cmd.name,
            "type": "prefix",
            "module": module,
            "handler": handler,
            "permission": ", ".join(checks) if checks else "default",
            "cooldown": cooldown if cooldown != "None" else "none",
            "db_usage": uses_db,
            "api_usage": uses_api,
            "premium": is_premium,
            "response_type": "embed/message",
            "error_handling": has_error_handling,
            "status": status
        })
        
    # 2. Slash / App commands
    for app_cmd in bot.tree.get_commands():
        if isinstance(app_cmd, discord.app_commands.Group):
            for sub in app_cmd.walk_commands():
                module = getattr(sub.callback, "__module__", "unknown") if hasattr(sub, "callback") else "group"
                handler = getattr(sub.callback, "__qualname__", sub.name) if hasattr(sub, "callback") else sub.name
                src = ""
                if hasattr(sub, "callback"):
                    try:
                        src = inspect.getsource(sub.callback)
                    except Exception:
                        pass
                commands_inventory.append({
                    "name": f"{app_cmd.name} {sub.name}",
                    "type": "slash_subcommand",
                    "module": module,
                    "handler": handler,
                    "permission": "slash_default",
                    "cooldown": "default",
                    "db_usage": "db" in src or "database" in src,
                    "api_usage": "response" in src or "interaction" in src,
                    "premium": "premium" in src.lower() or "entitlement" in src.lower(),
                    "response_type": "ephemeral/embed",
                    "error_handling": "try:" in src or "rai_error_handler" in src,
                    "status": "WORKING"
                })
        else:
            module = getattr(app_cmd.callback, "__module__", "unknown") if hasattr(app_cmd, "callback") else "tree"
            handler = getattr(app_cmd.callback, "__qualname__", app_cmd.name) if hasattr(app_cmd, "callback") else app_cmd.name
            src = ""
            if hasattr(app_cmd, "callback"):
                try:
                    src = inspect.getsource(app_cmd.callback)
                except Exception:
                    pass
            commands_inventory.append({
                "name": app_cmd.name,
                "type": "slash_command",
                "module": module,
                "handler": handler,
                "permission": "slash_default",
                "cooldown": "default",
                "db_usage": "db" in src or "database" in src,
                "api_usage": "response" in src or "interaction" in src,
                "premium": "premium" in src.lower() or "entitlement" in src.lower(),
                "response_type": "ephemeral/embed",
                "error_handling": "try:" in src or "rai_error_handler" in src,
                "status": "WORKING"
            })
            
    print(f"Total commands registered across prefix & app commands: {len(commands_inventory)}")
    with open("scripts/command_inventory.json", "w", encoding="utf-8") as f:
        json.dump(commands_inventory, f, indent=2)
    print("Saved scripts/command_inventory.json")

if __name__ == "__main__":
    asyncio.run(audit_commands())
