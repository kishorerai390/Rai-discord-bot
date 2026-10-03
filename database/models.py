"""
Data models and type definitions for SQLite tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class HiddenVoiceConfig:
    guild_id: int
    enabled: bool = True
    category_id: Optional[int] = None
    entry_channel_id: Optional[int] = None
    max_rooms_per_user: int = 1
    max_users_per_room: int = 99
    empty_grace_period: int = 60
    allow_invited_members: bool = True
    allow_ownership_transfer: bool = True
    staff_can_view_hidden_rooms: bool = False
    automatic_cleanup: bool = True
    automatic_owner_transfer: bool = False
    room_name_format: str = "🔒・{username}-private"
    updated_at: str = ""


@dataclass
class HiddenVoiceRoom:
    channel_id: int
    guild_id: int
    owner_id: int
    created_at: str
    last_activity: str
    invited_members: List[int]
    room_status: str = "active"
    user_limit: int = 0
    is_locked: bool = False
    is_hidden: bool = True
    name: str = ""
    grace_period_until: Optional[str] = None
    transferred_from: Optional[int] = None


@dataclass
class MusicConfig:
    guild_id: int
    dj_role_id: Optional[int] = None
    request_channel_id: Optional[int] = None
    default_volume: int = 50
    autoplay_enabled: bool = False
    inactivity_timeout: int = 180
    updated_at: str = ""


@dataclass
class MusicPlaylist:
    id: int
    guild_id: int
    user_id: int
    name: str
    tracks: List[Dict[str, Any]]
    is_guild_playlist: bool = False
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CommunityEvent:
    id: int
    guild_id: int
    title: str
    event_type: str
    start_time: str
    description: str
    creator_id: int
    channel_id: Optional[int] = None
    status: str = "scheduled"
    created_at: str = ""


@dataclass
class GamingLFG:
    id: int
    guild_id: int
    user_id: int
    game: str
    role: Optional[str] = None
    note: Optional[str] = None
    max_players: int = 4
    current_players: List[int] = None
    message_id: Optional[int] = None
    channel_id: Optional[int] = None
    status: str = "open"
    created_at: str = ""


@dataclass
class CreatorShowcase:
    id: int
    guild_id: int
    user_id: int
    title: str
    media_url: str
    software: Optional[str] = None
    description: Optional[str] = None
    upvotes: int = 0
    message_id: Optional[int] = None
    created_at: str = ""


@dataclass
class WatchEvent:
    id: int
    guild_id: int
    title: str
    platform: Optional[str] = None
    start_time: str = ""
    host_id: int = 0
    voice_channel_id: Optional[int] = None
    status: str = "scheduled"
    created_at: str = ""


@dataclass
class MusicAnalytics:
    guild_id: int
    tracks_played: int = 0
    total_playtime_seconds: int = 0
    unique_listeners: List[int] = None
    updated_at: str = ""


@dataclass
class UserEconomy:
    user_id: int
    guild_id: int
    coins: int = 100
    bank: int = 0
    daily_streak: int = 0
    last_daily: Optional[str] = None
    xp: int = 0
    level: int = 1
    purchased_roles: List[str] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class MatchmakerHistory:
    id: int
    guild_id: int
    game: str
    mode: str
    player_ids: List[int] = None
    voice_channel_id: Optional[int] = None
    created_at: str = ""


@dataclass
class OwnerReportsConfig:
    guild_id: int
    category_id: Optional[int] = None
    security_report_id: Optional[int] = None
    mod_report_id: Optional[int] = None
    music_report_id: Optional[int] = None
    room_report_id: Optional[int] = None
    bot_report_id: Optional[int] = None
    system_report_id: Optional[int] = None
    auto_repair: bool = True
    startup_reports_enabled: bool = False
    success_reports_enabled: bool = False
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ReportDestination:
    guild_id: int
    report_type: str
    channel_id: int
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ReportPermissionState:
    guild_id: int
    channel_id: int
    report_type: str
    status: str = "PENDING"  # PENDING, APPROVED, DENIED, DISABLED
    last_checked_at: Optional[str] = None
    last_warning_at: Optional[str] = None
    last_error: Optional[str] = None
    warning_message_id: Optional[int] = None
    retry_after: float = 0.0


@dataclass
class ReportEventRecord:
    event_id: str
    guild_id: int
    report_type: str
    severity: str
    fingerprint: str
    message: str
    first_seen: str = ""
    last_seen: str = ""
    occurrences: int = 1
    status: str = "DETECTED"  # DETECTED, VERIFIED, OPEN, UPDATED, RECOVERED, CLOSED


@dataclass
class ReportDeliveryRecord:
    event_id: str
    channel_id: int
    message_id: Optional[int] = None
    status: str = "PENDING"
    attempts: int = 0
    last_attempt_at: Optional[str] = None
    error: Optional[str] = None


@dataclass
class StreamTracker:
    id: int
    guild_id: int
    platform: str
    channel_name: str
    alert_channel_id: int
    custom_role_id: Optional[int] = None
    last_status: str = "offline"
    created_at: str = ""


@dataclass
class MemberInvites:
    guild_id: int
    inviter_id: int
    regular: int = 0
    leaves: int = 0
    fake: int = 0
    bonus: int = 0

    @property
    def total(self) -> int:
        return max(0, self.regular + self.bonus - self.leaves - self.fake)


@dataclass
class MemberVotes:
    user_id: int
    guild_id: int
    total_votes: int = 0
    last_voted: Optional[str] = None



@dataclass
class GuildConfig:
    guild_id: int
    security_enabled: bool = True
    automod_enabled: bool = False
    welcome_enabled: bool = False
    autorole_enabled: bool = False
    tickets_enabled: bool = False
    music_enabled: bool = True
    emergency_stop: bool = False
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SecurityConfig:
    guild_id: int
    channel_delete_limit: int = 5
    channel_delete_window: int = 10
    channel_create_limit: int = 10
    channel_create_window: int = 10
    role_delete_limit: int = 5
    role_delete_window: int = 10
    role_create_limit: int = 10
    role_create_window: int = 10
    ban_limit: int = 5
    ban_window: int = 10
    kick_limit: int = 5
    kick_window: int = 10
    webhook_limit: int = 3
    webhook_window: int = 10
    punishment: str = "alert"  # alert, warn, timeout, kick, ban, lock_channels
    updated_at: str = ""


@dataclass
class SecurityIncident:
    event_id: str
    guild_id: int
    timestamp: str
    event_type: str
    executor_id: Optional[int]
    executor_name: Optional[str]
    target_id: Optional[int]
    target_name: Optional[str]
    action: str
    detected_count: Optional[int]
    threshold: Optional[int]
    audit_log_id: Optional[int]
    reason: Optional[str]
    automated_action: Optional[str]
    result: Optional[str]
    severity: str = "medium"
    audit_verified: bool = False


@dataclass
class SecurityState:
    guild_id: int
    emergency_stop: bool = False
    lockdown_enabled: bool = False
    lockdown_started_at: Optional[str] = None
    emergency_started_at: Optional[str] = None
    changed_by: Optional[int] = None
    updated_at: str = ""


@dataclass
class ModerationWarning:
    id: int
    guild_id: int
    user_id: int
    moderator_id: int
    reason: str
    created_at: str
    expires_at: Optional[str] = None


@dataclass
class WelcomeConfig:
    guild_id: int
    welcome_channel_id: Optional[int] = None
    goodbye_channel_id: Optional[int] = None
    welcome_message: Optional[str] = None
    goodbye_message: Optional[str] = None
    autorole_id: Optional[int] = None
    dm_enabled: bool = False
    embed_enabled: bool = True
    updated_at: str = ""


@dataclass
class LoggingConfig:
    guild_id: int
    general_channel_id: Optional[int] = None
    moderation_channel_id: Optional[int] = None
    security_channel_id: Optional[int] = None
    automod_channel_id: Optional[int] = None
    member_channel_id: Optional[int] = None
    message_channel_id: Optional[int] = None
    voice_channel_id: Optional[int] = None
    updated_at: str = ""


@dataclass
class TicketConfig:
    guild_id: int
    category_id: Optional[int] = None
    log_channel_id: Optional[int] = None
    support_role_id: Optional[int] = None
    transcript_enabled: bool = True
    updated_at: str = ""


@dataclass
class TicketRecord:
    ticket_id: int
    guild_id: int
    channel_id: int
    creator_id: int
    status: str
    created_at: str
    closed_at: Optional[str] = None
    closed_by: Optional[int] = None


@dataclass
class AutoModConfig:
    guild_id: int
    spam_detection: bool = True
    spam_limit: int = 5
    spam_window: int = 5
    mention_limit: int = 5
    repeated_limit: int = 3
    banned_words_enabled: bool = True
    invite_links_block: bool = True
    suspicious_links_block: bool = True
    excessive_emojis_block: bool = True
    emoji_limit: int = 8
    excessive_caps_block: bool = True
    caps_percentage: int = 70
    action: str = "delete"  # delete, warn, timeout
    banned_words: str = ""  # comma-separated list
    updated_at: str = ""


# ==========================================
# SUGGESTIONS
# ==========================================

@dataclass
class SuggestionConfig:
    guild_id: int
    suggestion_channel_id: Optional[int] = None
    review_channel_id: Optional[int] = None
    staff_role_id: Optional[int] = None
    voting_enabled: bool = True
    discussion_enabled: bool = True
    cooldown_seconds: int = 60
    minimum_length: int = 10
    maximum_length: int = 2000
    show_rejection_reason: bool = True
    notifications_enabled: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SuggestionRecord:
    suggestion_id: int
    guild_id: int
    channel_id: int
    message_id: int
    author_id: int
    content: str
    status: str = "pending"  # pending, approved, rejected, implemented, archived
    reason: Optional[str] = None
    upvotes: int = 0
    downvotes: int = 0
    thread_id: Optional[int] = None
    created_at: str = ""
    updated_at: str = ""
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[str] = None


# ==========================================
# RAID DETECTION & SECURITY BRAIN
# ==========================================

@dataclass
class RaidConfig:
    guild_id: int
    enabled: bool = True
    baseline_enabled: bool = True
    join_threshold: int = 10
    join_multiplier: float = 3.0
    account_age_threshold_hours: int = 24
    risk_threshold_elevated: int = 30
    risk_threshold_suspicious: int = 50
    risk_threshold_high: int = 70
    risk_threshold_critical: int = 90
    observation_window_seconds: int = 60
    quiet_period_seconds: int = 300
    alert_cooldown_seconds: int = 60
    auto_containment: bool = False
    safe_mode_enabled: bool = False
    updated_at: str = ""


@dataclass
class RaidIncident:
    id: int
    guild_id: int
    incident_id: str
    started_at: str
    ended_at: Optional[str] = None
    status: str = "OPEN"  # OPEN, MONITORING, ESCALATED, CONTAINED, RESOLVED, FALSE_POSITIVE
    risk_level: str = "NORMAL"  # NORMAL, ELEVATED, SUSPICIOUS, HIGH, CRITICAL
    current_score: int = 0
    maximum_score: int = 0
    resolved_at: Optional[str] = None
    resolved_by: Optional[int] = None


@dataclass
class RaidEvent:
    id: int
    incident_id: str
    guild_id: int
    event_type: str
    user_id: Optional[int]
    channel_id: Optional[int]
    timestamp: str
    metadata: str = ""


# ==========================================
# VOICEGUARD
# ==========================================

@dataclass
class VoiceGuardConfig:
    guild_id: int
    enabled: bool = False
    default_threshold: float = 0.65  # Relative audio energy (0.0 to 1.0)
    extreme_threshold: float = 0.85
    minimum_duration_ms: int = 3000
    warning_limit: int = 3
    violation_decay_seconds: int = 600
    alert_cooldown_seconds: int = 120
    automatic_action: str = "warn"  # warn, alert, server_mute
    updated_at: str = ""


@dataclass
class VoiceIncident:
    id: int
    guild_id: int
    user_id: int
    channel_id: int
    started_at: str
    ended_at: Optional[str] = None
    peak_level: float = 0.0
    average_level: float = 0.0
    risk_score: int = 0
    severity: str = "medium"
    action_taken: str = "none"
    resolved_at: Optional[str] = None


# ==========================================
# AUTOMATION DASHBOARD
# ==========================================

@dataclass
class AutomationConfig:
    guild_id: int
    security_monitor: bool = True
    raid_detection: bool = True
    automod: bool = True
    voiceguard: bool = False
    welcome: bool = True
    autorole: bool = True
    logging: bool = True
    ticket_automation: bool = True
    suggestion_automation: bool = True
    database_maintenance: bool = True
    health_monitor: bool = True
    updated_at: str = ""


