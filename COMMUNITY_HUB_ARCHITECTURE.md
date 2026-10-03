# RAI COMMUNITY OS — EXTERNAL COMMUNITY HUB ARCHITECTURE

## 1. Executive Summary & Core Principle

**Rai Community OS** is an external persistent web platform connected directly to the Rai / The Raivora Discord bot platform.

```
       Discord Live Hangouts
               │
               ▼
     Rai Discord Gateway Bot
               │
               ▼
    Shared Rai Backend & API (aiohttp)
      ├── SQLite WAL Canonical Database
      ├── Redis Cache & State (optional)
      └── Cloud Fallbacks (PostgreSQL, Firebase)
               ▲
               │
    Rai Community OS Web UI (Port 8080)
```

- **Discord**: Real-time voice channels, text banter, moderation alerts, live gaming sessions, music streaming.
- **Website (Community OS)**: Persistent community identity, creator portfolios, project task management, resource library, community event calendar, idea proposals, knowledge base (Rai Brain), and staff Mission Control.
- **Shared Backend Layer**: Connects Discord bot events and web API calls to the same single source of truth without competing databases.
- **Failure Isolation**: An outage or network timeout on the web frontend never affects the Discord bot, music playback, or security engine.

---

## 2. Security & Authentication Architecture

1. **Discord OAuth2**:
   - Authorization URL generated with `identify guilds` scopes.
   - Access and refresh tokens securely exchanged on backend.
   - Never exposes client secrets to the browser.
2. **Session Storage (`web_sessions`)**:
   - Secure random 32-byte URL-safe token.
   - HttpOnly, SameSite=Lax cookie with 7-day TTL.
   - Server-side permission resolution: dynamically evaluates Discord guild owner and administrator permissions; never trusts frontend-supplied roles.
3. **Privacy Controls**:
   - Visibility modes: `PUBLIC (2)`, `COMMUNITY_ONLY (1)`, `PRIVATE (0)`.
   - Private profiles and private project workspaces are strictly gated at the database query level and completely hidden from public search and Rai Brain.

---

## 3. Database Schema & Migrations

Database operations use SQLite WAL mode with transactions and parameterization.
**Migration 35** adds the persistent platform tables:

| Table | Purpose |
|---|---|
| `web_sessions` | Discord OAuth2 web tokens and authenticated sessions |
| `project_tasks` | Kanban task items (`TODO`, `IN_PROGRESS`, `REVIEW`, `DONE`) |
| `creator_portfolios` | Creator showcases, categories, tools, and external links |
| `community_notifications` | User alerts for invites, RSVPs, task updates, and idea status |
| `community_ideas` | Community proposals with vote counts and comments |
| `idea_votes` | Anti-manipulation user voting records |
| `idea_comments` | Moderated discussion comments on idea proposals |
| `wiki_articles` | Versioned community documentation and guides |
| `community_achievements` | Badges awarded for projects, events, and resources |
| `sync_outbox` | Idempotent transactional event queue for Discord channel sync |
| `community_audit_logs` | Audit trail of administrative and emergency actions |

---

## 4. Web Views & REST API Endpoints

### Navigation & Views
- **Home (`/`)**: Hero banner, live stats, featured projects, creator showcases, and subsystem health matrix.
- **Discover (`/discover`)**: Real-time cross-module search with live filters.
- **Brain (`/brain`)**: AI knowledge assistant indexing verified wiki guides, resources, and projects with source citations.
- **Projects (`/projects`, `/projects/:id`)**: Project workspaces with member lists, Discord deep links, and Kanban boards.
- **Creators (`/creators`, `/creators/:id`)**: Creator portfolios, category filters, and collaboration request modals.
- **Gaming Hub (`/gaming`)**: Live LFG squad finder (Free Fire, BGMI, Roblox, Valorant) with join/leave squad actions.
- **Music Hub (`/music`)**: Curated community playlists and scheduled listening party listings.
- **Media Hub (`/media`)**: Community watch party calendar pointing to legitimate streaming sources.
- **Resource Library (`/resources`)**: Category-filtered repository for editing LUTs, audio packs, and design tools.
- **Events (`/events`, `/events/:id`)**: Upcoming event schedules with instant RSVP registration.
- **Ideas (`/ideas`, `/ideas/:id`)**: Community proposal board with upvoting and threaded discussions.
- **Workspace (`/workspace`)**: Authenticated dashboard displaying my projects, tasks, RSVPs, collaborations, and badges.
- **Profile (`/profile`)**: Bio, skills, games, social links, and privacy settings.
- **Notifications (`/notifications`)**: Inbox with unread indicators and mark-all-read controls.
- **Wiki (`/wiki`)**: Knowledge base reader with version tracking.
- **Status (`/status`)**: Live system status across Gateway, SQLite, Security, and REST API.
- **Labs (`/labs`)**: Interactive **Community Constellation** graph visualizer and safe simulation runner.
- **Mission Control (`/mission-control`)**: Real-time Rai Doctor diagnostics, worker supervisor telemetry, and Global Safe Mode toggle.

---

## 5. Discord Synchronization & Outbox Worker

1. **Transactional Outbox Pattern**:
   When a user creates a project or event on the website, the database record is saved and an event is queued into `sync_outbox` in the same operation.
2. **Background Worker**:
   An asynchronous loop periodically polls `sync_outbox` to create the corresponding Discord channels, categories, or voice rooms if the bot has required permissions.
3. **Idempotency & Retries**:
   - Unique `event_id` ensures no duplicated Discord resources are ever created.
   - If Discord rate-limits or fails, the job retries with exponential backoff up to 5 times.
   - Core website features never wait on Discord API responses.

---

## 6. Verification & Test Suite

The platform is covered by an automated test suite in [`tests/test_community_web_platform.py`](file:///f:/Bot/tests/test_community_web_platform.py):
- `test_01_ui_routes_render_html`: Verified all 18 UI routes render the luxury Midnight UI.
- `test_02_telemetry_stats_and_health`: Validated `/api/stats` and `/health`.
- `test_03_auth_dev_login_and_session`: Tested session cookies, permissions, and logout.
- `test_04_profile_management_and_privacy`: Verified profile updates and `PRIVATE` access denials (403).
- `test_05_projects_tasks_and_outbox_sync`: Tested project creation, Kanban task workflow, and outbox queue.
- `test_06_creator_portfolios`: Validated portfolio submission and creator spotlights.
- `test_07_gaming_lfg_hub`: Tested LFG squad creation, capacity checks, and member joining.
- `test_08_community_events_and_rsvp`: Verified event creation and attendee RSVP tracking.
- `test_09_resource_library`: Tested resource submissions and category queries.
- `test_10_idea_board_and_voting`: Tested idea submissions, voting deltas, and comments.
- `test_11_rai_brain_knowledge_search`: Tested permission-aware multi-source search with citations.
- `test_12_mission_control_and_doctor_diagnostics`: Validated staff-only access, Rai Doctor diagnostics, and safe mode intervention.
- `test_13_community_constellation_graph`: Verified graph nodes and relationships generation.
