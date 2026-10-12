# Sentinel Security Plugin Authoring Guide

All plugins reside in `security_plugins/` and inherit from `BaseSecurityPlugin`.

## Template

```python
from typing import Optional
import discord
from core.plugin_engine import BaseSecurityPlugin

class CustomSecurityPlugin(BaseSecurityPlugin):
    name = "CustomPlugin"
    version = "1.0.0"
    author = "Security Team"
    description = "Inspects specific server threat patterns"

    async def on_load(self) -> None:
        # One-time initialization logic
        pass

    async def on_message(self, message: discord.Message) -> Optional[bool]:
        # Return False to veto message processing (or delete it)
        # Return True or None to allow
        return True

    async def on_member_join(self, member: discord.Member) -> Optional[bool]:
        # Return False to flag member
        return True
```
