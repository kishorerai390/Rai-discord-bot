"""
Data models and type definitions for SQLite tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class GamingLFG:
    id: int
    guild_id: int
    user_id: int
    game: str
    role: Optional[str] = None
    note: Optional[str] = None
    max_players: int = 4
    current_players: List[int] = field(default_factory=list)
    message_id: Optional[int] = None
    channel_id: Optional[int] = None
    status: str = "open"
    created_at: str = ""


@dataclass
class AutopilotConfig:
    """Per-guild configuration for the Autopilot Engine."""
    guild_id: int
    enabled: bool = True
    dry_run: bool = False
    max_safety_level: str = "HIGH"
    alert_channel_id: Optional[int] = None
    ticket_management: bool = True
    auto_safe_mode: bool = True
    anti_nuke: bool = True
    updated_at: str = ""


@dataclass
class AutopilotAction:
    """Audit record for a single autonomous action taken by the Autopilot Engine."""
    id: str
    guild_id: int
    module: str
    trigger: str
    reason: str
    risk_level: str
    action: str
    result: str
    target_id: Optional[int] = None
    target_type: Optional[str] = None
    details: Optional[str] = None
    created_at: str = ""

    @property
    def action_id(self) -> str:
        return self.id


@dataclass
class SecurityBaseline:
    """Adaptive server-activity baseline used by the Autopilot Engine."""
    guild_id: int
    joins_per_hour: float = 0.0
    messages_per_min: float = 0.0
    voice_users: float = 0.0
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Self-Healing
# ---------------------------------------------------------------------------

@dataclass
class SelfHealingRecord:
    """Audit record for a self-healing recovery attempt."""
    id: str
    component: str
    error_class: str
    error_message: str
    recovery_action: str
    result: str                   # SUCCESS / FAILED / SKIPPED
    attempt_count: int = 1
    details: Optional[str] = None
    created_at: str = ""


# ---------------------------------------------------------------------------
# Interactive Incidents
# ---------------------------------------------------------------------------

@dataclass
class InteractiveIncident:
    """A rich, actionable incident card sent to staff via DM or log channel."""
    incident_id: str
    guild_id: int
    report_type: str              # security / mod / room / etc.
    event_type: str
    title: str
    description: str
    actor_id: Optional[int] = None
    actor_name: Optional[str] = None
    target_id: Optional[int] = None
    target_name: Optional[str] = None
    action_taken: Optional[str] = None
    status: str = "ACTIVE"        # ACTIVE / RESOLVED / DISMISSED
    severity: str = "MEDIUM"      # LOW / MEDIUM / HIGH / CRITICAL
    details_json: Optional[str] = None
    dm_message_id: Optional[int] = None
    dm_channel_id: Optional[int] = None
    channel_message_id: Optional[int] = None
    report_channel_id: Optional[int] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class IncidentActionAudit:
    """Individual action taken by a staff member on an InteractiveIncident."""
    id: Optional[int]
    incident_id: str
    actor_id: int
    action: str
    result: str
    target_id: Optional[int] = None
    details: Optional[str] = None
    created_at: str = ""
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Guild Roles
# ---------------------------------------------------------------------------

@dataclass
class GuildRole:
    """A Discord role that Rai manages or tracks for a guild."""
    id: int
    guild_id: int
    role_key: str
    discord_role_id: int
    role_name: str
    role_type: str
    managed_by_rai: bool = False
    enabled: bool = True
    position: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class RoleAuditLog:
    """Audit entry for automatic or manual role changes."""
    id: int
    guild_id: int
    user_id: Optional[int]
    role_id: Optional[int]
    role_key: Optional[str]
    action: str
    reason: Optional[str]
    trigger: Optional[str]
    executor: Optional[str]
    success: bool
    error: Optional[str]
    timestamp: str


# ---------------------------------------------------------------------------
# Bot Shield Audit
# ---------------------------------------------------------------------------

@dataclass
class BotShieldAuditRecord:
    """Audit log entry for Rai's third-party bot privilege shield actions."""
    audit_id: str
    guild_id: int
    bot_id: int
    bot_name: str
    risk_level: str
    dangerous_permissions: str
    is_isolated: bool = False
    isolated_at: Optional[str] = None
    created_at: str = ""


# ---------------------------------------------------------------------------
# Channel Access
# ---------------------------------------------------------------------------

@dataclass
class ChannelAccessConfig:
    """Configuration for the automatic channel access recovery service."""
    guild_id: int
    enabled: bool = True
    empty_channels_only: bool = True
    include_text: bool = True
    include_announcement: bool = True
    include_forum: bool = True
    include_voice: bool = False
    include_stage: bool = False
    include_private: bool = False
    auto_update: bool = True
    updated_at: str = ""


@dataclass
class ChannelAccessState:
    """Last known access state for a single channel."""
    guild_id: int
    channel_id: int
    channel_type: str
    last_checked: str
    access_status: str            # ACCESSIBLE / UPDATED / FAILED
    last_updated: Optional[str] = None
    error_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Dynamic Voice Rooms
# ---------------------------------------------------------------------------

@dataclass
class TempVoiceConfig:
    """Guild-level configuration for the dynamic/temporary voice room system."""
    guild_id: int
    enabled: bool = False
    hub_channel_id: Optional[int] = None
    category_id: Optional[int] = None
    default_user_limit: int = 0
    name_format: str = "🎙️ {username}'s Room"
    updated_at: str = ""


@dataclass
class ServerStatsConfig:
    """Guild-level configuration for automated server statistics voice counters."""
    guild_id: int
    enabled: bool = False
    category_id: Optional[int] = None
    all_members_channel_id: Optional[int] = None
    members_channel_id: Optional[int] = None
    bots_channel_id: Optional[int] = None
    updated_at: str = ""


@dataclass
class DynamicRoom:
    """An active temporary voice room provisioned for a member."""
    guild_id: int
    voice_channel_id: int
    owner_id: int
    room_type: str = "public"                # public / private / hidden
    privacy_mode: str = "public"
    user_limit: int = 0
    locked: bool = False
    status: str = "active"
    control_message_id: Optional[int] = None
    control_channel_id: Optional[int] = None
    cleanup_status: Any = "active"
    empty_since: Optional[str] = None
    cleanup_due_at: Optional[str] = None
    last_empty_at: Optional[str] = None
    protected_until: Optional[str] = None
    last_voice_activity: Optional[str] = None
    co_host_ids: Optional[List[int]] = None
    dj_ids: Optional[List[int]] = None
    template_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def channel_id(self) -> int:
        return self.voice_channel_id

    @channel_id.setter
    def channel_id(self, val: int) -> None:
        self.voice_channel_id = val



@dataclass
class RoomMember:
    """A member with explicit access to a private/hidden DynamicRoom."""
    id: int
    room_channel_id: int
    member_id: int
    permission_type: str = "view"  # view / speak / manage
    added_at: str = ""

    @property
    def user_id(self) -> int:
        return self.member_id

    @user_id.setter
    def user_id(self, val: int) -> None:
        self.member_id = val


@dataclass
class RoomTemplate:
    """User-saved voice room preset/template."""
    guild_id: int
    user_id: int
    template_name: str
    settings: str
    created_at: str = ""


@dataclass
class RoomKnockRequest:
    """Knock / access request for a private dynamic voice room."""
    id: int
    room_id: int
    user_id: int
    status: str = "pending"  # pending, allowed, declined, expired
    expires_at: str = ""
    created_at: str = ""


# ---------------------------------------------------------------------------
# Mention Spam
# ---------------------------------------------------------------------------

@dataclass
class MentionSpamConfig:
    """Per-guild configuration for the mention spam protection engine."""
    guild_id: int
    enabled: bool = True
    warning_threshold: int = 5
    high_threshold: int = 10
    critical_threshold: int = 20
    window_seconds: int = 10
    cross_channel_threshold: int = 3
    repeat_message_threshold: int = 3
    action_low: str = "delete"
    action_high: str = "timeout"
    action_critical: str = "timeout_and_purge"
    timeout_duration_high: int = 600
    timeout_duration_critical: int = 86400
    purge_window_seconds: int = 60
    staff_exempt: bool = True
    updated_at: str = ""


@dataclass
class MentionSpamIncident:
    """A logged mention-spam incident for audit and analytics."""
    id: int
    guild_id: int
    user_id: int
    channel_id: int
    mention_count: int
    action_taken: str
    severity: str
    message_content: Optional[str] = None
    created_at: str = ""


# ---------------------------------------------------------------------------
# Pending Sync Operations (cloud sync queue)
# ---------------------------------------------------------------------------

@dataclass
class PendingSyncOperation:
    """A queued database sync operation waiting to be pushed to the cloud."""
    operation_id: str
    guild_id: int
    target: str              # e.g. "firebase" / "postgres"
    operation_type: str      # upsert / delete / etc.
    payload: Dict[str, Any]
    priority: int = 5
    status: str = "PENDING"  # PENDING / RETRYING / SYNCED / DEAD_LETTER
    attempt_count: int = 0
    incident_id: Optional[str] = None
    error_code: Optional[str] = None
    next_attempt: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Private Control Center
# ---------------------------------------------------------------------------

@dataclass
class PrivateControlConfig:
    """Configuration for Rai's owner-only private control centre channels."""
    guild_id: int
    enabled: bool = True
    auto_repair: bool = True
    control_hub_category_id: Optional[int] = None
    reports_category_id: Optional[int] = None
    security_category_id: Optional[int] = None
    admin_category_id: Optional[int] = None
    security_alerts_id: Optional[int] = None
    anti_nuke_id: Optional[int] = None
    security_log_id: Optional[int] = None
    audit_monitor_id: Optional[int] = None
    lockdown_control_id: Optional[int] = None
    admin_control_id: Optional[int] = None
    server_dashboard_id: Optional[int] = None
    bot_config_id: Optional[int] = None
    automation_control_id: Optional[int] = None
    backup_control_id: Optional[int] = None
    system_health_id: Optional[int] = None
    bot_report_channel_id: Optional[int] = None
    security_report_channel_id: Optional[int] = None
    system_report_channel_id: Optional[int] = None
    rai_security_role_id: Optional[int] = None
    rai_admin_role_id: Optional[int] = None
    owner_category_id: Optional[int] = None
    owner_ids: List[int] = field(default_factory=list)
    security_role_ids: List[int] = field(default_factory=list)
    admin_role_ids: List[int] = field(default_factory=list)
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Security Risk State
# ---------------------------------------------------------------------------

@dataclass
class SecurityRiskState:
    """Persistent risk posture snapshot for a guild."""
    guild_id: int
    risk_level: str = "NORMAL"      # NORMAL / ELEVATED / HIGH_ALERT / CRITICAL / EMERGENCY
    hysteresis_state: str = "NORMAL"
    threat_score: float = 0.0
    incident_id: Optional[str] = None
    cooldown_remaining: float = 0.0
    reason: Optional[str] = None
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Server Billboard
# ---------------------------------------------------------------------------

@dataclass
class ServerBillboardConfig:
    """Configuration for the live server-status billboard embed."""
    guild_id: int
    channel_id: Optional[int] = None
    message_id: Optional[int] = None
    is_active: bool = False
    update_interval: int = 60      # minutes
    last_updated_at: Optional[str] = None
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

@dataclass
class VerificationConfig:
    """Per-guild configuration for the interactive member verification system."""
    guild_id: int
    enabled: bool = False
    role_id: Optional[int] = None
    channel_id: Optional[int] = None
    verified_role_id: Optional[int] = None
    community_role_id: Optional[int] = None
    verify_channel_id: Optional[int] = None
    welcome_channel_id: Optional[int] = None
    min_account_age_hours: int = 0
    require_2fa: bool = False
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Workflow Engine
# ---------------------------------------------------------------------------

@dataclass
class Workflow:
    """A user-defined multi-step automated workflow pipeline."""
    id: str
    guild_id: int
    creator_id: int
    name: str
    status: str = "ACTIVE"           # ACTIVE / PAUSED / DISABLED
    trigger_type: str = "manual"
    description: Optional[str] = None
    trigger_config: Dict[str, Any] = field(default_factory=dict)
    missed_schedule_policy: str = "SKIP"  # SKIP / RUN_ONCE / RUN_ALL
    version: int = 1
    last_run_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class WorkflowStep:
    """A single action step within a Workflow."""
    id: str
    workflow_id: str
    step_order: int
    action_type: str
    action_config: Dict[str, Any] = field(default_factory=dict)
    condition_config: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "LOW"
    failure_policy: str = "STOP"     # STOP / CONTINUE / RETRY / FALLBACK
    timeout_seconds: int = 60
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class WorkflowEvent:
    """An event log entry emitted during workflow processing."""
    id: str
    workflow_id: str
    execution_id: str
    guild_id: int
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class WorkflowExecution:
    """A single recorded execution run of a Workflow."""
    id: str
    workflow_id: str
    guild_id: int
    trigger_event: str
    status: str = "RUNNING"          # RUNNING / COMPLETED / WAITING / FAILED
    current_step_order: int = 1
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    started_at: str = ""
    completed_at: Optional[str] = None
    version: int = 1
    context_json: Any = field(default_factory=dict)


@dataclass
class WorkflowStepExecution:
    """Result record for a single step within a WorkflowExecution."""
    id: str
    execution_id: str
    workflow_id: str = ""
    step_order: int = 1
    action_type: str = ""
    status: str = "PENDING"          # PENDING / SUCCESS / FAILED / SKIPPED
    step_id: Optional[str] = None
    attempt: int = 1
    result_data: Optional[str] = None
    result_json: Any = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: int = 0
    executed_at: str = ""
    started_at: str = ""
    completed_at: Optional[str] = None


@dataclass
class WorkflowWaitingTimer:
    """A persistent delay timer that pauses a workflow until a future time."""
    id: str
    execution_id: str
    workflow_id: str
    guild_id: int
    resume_at: str
    next_step_order: int
    status: str = "WAITING"          # WAITING / COMPLETED / CANCELLED
    created_at: str = ""


@dataclass
class WorkflowTemplate:
    """A built-in or community workflow template."""
    id: str
    name: str
    description: str
    trigger_type: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    trigger_config: Dict[str, Any] = field(default_factory=dict)
    category: str = "general"
    is_builtin: bool = True


@dataclass
class SubsystemHealthRecord:
    """Subsystem operational health record."""
    subsystem: str
    status: str
    details: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Channel Assignment & Interaction Telemetry Models
# ---------------------------------------------------------------------------

@dataclass
class GuildChannelConfig:
    """Guild-specific canonical channel assignment configuration."""
    guild_id: int
    security_alerts_channel_id: Optional[int] = None
    anti_nuke_channel_id: Optional[int] = None
    lockdown_control_channel_id: Optional[int] = None
    security_log_channel_id: Optional[int] = None
    audit_monitor_channel_id: Optional[int] = None

    security_report_channel_id: Optional[int] = None
    moderation_report_channel_id: Optional[int] = None
    music_report_channel_id: Optional[int] = None
    room_report_channel_id: Optional[int] = None
    bot_report_channel_id: Optional[int] = None
    system_report_channel_id: Optional[int] = None

    admin_control_channel_id: Optional[int] = None
    server_dashboard_channel_id: Optional[int] = None
    bot_config_channel_id: Optional[int] = None
    automation_control_channel_id: Optional[int] = None
    backup_control_channel_id: Optional[int] = None
    system_health_channel_id: Optional[int] = None

    created_at: str = ""
    updated_at: str = ""


@dataclass
class InteractionRecord:
    """Interaction execution record for ACK latency and reliability tracking."""
    request_id: str
    guild_id: Optional[int]
    user_id: int
    interaction_id: Optional[int]
    interaction_type: str
    command_name: str
    module: Optional[str]
    received_at: float
    ack_at: Optional[float] = None
    completed_at: Optional[float] = None
    ack_latency_ms: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = "COMPLETED"
    error_code: Optional[str] = None
    created_at: str = ""

