# Sentinel Bot Threat Matrix & Escalation Protocol

| Severity | Threat Type | Automated Action | Notification Target |
|---|---|---|---|
| **CRITICAL** | Mass Channel/Role Deletion (Raid) | Auto-ban rogue account, restore role/channel from atomic backup | `#🚨・security-report` & Owner DM |
| **CRITICAL** | Webhook Token / Bot Secret Leak | Immediate message deletion, purge webhook | `#🚨・security-report` & Chat Alert |
| **HIGH** | Executable/Trojan File Attachment | Message deleted, user warned, incident logged | `#🚨・security-report` |
| **HIGH** | Phishing / Nitro Scam Link | Message deleted, user muted for 10m | `#🚨・security-report` |
| **MEDIUM** | Discord Server Invite Spam | Message deleted, invite code logged | `#🤖・bot-report` |
| **LOW** | Brand New Account Join (< 72h) | Monitored in low-trust watchlist | `#🤖・bot-report` |
