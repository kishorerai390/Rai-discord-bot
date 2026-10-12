---
name: sentinel-security-audit
description: Audits Rai Sentinel Discord security bot configuration, inspects incident databases, verifies security plugins, and manages hot-reloadable security extensions.
---

# Sentinel Discord Security Audit & Operations Skill

This skill guides AI agents in inspecting, auditing, troubleshooting, and extending the **Rai SentinelBot** Discord security infrastructure.

## Core Security Pillars

1. **Anti-Nuke & Permission Guard**:
   - Monitored channels, mass role deletions, unauthorized channel creations, webhook spam.
   - Enforced by `cogs/security.py` and `cogs/voiceguard.py`.
2. **AutoMod & Content Filtering**:
   - Anti-invite, anti-spam, suspicious phishing links, invisible Unicode/zero-width character sanitization.
   - Enforced by `cogs/automod.py`.
3. **Modular Security Plugin Engine**:
   - Hot-reloadable plugins located in `security_plugins/`.
   - Core engine managed by `core/plugin_engine.py` and slash interface via `cogs/plugins.py`.

---

## When to Use This Skill

Activate this skill when:
- Investigating security alerts delivered to `#🚨・security-report` or `#⚙️・system-report`.
- Authoring, reviewing, or testing new security plugins in `security_plugins/`.
- Verifying database integrity across `data/bot.db` security incident tables.
- Conducting automated health audits of bot permissions, gateway latency, and rate limiter health.

---

## Standard Audit Workflow

### Step 1: Check Security Incidents
Query the SQLite database `data/bot.db` to inspect recent incidents:
```sql
SELECT id, event, user_id, action_taken, timestamp, details
FROM security_logs
ORDER BY id DESC
LIMIT 10;
```

### Step 2: Inspect Security Plugins
Review all active modules in `security_plugins/`:
- `anti_malware_links.py`: Blocks dangerous extensions (`.exe`, `.scr`, `.bat`) and suspicious TLDs.
- `token_leak_sanitizer.py`: Immediate deletion and incident notification for leaked Discord tokens / API keys.
- `alt_account_radar.py`: Flags accounts created < 72 hours ago.

### Step 3: Hot-Reload Plugins on Discord
Administrators can run `/plugin reload <plugin_name>` in Discord to hot-reload code without restarting SentinelBot or causing voice audio interruptions.

---

## Authoring New Security Plugins

To add a new security capability:
1. Create a Python file in `security_plugins/<plugin_name>.py`.
2. Inherit from `BaseSecurityPlugin` in `core.plugin_engine`.
3. Implement `on_message(self, message)` or `on_member_join(self, member)`.
4. Return `False` to intercept / veto the event, or `True` to allow.
5. Hot-reload via `/plugin reload <plugin_name>` or call `engine.load_plugin("<plugin_name>")`.
