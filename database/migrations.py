"""
Database migrations system for the Discord Bot.
Tracks schema version, performs forward migrations inside transactions, and supports backups.
"""

from __future__ import annotations

import datetime
import logging
import shutil
from pathlib import Path
from typing import List, Tuple
import aiosqlite

from config import BACKUPS_DIR

logger = logging.getLogger(__name__)

# List of migration definitions: (version, description, sql_statements)
MIGRATIONS: List[Tuple[int, str, List[str]]] = [
    (
        1,
        "Initial base schema with security, automod, logging, moderation, and tickets",
        [
            # 1. Guild Config
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                security_enabled INTEGER NOT NULL DEFAULT 1,
                automod_enabled INTEGER NOT NULL DEFAULT 0,
                welcome_enabled INTEGER NOT NULL DEFAULT 0,
                autorole_enabled INTEGER NOT NULL DEFAULT 0,
                tickets_enabled INTEGER NOT NULL DEFAULT 0,
                music_enabled INTEGER NOT NULL DEFAULT 1,
                emergency_stop INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """,
            # 2. Security Config
            """
            CREATE TABLE IF NOT EXISTS security_config (
                guild_id INTEGER PRIMARY KEY,
                channel_delete_limit INTEGER NOT NULL DEFAULT 5,
                channel_delete_window INTEGER NOT NULL DEFAULT 10,
                channel_create_limit INTEGER NOT NULL DEFAULT 10,
                channel_create_window INTEGER NOT NULL DEFAULT 10,
                role_delete_limit INTEGER NOT NULL DEFAULT 5,
                role_delete_window INTEGER NOT NULL DEFAULT 10,
                role_create_limit INTEGER NOT NULL DEFAULT 10,
                role_create_window INTEGER NOT NULL DEFAULT 10,
                ban_limit INTEGER NOT NULL DEFAULT 5,
                ban_window INTEGER NOT NULL DEFAULT 10,
                kick_limit INTEGER NOT NULL DEFAULT 5,
                kick_window INTEGER NOT NULL DEFAULT 10,
                webhook_limit INTEGER NOT NULL DEFAULT 3,
                webhook_window INTEGER NOT NULL DEFAULT 10,
                punishment TEXT NOT NULL DEFAULT 'alert',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            # 3. Security Whitelist
            """
            CREATE TABLE IF NOT EXISTS security_whitelist (
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_type TEXT NOT NULL CHECK(target_type IN ('user', 'role')),
                added_by INTEGER NOT NULL,
                added_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, target_id, target_type),
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_security_whitelist_guild
            ON security_whitelist(guild_id);
            """,
            # 4. Security Incidents
            """
            CREATE TABLE IF NOT EXISTS security_incidents (
                event_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                executor_id INTEGER,
                executor_name TEXT,
                target_id INTEGER,
                target_name TEXT,
                action TEXT NOT NULL,
                detected_count INTEGER,
                threshold INTEGER,
                audit_log_id INTEGER,
                reason TEXT,
                automated_action TEXT,
                result TEXT,
                severity TEXT NOT NULL DEFAULT 'medium',
                audit_verified INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_security_incidents_guild_time
            ON security_incidents(guild_id, timestamp);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_security_incidents_executor
            ON security_incidents(guild_id, executor_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_security_incidents_type
            ON security_incidents(guild_id, event_type);
            """,
            # 5. Security State
            """
            CREATE TABLE IF NOT EXISTS security_state (
                guild_id INTEGER PRIMARY KEY,
                emergency_stop INTEGER NOT NULL DEFAULT 0,
                lockdown_enabled INTEGER NOT NULL DEFAULT 0,
                lockdown_started_at TEXT,
                emergency_started_at TEXT,
                changed_by INTEGER,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            # 6. Rate Limit Config
            """
            CREATE TABLE IF NOT EXISTS rate_limit_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                scope TEXT NOT NULL,
                action TEXT NOT NULL,
                limit_count INTEGER NOT NULL,
                window_seconds INTEGER NOT NULL,
                cooldown_seconds INTEGER NOT NULL DEFAULT 0,
                persistent INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(guild_id, scope, action),
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            # 7. Persistent Cooldowns
            """
            CREATE TABLE IF NOT EXISTS persistent_cooldowns (
                guild_id INTEGER NOT NULL,
                user_id INTEGER,
                action TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id, action),
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_persistent_cooldowns_expiry
            ON persistent_cooldowns(expires_at);
            """,
            # 8. Violation History
            """
            CREATE TABLE IF NOT EXISTS violation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                executor_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                violation_count INTEGER NOT NULL DEFAULT 1,
                first_violation_at TEXT NOT NULL,
                last_violation_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_violation_history_executor
            ON violation_history(guild_id, executor_id, event_type);
            """,
            # 9. Moderation Warnings
            """
            CREATE TABLE IF NOT EXISTS moderation_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_warnings_user
            ON moderation_warnings(guild_id, user_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_warnings_expiry
            ON moderation_warnings(expires_at);
            """,
            # 10. Welcome Config
            """
            CREATE TABLE IF NOT EXISTS welcome_config (
                guild_id INTEGER PRIMARY KEY,
                welcome_channel_id INTEGER,
                goodbye_channel_id INTEGER,
                welcome_message TEXT,
                goodbye_message TEXT,
                autorole_id INTEGER,
                dm_enabled INTEGER NOT NULL DEFAULT 0,
                embed_enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            # 11. Logging Config
            """
            CREATE TABLE IF NOT EXISTS logging_config (
                guild_id INTEGER PRIMARY KEY,
                general_channel_id INTEGER,
                moderation_channel_id INTEGER,
                security_channel_id INTEGER,
                automod_channel_id INTEGER,
                member_channel_id INTEGER,
                message_channel_id INTEGER,
                voice_channel_id INTEGER,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            # 12. Ticket Config
            """
            CREATE TABLE IF NOT EXISTS ticket_config (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER,
                log_channel_id INTEGER,
                support_role_id INTEGER,
                transcript_enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            # 13. Tickets
            """
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL UNIQUE,
                creator_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                closed_at TEXT,
                closed_by INTEGER,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            # 14. Bot Config
            """
            CREATE TABLE IF NOT EXISTS bot_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT NOT NULL
            );
            """,
            # 15. AutoMod Config
            """
            CREATE TABLE IF NOT EXISTS automod_config (
                guild_id INTEGER PRIMARY KEY,
                spam_detection INTEGER NOT NULL DEFAULT 1,
                spam_limit INTEGER NOT NULL DEFAULT 5,
                spam_window INTEGER NOT NULL DEFAULT 5,
                mention_limit INTEGER NOT NULL DEFAULT 5,
                repeated_limit INTEGER NOT NULL DEFAULT 3,
                banned_words_enabled INTEGER NOT NULL DEFAULT 1,
                invite_links_block INTEGER NOT NULL DEFAULT 1,
                suspicious_links_block INTEGER NOT NULL DEFAULT 1,
                excessive_emojis_block INTEGER NOT NULL DEFAULT 1,
                emoji_limit INTEGER NOT NULL DEFAULT 8,
                excessive_caps_block INTEGER NOT NULL DEFAULT 1,
                caps_percentage INTEGER NOT NULL DEFAULT 70,
                action TEXT NOT NULL DEFAULT 'timeout',
                banned_words TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """
        ]
    ),
    (
        2,
        "Add fun module configuration and game leaderboard statistics",
        [
            """
            CREATE TABLE IF NOT EXISTS fun_config (
                guild_id INTEGER PRIMARY KEY,
                fun_enabled INTEGER NOT NULL DEFAULT 1,
                family_friendly INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS fun_user_stats (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                trivia_wins INTEGER NOT NULL DEFAULT 0,
                coinflip_wins INTEGER NOT NULL DEFAULT 0,
                rps_wins INTEGER NOT NULL DEFAULT 0,
                games_played INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id),
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_fun_user_stats_guild
            ON fun_user_stats(guild_id);
            """
        ]
    ),
    (
        3,
        "Remove fun tables; add suggestion, raid detection, voiceguard, and automation tables",
        [
            # Clean up fun tables
            "DROP TABLE IF EXISTS fun_config;",
            "DROP TABLE IF EXISTS fun_user_stats;",

            # Suggestions
            """
            CREATE TABLE IF NOT EXISTS suggestion_config (
                guild_id INTEGER PRIMARY KEY,
                suggestion_channel_id INTEGER,
                review_channel_id INTEGER,
                staff_role_id INTEGER,
                voting_enabled INTEGER NOT NULL DEFAULT 1,
                discussion_enabled INTEGER NOT NULL DEFAULT 1,
                cooldown_seconds INTEGER NOT NULL DEFAULT 60,
                minimum_length INTEGER NOT NULL DEFAULT 10,
                maximum_length INTEGER NOT NULL DEFAULT 2000,
                show_rejection_reason INTEGER NOT NULL DEFAULT 1,
                notifications_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS suggestions (
                suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                reason TEXT,
                upvotes INTEGER NOT NULL DEFAULT 0,
                downvotes INTEGER NOT NULL DEFAULT 0,
                thread_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reviewed_by INTEGER,
                reviewed_at TEXT,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_suggestions_guild_status
            ON suggestions(guild_id, status);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_suggestions_author
            ON suggestions(guild_id, author_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_suggestions_message
            ON suggestions(message_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS suggestion_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                suggestion_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                vote_type TEXT NOT NULL CHECK(vote_type IN ('upvote', 'downvote')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(guild_id, suggestion_id, user_id),
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE,
                FOREIGN KEY (suggestion_id) REFERENCES suggestions(suggestion_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_suggestion_votes_lookup
            ON suggestion_votes(guild_id, suggestion_id, user_id);
            """,

            # Raid Detection
            """
            CREATE TABLE IF NOT EXISTS raid_config (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                baseline_enabled INTEGER NOT NULL DEFAULT 1,
                join_threshold INTEGER NOT NULL DEFAULT 10,
                join_multiplier REAL NOT NULL DEFAULT 3.0,
                account_age_threshold_hours INTEGER NOT NULL DEFAULT 24,
                risk_threshold_elevated INTEGER NOT NULL DEFAULT 30,
                risk_threshold_suspicious INTEGER NOT NULL DEFAULT 50,
                risk_threshold_high INTEGER NOT NULL DEFAULT 70,
                risk_threshold_critical INTEGER NOT NULL DEFAULT 90,
                observation_window_seconds INTEGER NOT NULL DEFAULT 60,
                quiet_period_seconds INTEGER NOT NULL DEFAULT 300,
                alert_cooldown_seconds INTEGER NOT NULL DEFAULT 60,
                auto_containment INTEGER NOT NULL DEFAULT 0,
                safe_mode_enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS raid_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                incident_id TEXT NOT NULL UNIQUE,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                risk_level TEXT NOT NULL DEFAULT 'NORMAL',
                current_score INTEGER NOT NULL DEFAULT 0,
                maximum_score INTEGER NOT NULL DEFAULT 0,
                resolved_at TEXT,
                resolved_by INTEGER,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_raid_incidents_guild
            ON raid_incidents(guild_id, started_at);
            """,
            """
            CREATE TABLE IF NOT EXISTS raid_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                user_id INTEGER,
                channel_id INTEGER,
                timestamp TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_raid_events_incident
            ON raid_events(incident_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS raid_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                alert_level TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                channel_id INTEGER,
                message_id INTEGER,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,

            # VoiceGuard
            """
            CREATE TABLE IF NOT EXISTS voiceguard_config (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                default_threshold REAL NOT NULL DEFAULT 0.65,
                extreme_threshold REAL NOT NULL DEFAULT 0.85,
                minimum_duration_ms INTEGER NOT NULL DEFAULT 3000,
                warning_limit INTEGER NOT NULL DEFAULT 3,
                violation_decay_seconds INTEGER NOT NULL DEFAULT 600,
                alert_cooldown_seconds INTEGER NOT NULL DEFAULT 120,
                automatic_action TEXT NOT NULL DEFAULT 'warn',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS voice_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                peak_level REAL NOT NULL DEFAULT 0.0,
                average_level REAL NOT NULL DEFAULT 0.0,
                risk_score INTEGER NOT NULL DEFAULT 0,
                severity TEXT NOT NULL DEFAULT 'medium',
                action_taken TEXT NOT NULL DEFAULT 'none',
                resolved_at TEXT,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_voice_incidents_guild
            ON voice_incidents(guild_id, user_id, channel_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS voice_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                incident_id INTEGER,
                warning_number INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,

            # Automation Configuration
            """
            CREATE TABLE IF NOT EXISTS automation_config (
                guild_id INTEGER PRIMARY KEY,
                security_monitor INTEGER NOT NULL DEFAULT 1,
                raid_detection INTEGER NOT NULL DEFAULT 1,
                automod INTEGER NOT NULL DEFAULT 1,
                voiceguard INTEGER NOT NULL DEFAULT 0,
                welcome INTEGER NOT NULL DEFAULT 1,
                autorole INTEGER NOT NULL DEFAULT 1,
                logging INTEGER NOT NULL DEFAULT 1,
                ticket_automation INTEGER NOT NULL DEFAULT 1,
                suggestion_automation INTEGER NOT NULL DEFAULT 1,
                database_maintenance INTEGER NOT NULL DEFAULT 1,
                health_monitor INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """
        ]
    ),
    (
        12,
        "Add owner_reports_config table for private owner reports category",
        [
            """
            CREATE TABLE IF NOT EXISTS owner_reports_config (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER,
                security_report_id INTEGER,
                mod_report_id INTEGER,
                music_report_id INTEGER,
                room_report_id INTEGER,
                bot_report_id INTEGER,
                system_report_id INTEGER,
                auto_repair INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """
        ]
    ),
    (
        13,
        "Add stream_trackers, member_invites, and member_votes tables for external features",
        [
            """
            CREATE TABLE IF NOT EXISTS stream_trackers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                alert_channel_id INTEGER NOT NULL,
                custom_role_id INTEGER,
                last_status TEXT NOT NULL DEFAULT 'offline',
                created_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS member_invites (
                guild_id INTEGER NOT NULL,
                inviter_id INTEGER NOT NULL,
                regular INTEGER NOT NULL DEFAULT 0,
                leaves INTEGER NOT NULL DEFAULT 0,
                fake INTEGER NOT NULL DEFAULT 0,
                bonus INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, inviter_id),
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS member_votes (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                total_votes INTEGER NOT NULL DEFAULT 0,
                last_voted TEXT,
                PRIMARY KEY (user_id, guild_id),
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """
        ]
    ),
    (
        14,
        "Add community platform tables: user profiles, gaming, web sessions, projects, creators, LFG, resources, events, ideas, wiki, and notifications",
        [
            """
            CREATE TABLE IF NOT EXISTS community_gaming_profiles (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                games TEXT DEFAULT '',
                rank TEXT DEFAULT '',
                preferred_modes TEXT DEFAULT '',
                play_times TEXT DEFAULT '',
                mic_available INTEGER DEFAULT 1,
                is_visible INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_user_profiles (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                skills TEXT DEFAULT '',
                interests TEXT DEFAULT '',
                bio TEXT DEFAULT '',
                is_visible INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_collaborations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                requester_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                skill TEXT NOT NULL,
                note TEXT DEFAULT '',
                status TEXT DEFAULT 'PENDING',
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_notification_prefs (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                music_events INTEGER DEFAULT 1,
                gaming_events INTEGER DEFAULT 1,
                creator_events INTEGER DEFAULT 1,
                community_events INTEGER DEFAULT 1,
                idea_updates INTEGER DEFAULT 1,
                reminders INTEGER DEFAULT 1,
                PRIMARY KEY (guild_id, user_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_module_settings (
                guild_id INTEGER PRIMARY KEY,
                music_enabled INTEGER DEFAULT 1,
                dynamic_rooms_enabled INTEGER DEFAULT 1,
                gaming_enabled INTEGER DEFAULT 1,
                creator_enabled INTEGER DEFAULT 1,
                events_enabled INTEGER DEFAULT 1,
                reputation_enabled INTEGER DEFAULT 1,
                resources_enabled INTEGER DEFAULT 1,
                collaboration_enabled INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS web_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                discord_user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                discriminator TEXT DEFAULT '0',
                avatar TEXT,
                access_token TEXT,
                refresh_token TEXT,
                expires_at TEXT,
                user_data_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                project_type TEXT NOT NULL,
                owner_id INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                category_id INTEGER,
                chat_channel_id INTEGER,
                voice_channel_id INTEGER,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS project_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                status TEXT DEFAULT 'TODO',
                assignee_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS creator_portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'General',
                media_url TEXT,
                tools_used TEXT,
                tags TEXT,
                external_links TEXT,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_lfg (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                game_name TEXT NOT NULL,
                mode TEXT,
                current_players INTEGER DEFAULT 1,
                max_players INTEGER DEFAULT 4,
                description TEXT,
                status TEXT DEFAULT 'OPEN',
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                event_type TEXT DEFAULT 'General',
                start_time TEXT NOT NULL,
                end_time TEXT,
                status TEXT DEFAULT 'scheduled',
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'General',
                link TEXT,
                tags TEXT,
                downloads_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'Feature',
                status TEXT DEFAULT 'NEW',
                votes_count INTEGER DEFAULT 0,
                comments_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS idea_votes (
                idea_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                direction INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (idea_id, user_id),
                FOREIGN KEY (idea_id) REFERENCES community_ideas(id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS idea_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idea_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (idea_id) REFERENCES community_ideas(id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                link TEXT DEFAULT '',
                is_read INTEGER DEFAULT 0,
                priority TEXT DEFAULT 'NORMAL',
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS wiki_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                author_id INTEGER DEFAULT 0,
                is_published INTEGER DEFAULT 1,
                version INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                badge_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                icon TEXT DEFAULT '🏆',
                unlocked_at TEXT NOT NULL,
                UNIQUE(user_id, badge_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS sync_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                payload_json TEXT DEFAULT '{}',
                status TEXT DEFAULT 'PENDING',
                retry_count INTEGER DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                processed_at TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER NOT NULL,
                actor_name TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                details_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_saved_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                item_id TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(user_id, item_type, item_id)
            );
            """
        ]
    )
]


def backup_database(db_path: Path) -> Path | None:
    """Create a timestamped backup before any destructive migrations."""
    if not db_path.exists():
        return None
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_file = BACKUPS_DIR / f"bot-{timestamp}.db"
    try:
        shutil.copy2(db_path, backup_file)
        logger.info(f"Database backed up to {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"Failed to backup database: {e}")
        return None


async def run_migrations(db: aiosqlite.Connection) -> int:
    """
    Run any pending database migrations.
    Returns the current schema version.
    """
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
    """)
    await db.commit()

    async with db.execute("SELECT MAX(version) FROM schema_version") as cursor:
        row = await cursor.fetchone()
        current_version = row[0] if (row and row[0] is not None) else 0

    applied_count = 0
    for version, desc, stmts in MIGRATIONS:
        if version > current_version:
            logger.info(f"Applying migration v{version}: {desc}")
            try:
                for stmt in stmts:
                    clean_stmt = stmt.strip()
                    if not clean_stmt:
                        continue
                    try:
                        await db.execute(clean_stmt)
                    except Exception as s_err:
                        if "duplicate column name" in str(s_err).lower():
                            continue
                        raise s_err
                now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                await db.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (version, now_str)
                )
                await db.commit()
                current_version = version
                applied_count += 1
            except Exception as e:
                await db.rollback()
                logger.error(f"Migration v{version} failed: {e}")
                raise RuntimeError(f"Migration v{version} failed: {e}") from e

    logger.info(f"Schema is up to date at version {current_version} ({applied_count} applied)")
    return current_version
