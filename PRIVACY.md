# Privacy Policy for MusicMaid

**Effective Date:** October 14, 2026  
**Application:** MusicMaid Discord Music Bot & Platform  
**Developer Team:** Rai Discord Bot / Kishore  

---

## 1. Data Minimization Commitment

We believe in strict data minimization. MusicMaid processes and stores only the minimum technical identifiers strictly required to provide audio playback, maintain server song queues, and remember server equalizer and prefix preferences.

---

## 2. Information We Collect

| Data Field | Purpose | Retention |
| :--- | :--- | :--- |
| **Server ID (Guild ID)** | Associates active voice sessions, custom prefix, volume level, and song queues with your Discord server. | Retained while bot is in server. Permanently deleted when the bot is removed. |
| **Channel ID** | Directs playback embeds, interactive button controls, and status notices to the correct channel. | Ephemeral session memory. |
| **User ID** | Tracks track requesters and preserves personal playlist favorites if explicitly saved. | Stored until manually deleted by the user. |
| **Song Queue & History** | Allows playback queue resumption across bot reboots and displays `/history`. | Stored in local encrypted SQLite database. |

---

## 3. What We NEVER Collect

- **NO Voice Recording:** We do **NOT** listen to, record, intercept, or store any microphone audio or voice communications in voice channels.
- **NO Direct Messages:** We do **NOT** read, store, or monitor user private direct messages (DMs).
- **NO Personal Identifiable Information:** We do **NOT** collect real names, email addresses, phone numbers, passwords, physical locations, or IP addresses.
- **NO Data Selling or Advertising:** We do **NOT** sell, rent, monetize, or share user data with data brokers or third-party advertisers.

---

## 4. Third-Party Services

To resolve song requests, MusicMaid communicates with third-party service APIs:

- **Discord API:** Voice gateway transmission, user interaction responses, and slash command routing.
- **YouTube & SoundCloud:** Resolving publicly accessible audio streams requested by users.
- **Spotify Web API:** Reading public track and album metadata (track names and artists).

---

## 5. User Data Deletion Rights (GDPR & CCPA Compliant)

You maintain complete control over your data:

- **Server Removal:** Kicking or banning MusicMaid from your Discord server permanently removes all server session settings and queue history.
- **Self-Service Clear:** Server administrators can wipe all stored playlist queues at any time with `/clear` or `/playlist delete`.
- **Manual Request:** Users can request full deletion of their stored favorites or history by contacting the developer via `/support`.

---

## 6. Updates to this Policy

We may periodically update this policy to reflect new capabilities or Discord Developer Policy changes. Any revisions will be published here with an updated effective date.
