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
        36,
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
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'TODO',
                assignee_id INTEGER,
                priority TEXT DEFAULT 'NORMAL',
                due_date TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
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
                is_featured INTEGER DEFAULT 0,
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
            CREATE TABLE IF NOT EXISTS gaming_lfg (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                role TEXT,
                note TEXT,
                max_players INTEGER NOT NULL DEFAULT 4,
                current_players_json TEXT NOT NULL DEFAULT '[]',
                channel_id INTEGER,
                message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'open',
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
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'General',
                start_time TEXT NOT NULL,
                description TEXT DEFAULT '',
                creator_id INTEGER NOT NULL DEFAULT 0,
                channel_id INTEGER,
                status TEXT NOT NULL DEFAULT 'scheduled',
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS event_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                UNIQUE(event_id, user_id),
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
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
                status TEXT DEFAULT 'APPROVED',
                downloads_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS community_ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                author_name TEXT DEFAULT '',
                title TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'Feature',
                tags TEXT DEFAULT '',
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
                entity_id TEXT DEFAULT '',
                source TEXT DEFAULT 'WEB',
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
    ),
    (
        37,
        "Ensure sync_outbox and project_tasks have all columns",
        [
            """
            ALTER TABLE sync_outbox ADD COLUMN source TEXT DEFAULT 'WEB';
            """,
            """
            ALTER TABLE project_tasks ADD COLUMN description TEXT DEFAULT '';
            """,
            """
            ALTER TABLE project_tasks ADD COLUMN priority TEXT DEFAULT 'NORMAL';
            """,
            """
            ALTER TABLE project_tasks ADD COLUMN due_date TEXT;
            """,
            """
            ALTER TABLE project_tasks ADD COLUMN updated_at TEXT;
            """
        ]
    ),
    (
        38,
        "Ensure community_resources has tags and downloads_count",
        [
            """
            ALTER TABLE community_resources ADD COLUMN tags TEXT DEFAULT '';
            """,
            """
            ALTER TABLE community_resources ADD COLUMN downloads_count INTEGER DEFAULT 0;
            """
        ]
    ),
    (
        39,
        "Create dynamic_rooms, room_members, and temp_voice_configs tables for dynamic voice lifecycle",
        [
            """
            CREATE TABLE IF NOT EXISTS temp_voice_configs (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                hub_channel_id INTEGER,
                category_id INTEGER,
                default_user_limit INTEGER NOT NULL DEFAULT 0,
                name_format TEXT NOT NULL DEFAULT '🎙️ {username}''s Room',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS dynamic_rooms (
                guild_id INTEGER NOT NULL,
                voice_channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                room_type TEXT DEFAULT 'public',
                privacy_mode TEXT DEFAULT 'public',
                user_limit INTEGER DEFAULT 0,
                locked INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                control_message_id INTEGER,
                control_channel_id INTEGER,
                cleanup_status TEXT DEFAULT 'active',
                empty_since TEXT,
                cleanup_due_at TEXT,
                last_empty_at TEXT,
                protected_until TEXT,
                last_voice_activity TEXT,
                co_host_ids TEXT,
                dj_ids TEXT,
                template_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """,
            """
            ALTER TABLE dynamic_rooms ADD COLUMN last_empty_at TEXT;
            """,
            """
            ALTER TABLE dynamic_rooms ADD COLUMN protected_until TEXT;
            """,
            """
            ALTER TABLE dynamic_rooms ADD COLUMN last_voice_activity TEXT;
            """,
            """
            ALTER TABLE dynamic_rooms ADD COLUMN co_host_ids TEXT;
            """,
            """
            ALTER TABLE dynamic_rooms ADD COLUMN dj_ids TEXT;
            """,
            """
            ALTER TABLE dynamic_rooms ADD COLUMN template_id TEXT;
            """,
            """
            CREATE TABLE IF NOT EXISTS room_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voice_channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                permission_type TEXT DEFAULT 'view',
                added_at TEXT NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_dynamic_rooms_guild ON dynamic_rooms(guild_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS room_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                template_name TEXT NOT NULL,
                settings TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS room_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                actor_id INTEGER NOT NULL DEFAULT 0,
                user_id INTEGER DEFAULT 0,
                timestamp REAL DEFAULT 0,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT ''
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS room_knock_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS nl_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                raw_message TEXT NOT NULL,
                intent TEXT NOT NULL,
                confidence REAL NOT NULL,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_nl_audits_guild ON nl_audits(guild_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS music_config (
                guild_id INTEGER PRIMARY KEY,
                dj_role_id INTEGER,
                request_channel_id INTEGER,
                default_volume INTEGER DEFAULT 50,
                autoplay_enabled INTEGER DEFAULT 0,
                inactivity_timeout INTEGER DEFAULT 180,
                updated_at TEXT
            );
            """
        ]
    ),
    (
        40,
        "Add guild_channel_configs, interaction_records, and incident aggregation columns",
        [
            """
            CREATE TABLE IF NOT EXISTS guild_channel_configs (
                guild_id INTEGER PRIMARY KEY,
                security_alerts_channel_id INTEGER,
                anti_nuke_channel_id INTEGER,
                lockdown_control_channel_id INTEGER,
                security_log_channel_id INTEGER,
                audit_monitor_channel_id INTEGER,

                security_report_channel_id INTEGER,
                moderation_report_channel_id INTEGER,
                music_report_channel_id INTEGER,
                room_report_channel_id INTEGER,
                bot_report_channel_id INTEGER,
                system_report_channel_id INTEGER,

                admin_control_channel_id INTEGER,
                server_dashboard_channel_id INTEGER,
                bot_config_channel_id INTEGER,
                automation_control_channel_id INTEGER,
                backup_control_channel_id INTEGER,
                system_health_channel_id INTEGER,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_guild_channel_configs_guild ON guild_channel_configs(guild_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS interaction_records (
                request_id TEXT PRIMARY KEY,
                guild_id INTEGER,
                user_id INTEGER NOT NULL,
                interaction_id INTEGER,
                interaction_type TEXT NOT NULL,
                command_name TEXT NOT NULL,
                module TEXT,
                received_at REAL NOT NULL,
                ack_at REAL,
                completed_at REAL,
                ack_latency_ms REAL,
                duration_ms REAL,
                status TEXT NOT NULL DEFAULT 'COMPLETED',
                error_code TEXT,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_interaction_records_guild ON interaction_records(guild_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_interaction_records_req ON interaction_records(request_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS interactive_incidents (
                incident_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                report_type TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id INTEGER,
                actor_name TEXT,
                target_id INTEGER,
                target_name TEXT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                action_taken TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                severity TEXT NOT NULL DEFAULT 'HIGH',
                details_json TEXT,
                dm_message_id INTEGER,
                dm_channel_id INTEGER,
                channel_message_id INTEGER,
                report_channel_id INTEGER,
                alert_message_id INTEGER,
                alert_channel_id INTEGER,
                event_count INTEGER DEFAULT 1,
                fingerprint TEXT,
                acknowledged_by INTEGER,
                acknowledged_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """,
            """
            ALTER TABLE interactive_incidents ADD COLUMN alert_message_id INTEGER;
            """,
            """
            ALTER TABLE interactive_incidents ADD COLUMN alert_channel_id INTEGER;
            """,
            """
            ALTER TABLE interactive_incidents ADD COLUMN event_count INTEGER DEFAULT 1;
            """,
            """
            ALTER TABLE interactive_incidents ADD COLUMN fingerprint TEXT;
            """,
            """
            ALTER TABLE interactive_incidents ADD COLUMN acknowledged_by INTEGER;
            """,
            """
            ALTER TABLE interactive_incidents ADD COLUMN acknowledged_at TEXT;
            """
        ]
    ),
    (
        41,
        "Add music_playlists table for server and user playlist storage",
        [
            """
            CREATE TABLE IF NOT EXISTS music_playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                tracks_json TEXT NOT NULL DEFAULT '[]',
                is_guild_playlist INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(guild_id, user_id, name)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_music_playlists_guild_user
            ON music_playlists(guild_id, user_id);
            """
        ]
    ),
    (
        42,
        "Add workflows, bot_shield_audits, server_memory, and conversation_context tables",
        [
            """
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                trigger_type TEXT NOT NULL DEFAULT 'manual',
                trigger_config TEXT NOT NULL DEFAULT '{}',
                missed_schedule_policy TEXT NOT NULL DEFAULT 'SKIP',
                version INTEGER NOT NULL DEFAULT 1,
                last_run_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_workflows_guild ON workflows(guild_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS workflow_steps (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                step_order INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                action_config TEXT NOT NULL DEFAULT '{}',
                condition_config TEXT NOT NULL DEFAULT '{}',
                risk_level TEXT NOT NULL DEFAULT 'LOW',
                failure_policy TEXT NOT NULL DEFAULT 'STOP',
                timeout_seconds INTEGER NOT NULL DEFAULT 60,
                retry_policy TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_workflow_steps_wf ON workflow_steps(workflow_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS workflow_executions (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                trigger_event TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'RUNNING',
                current_step_order INTEGER NOT NULL DEFAULT 1,
                step_results TEXT NOT NULL DEFAULT '[]',
                error TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_workflow_executions_guild ON workflow_executions(guild_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS workflow_step_executions (
                id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                step_order INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                result_data TEXT,
                error TEXT,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                executed_at TEXT NOT NULL,
                FOREIGN KEY (execution_id) REFERENCES workflow_executions(id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS workflow_waiting_timers (
                id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                resume_at TEXT NOT NULL,
                next_step_order INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'WAITING',
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_workflow_waiting_timers_due ON workflow_waiting_timers(resume_at, status);
            """,
            """
            CREATE TABLE IF NOT EXISTS workflow_events (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS bot_shield_audits (
                audit_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                bot_id INTEGER NOT NULL,
                bot_name TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                dangerous_permissions TEXT NOT NULL,
                is_isolated INTEGER NOT NULL DEFAULT 0,
                isolated_at TEXT,
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_bot_shield_audits_guild ON bot_shield_audits(guild_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS server_memory (
                guild_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                created_by INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(guild_id, key)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_server_memory_guild ON server_memory(guild_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS conversation_context (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                key TEXT NOT NULL,
                val TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(guild_id, user_id, channel_id, key)
            );
            """
        ]
    ),
    (
        43,
        "Premium Monetization Subsystem (products, entitlements, feature rules, events)",
        [
            """
            CREATE TABLE IF NOT EXISTS premium_products (
                sku_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                scope TEXT NOT NULL,
                sku_type INTEGER DEFAULT 5,
                price_cents INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS premium_entitlements (
                entitlement_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                guild_id INTEGER,
                sku_id INTEGER NOT NULL,
                scope TEXT NOT NULL,
                status TEXT NOT NULL,
                starts_at TEXT,
                ends_at TEXT,
                is_test INTEGER DEFAULT 0,
                consumed INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_prem_ent_user ON premium_entitlements(user_id, status);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_prem_ent_guild ON premium_entitlements(guild_id, status);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_prem_ent_expiry ON premium_entitlements(ends_at, status);
            """,
            """
            CREATE TABLE IF NOT EXISTS premium_feature_rules (
                feature_key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                scope_required TEXT NOT NULL DEFAULT 'any',
                is_enabled INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS premium_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                entitlement_id INTEGER,
                user_id INTEGER,
                guild_id INTEGER,
                sku_id INTEGER,
                details TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_prem_events_user ON premium_events(user_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_prem_events_guild ON premium_events(guild_id);
            """
        ]
    ),
    (
        44,
        "Operations Core: Operations state, configuration versions, and scheduled tasks",
        [
            """
            CREATE TABLE IF NOT EXISTS operations_state (
                guild_id INTEGER PRIMARY KEY,
                maintenance_mode INTEGER NOT NULL DEFAULT 0,
                maintenance_reason TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS config_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                created_by TEXT NOT NULL,
                label TEXT NOT NULL,
                config_data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_config_versions_guild ON config_versions(guild_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                task_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                task_type TEXT NOT NULL,
                command_phrase TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL,
                next_run_at TEXT NOT NULL,
                last_run_at TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_guild ON scheduled_tasks(guild_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_next ON scheduled_tasks(next_run_at);
            """,
            """
            ALTER TABLE room_events ADD COLUMN user_id INTEGER DEFAULT 0;
            """,
            """
            ALTER TABLE room_events ADD COLUMN timestamp REAL DEFAULT 0;
            """,
            """
            CREATE TABLE IF NOT EXISTS event_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'community',
                default_description TEXT NOT NULL DEFAULT '',
                default_duration_mins INTEGER NOT NULL DEFAULT 60,
                created_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE,
                UNIQUE(guild_id, name)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS reputation_profiles (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                points INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                helpful_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id),
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS reputation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                giver_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                points INTEGER NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_rep_leaderboard ON reputation_profiles(guild_id, points DESC);
            """,
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                project_type TEXT NOT NULL DEFAULT 'creator',
                owner_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            ALTER TABLE projects ADD COLUMN updated_at TEXT;
            """,
            """
            CREATE TABLE IF NOT EXISTS project_members (
                project_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'contributor',
                joined_at TEXT NOT NULL,
                PRIMARY KEY (project_id, user_id),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS server_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_knowledge_search ON server_knowledge(guild_id, topic);
            """,
            """
            CREATE TABLE IF NOT EXISTS simulation_runs (
                simulation_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                sim_type TEXT NOT NULL,
                actor_id INTEGER NOT NULL,
                details TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS private_control_config (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                auto_repair INTEGER NOT NULL DEFAULT 1,
                control_hub_category_id INTEGER,
                reports_category_id INTEGER,
                security_category_id INTEGER,
                admin_category_id INTEGER,
                security_alerts_id INTEGER,
                anti_nuke_id INTEGER,
                security_log_id INTEGER,
                audit_monitor_id INTEGER,
                lockdown_control_id INTEGER,
                admin_control_id INTEGER,
                server_dashboard_id INTEGER,
                bot_config_id INTEGER,
                automation_control_id INTEGER,
                backup_control_id INTEGER,
                system_health_id INTEGER,
                bot_report_channel_id INTEGER,
                security_report_channel_id INTEGER,
                system_report_channel_id INTEGER,
                rai_security_role_id INTEGER,
                rai_admin_role_id INTEGER,
                owner_category_id INTEGER,
                owner_ids TEXT NOT NULL DEFAULT '[]',
                security_role_ids TEXT NOT NULL DEFAULT '[]',
                admin_role_ids TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS guild_modules (
                guild_id INTEGER NOT NULL,
                module_name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, module_name),
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS server_profiles (
                guild_id INTEGER PRIMARY KEY,
                server_type TEXT NOT NULL DEFAULT 'Community + Gaming + Creator',
                automation_level TEXT NOT NULL DEFAULT 'HIGH',
                security_level TEXT NOT NULL DEFAULT 'BALANCED',
                modules_enabled TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """
        ]
    ),
    (
        45,
        "Add billboard, multi-db sync queue, threat timeline, community showcases, watch events, music analytics, and hidden voice tables",
        [
            """
            CREATE TABLE IF NOT EXISTS server_billboards (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                message_id INTEGER,
                is_active INTEGER NOT NULL DEFAULT 0,
                update_interval INTEGER NOT NULL DEFAULT 60,
                last_updated_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS pending_sync_operations (
                operation_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                target TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'SECURITY',
                status TEXT NOT NULL DEFAULT 'PENDING',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                incident_id TEXT,
                error_code TEXT,
                next_attempt TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sync_ops_pending ON pending_sync_operations(target, status, priority);
            """,
            """
            CREATE TABLE IF NOT EXISTS mention_spam_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT UNIQUE NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                first_channel_id INTEGER,
                channels_affected TEXT NOT NULL DEFAULT '[]',
                messages_count INTEGER NOT NULL DEFAULT 1,
                mentions_count INTEGER NOT NULL DEFAULT 1,
                unique_targets_count INTEGER NOT NULL DEFAULT 1,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                severity TEXT NOT NULL,
                action_taken TEXT,
                incident_status TEXT NOT NULL DEFAULT 'RESOLVED',
                created_at TEXT,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS threat_timeline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                module TEXT NOT NULL,
                event_type TEXT NOT NULL,
                description TEXT,
                risk_score INTEGER NOT NULL DEFAULT 0,
                severity TEXT NOT NULL DEFAULT 'low',
                created_at TEXT NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_threat_timeline_inc ON threat_timeline_events(incident_id);
            """,
            """
            CREATE TABLE IF NOT EXISTS creator_showcases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                media_url TEXT,
                software TEXT,
                description TEXT,
                upvotes INTEGER NOT NULL DEFAULT 0,
                message_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS watch_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                platform TEXT,
                start_time TEXT NOT NULL,
                host_id INTEGER NOT NULL,
                voice_channel_id INTEGER,
                status TEXT NOT NULL DEFAULT 'scheduled',
                created_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS music_analytics (
                guild_id INTEGER PRIMARY KEY,
                tracks_played INTEGER NOT NULL DEFAULT 0,
                total_playtime_seconds INTEGER NOT NULL DEFAULT 0,
                unique_listeners_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS hidden_voice_config (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                category_id INTEGER,
                entry_channel_id INTEGER,
                max_rooms_per_user INTEGER NOT NULL DEFAULT 1,
                max_users_per_room INTEGER NOT NULL DEFAULT 99,
                empty_grace_period INTEGER NOT NULL DEFAULT 60,
                allow_invited_members INTEGER NOT NULL DEFAULT 1,
                allow_ownership_transfer INTEGER NOT NULL DEFAULT 1,
                staff_can_view_hidden_rooms INTEGER NOT NULL DEFAULT 0,
                automatic_cleanup INTEGER NOT NULL DEFAULT 1,
                automatic_owner_transfer INTEGER NOT NULL DEFAULT 0,
                room_name_format TEXT NOT NULL DEFAULT '🔒・{username}-private',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS hidden_voice_rooms (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                user_limit INTEGER NOT NULL DEFAULT 0,
                is_locked INTEGER NOT NULL DEFAULT 0,
                is_hidden INTEGER NOT NULL DEFAULT 1,
                room_status TEXT NOT NULL DEFAULT 'active',
                invited_members TEXT NOT NULL DEFAULT '[]',
                grace_period_until TEXT,
                transferred_from INTEGER,
                created_at TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS autopilot_configs (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                dry_run INTEGER DEFAULT 0,
                max_safety_level TEXT DEFAULT 'HIGH',
                alert_channel_id INTEGER,
                ticket_management INTEGER DEFAULT 1,
                auto_safe_mode INTEGER DEFAULT 1,
                anti_nuke INTEGER DEFAULT 1,
                raid_protection INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (guild_id) REFERENCES guild_config(guild_id) ON DELETE CASCADE
            );
            """,
            """
            ALTER TABLE autopilot_configs ADD COLUMN raid_protection INTEGER DEFAULT 1;
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
