"""
Centralized Typed Result Model and Operation Diagnostics for 『RΛI』.

Core Responsibilities:
1. Replaces untyped booleans, swallowed exceptions, and ambiguous None returns
   with strongly typed, invariant-enforcing Result[T] containers.
2. Enforces Result Invariants:
   - SUCCESS => success=True, error=None
   - FAILURE / PARTIAL / PERMISSION_DENIED / etc. => success=False, error!=None
   - Rejects contradictory states (e.g. status=SUCCESS with success=False).
3. Defines stable machine-readable ErrorCodes.
4. Encapsulates typed operation data models for deletions, moderation, permissions,
   detection, database actions, and aggregated multi-step operations.
5. Provides rich failure classification: retryable vs non-retryable, role hierarchy,
   Discord rate limits, and subsystem isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

T = TypeVar("T")


class ResultStatus(str, Enum):
    """Normalized status values for RAI operation outcomes."""
    SUCCESS = "success"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    FAILED = "failed"
    PERMISSION_DENIED = "permission_denied"
    ROLE_HIERARCHY_BLOCKED = "role_hierarchy_blocked"
    CHANNEL_PERMISSION_DENIED = "channel_permission_denied"
    BOT_MISSING_PERMISSION = "bot_missing_permission"
    RATE_LIMITED = "rate_limited"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    ALREADY_HANDLED = "already_handled"
    DISCORD_ERROR = "discord_error"
    DATABASE_ERROR = "database_error"
    INTERNAL_ERROR = "internal_error"


class ErrorCodes:
    """Stable, machine-readable diagnostic error codes."""
    # Detection
    MENTION_THRESHOLD_EXCEEDED = "MENTION_THRESHOLD_EXCEEDED"
    MENTION_RATE_LIMIT = "MENTION_RATE_LIMIT"
    CROSS_CHANNEL_SPAM = "CROSS_CHANNEL_SPAM"
    REPEATED_MENTION_SPAM = "REPEATED_MENTION_SPAM"
    NO_THREAT = "NO_THREAT"
    SUSPICIOUS = "SUSPICIOUS"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL = "CRITICAL"
    IGNORED = "IGNORED"
    EXEMPT = "EXEMPT"

    # Permissions
    MISSING_MANAGE_MESSAGES = "MISSING_MANAGE_MESSAGES"
    MISSING_MODERATE_MEMBERS = "MISSING_MODERATE_MEMBERS"
    MISSING_BAN_MEMBERS = "MISSING_BAN_MEMBERS"
    MISSING_KICK_MEMBERS = "MISSING_KICK_MEMBERS"
    MISSING_MANAGE_CHANNELS = "MISSING_MANAGE_CHANNELS"
    MISSING_MANAGE_ROLES = "MISSING_MANAGE_ROLES"
    MISSING_VIEW_AUDIT_LOG = "MISSING_VIEW_AUDIT_LOG"
    ROLE_HIERARCHY_BLOCKED = "ROLE_HIERARCHY_BLOCKED"
    CHANNEL_PERMISSION_DENIED = "CHANNEL_PERMISSION_DENIED"
    BOT_MISSING_PERMISSION = "BOT_MISSING_PERMISSION"

    # Discord Operations
    MESSAGE_NOT_FOUND = "MESSAGE_NOT_FOUND"
    ALREADY_DELETED = "ALREADY_DELETED"
    MEMBER_NOT_FOUND = "MEMBER_NOT_FOUND"
    INVALID_DURATION = "INVALID_DURATION"
    DISCORD_API_ERROR = "DISCORD_API_ERROR"
    DISCORD_RATE_LIMIT = "DISCORD_RATE_LIMIT"

    # Database
    DATABASE_ERROR = "DATABASE_ERROR"
    DATABASE_TIMEOUT = "DATABASE_TIMEOUT"
    INCIDENT_SAVED = "INCIDENT_SAVED"
    INCIDENT_ALREADY_EXISTS = "INCIDENT_ALREADY_EXISTS"

    # System & Execution
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    ALREADY_HANDLED = "ALREADY_HANDLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class ResultError:
    """Structured, machine-readable error diagnostic."""
    code: str
    message: str
    retryable: bool = False
    details: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class Result(Generic[T]):
    """
    Centralized, strongly typed result container.
    Enforces strict invariants to eliminate ambiguous return values.
    """
    status: ResultStatus
    success: bool
    data: Optional[T] = None
    error: Optional[ResultError] = None
    incident_id: Optional[str] = None

    def __post_init__(self) -> None:
        """Enforces result invariants upon creation."""
        # 1. SUCCESS Invariant: success MUST be True, error MUST be None
        if self.status == ResultStatus.SUCCESS:
            if not self.success:
                raise ValueError(
                    f"Result invariant violation: status is SUCCESS but success=False."
                )
            if self.error is not None:
                raise ValueError(
                    f"Result invariant violation: status is SUCCESS but error is populated ({self.error})."
                )
        else:
            # 2. NON-SUCCESS Invariant: success MUST be False, error MUST NOT be None
            if self.success:
                raise ValueError(
                    f"Result invariant violation: status is {self.status.value} but success=True."
                )
            if self.error is None:
                raise ValueError(
                    f"Result invariant violation: non-success status ({self.status.value}) requires an error object."
                )

    def __bool__(self) -> bool:
        """
        Boolean coercion helper for backwards compatibility.
        If data has a 'detected' attribute, evaluates to data.detected.
        Otherwise evaluates to self.success.
        """
        if self.data is not None and hasattr(self.data, "detected"):
            return bool(getattr(self.data, "detected"))
        return self.success

    @property
    def value(self) -> Optional[T]:
        """Backwards compatibility alias for data."""
        return self.data

    @property
    def is_success(self) -> bool:
        """Backwards compatibility alias for success."""
        return self.success

    @classmethod
    def ok(cls, data: Optional[T] = None, incident_id: Optional[str] = None) -> Result[T]:
        """Creates a verified SUCCESS result."""
        return cls(
            status=ResultStatus.SUCCESS,
            success=True,
            data=data,
            error=None,
            incident_id=incident_id,
        )

    @classmethod
    def fail(
        cls,
        status: ResultStatus,
        code: str,
        message: str,
        retryable: bool = False,
        incident_id: Optional[str] = None,
        data: Optional[T] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Result[T]:
        """Creates a verified failure result."""
        if status == ResultStatus.SUCCESS:
            raise ValueError("Result.fail cannot be called with ResultStatus.SUCCESS.")
        return cls(
            status=status,
            success=False,
            data=data,
            error=ResultError(code=code, message=message, retryable=retryable, details=details),
            incident_id=incident_id,
        )

    @classmethod
    def success(cls, data: Optional[T] = None, incident_id: Optional[str] = None) -> Result[T]:
        """Alias for ok()."""
        return cls.ok(data=data, incident_id=incident_id)

    @classmethod
    def failure(
        cls,
        error: str = "Operation failed",
        status: ResultStatus = ResultStatus.FAILED,
        error_code: str = ErrorCodes.INTERNAL_ERROR,
        retryable: bool = False,
        incident_id: Optional[str] = None,
        data: Optional[T] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Result[T]:
        """Creates a verified failure result with keyword-arg flexibility."""
        return cls.fail(
            status=status,
            code=error_code,
            message=str(error),
            retryable=retryable,
            incident_id=incident_id,
            data=data,
            details=details,
        )


    @classmethod
    def partial(
        cls,
        code: str,
        message: str,
        data: Optional[T] = None,
        incident_id: Optional[str] = None,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> Result[T]:
        """Creates a PARTIAL outcome result (some operations succeeded, some failed)."""
        return cls.fail(
            status=ResultStatus.PARTIAL,
            code=code,
            message=message,
            retryable=retryable,
            incident_id=incident_id,
            data=data,
            details=details,
        )

    @classmethod
    def permission_denied(
        cls,
        code: str,
        message: str,
        incident_id: Optional[str] = None,
        data: Optional[T] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Result[T]:
        """Creates a PERMISSION_DENIED result (non-retryable)."""
        return cls.fail(
            status=ResultStatus.PERMISSION_DENIED,
            code=code,
            message=message,
            retryable=False,
            incident_id=incident_id,
            data=data,
            details=details,
        )

    @classmethod
    def role_hierarchy_blocked(
        cls,
        message: str = "Target member or role is higher than or equal to bot's highest role.",
        code: str = ErrorCodes.ROLE_HIERARCHY_BLOCKED,
        incident_id: Optional[str] = None,
        data: Optional[T] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Result[T]:
        """Creates a ROLE_HIERARCHY_BLOCKED result (non-retryable)."""
        return cls.fail(
            status=ResultStatus.ROLE_HIERARCHY_BLOCKED,
            code=code,
            message=message,
            retryable=False,
            incident_id=incident_id,
            data=data,
            details=details,
        )

    @classmethod
    def rate_limited(
        cls,
        message: str = "Discord rate limit reached.",
        code: str = ErrorCodes.DISCORD_RATE_LIMIT,
        retryable: bool = True,
        incident_id: Optional[str] = None,
        data: Optional[T] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Result[T]:
        """Creates a RATE_LIMITED result (retryable)."""
        return cls.fail(
            status=ResultStatus.RATE_LIMITED,
            code=code,
            message=message,
            retryable=retryable,
            incident_id=incident_id,
            data=data,
            details=details,
        )

    @classmethod
    def not_found(
        cls,
        message: str,
        code: str = ErrorCodes.MESSAGE_NOT_FOUND,
        incident_id: Optional[str] = None,
        data: Optional[T] = None,
    ) -> Result[T]:
        """Creates a NOT_FOUND result (non-retryable)."""
        return cls.fail(
            status=ResultStatus.NOT_FOUND,
            code=code,
            message=message,
            retryable=False,
            incident_id=incident_id,
            data=data,
        )

    @classmethod
    def already_handled(
        cls,
        message: str,
        code: str = ErrorCodes.ALREADY_HANDLED,
        incident_id: Optional[str] = None,
        data: Optional[T] = None,
    ) -> Result[T]:
        """Creates an ALREADY_HANDLED result (non-retryable)."""
        return cls.fail(
            status=ResultStatus.ALREADY_HANDLED,
            code=code,
            message=message,
            retryable=False,
            incident_id=incident_id,
            data=data,
        )

    @classmethod
    def skipped(
        cls,
        reason: str,
        code: str = ErrorCodes.IGNORED,
        incident_id: Optional[str] = None,
        data: Optional[T] = None,
    ) -> Result[T]:
        """Creates a SKIPPED result (e.g. feature disabled, user exempt)."""
        return cls.fail(
            status=ResultStatus.SKIPPED,
            code=code,
            message=reason,
            retryable=False,
            incident_id=incident_id,
            data=data,
        )

    @classmethod
    def discord_error(
        cls,
        message: str,
        code: str = ErrorCodes.DISCORD_API_ERROR,
        retryable: bool = True,
        incident_id: Optional[str] = None,
        data: Optional[T] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Result[T]:
        """Creates a DISCORD_ERROR result."""
        return cls.fail(
            status=ResultStatus.DISCORD_ERROR,
            code=code,
            message=message,
            retryable=retryable,
            incident_id=incident_id,
            data=data,
            details=details,
        )

    @classmethod
    def database_error(
        cls,
        message: str,
        code: str = ErrorCodes.DATABASE_ERROR,
        retryable: bool = True,
        incident_id: Optional[str] = None,
        data: Optional[T] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Result[T]:
        """Creates a DATABASE_ERROR result."""
        return cls.fail(
            status=ResultStatus.DATABASE_ERROR,
            code=code,
            message=message,
            retryable=retryable,
            incident_id=incident_id,
            data=data,
            details=details,
        )

    @classmethod
    def internal_error(
        cls,
        message: str,
        code: str = ErrorCodes.INTERNAL_ERROR,
        incident_id: Optional[str] = None,
        data: Optional[T] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Result[T]:
        """Creates an INTERNAL_ERROR result."""
        return cls.fail(
            status=ResultStatus.INTERNAL_ERROR,
            code=code,
            message=message,
            retryable=False,
            incident_id=incident_id,
            data=data,
            details=details,
        )


# ==========================================
# TYPED OPERATION DATA MODELS
# ==========================================

@dataclass(frozen=True)
class DeleteMessageData:
    """Diagnostic data for message deletion operations."""
    message_id: int
    channel_id: int
    deleted: bool = True


@dataclass(frozen=True)
class ModerationData:
    """Diagnostic data for user moderation / restriction operations."""
    target_id: int
    action: str
    duration_seconds: Optional[int] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class PermissionCheckData:
    """Diagnostic data for permission verification operations."""
    permission: str
    available: bool
    reason: Optional[str] = None
    channel_id: Optional[int] = None


@dataclass(frozen=True)
class PermissionFailureData:
    """Diagnostic data for permission failure operations."""
    permission: str
    action: str
    channel_id: Optional[int]
    reason: str
    retryable: bool = False


@dataclass(frozen=True)
class SecurityDetectionData:
    """Diagnostic data for security detection outcomes."""
    severity: str
    mention_count: int
    message_count: int
    channels_affected: int
    incident_id: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class OperationSummary:
    """Aggregate summary for multi-step batch or pipeline operations."""
    attempted: int
    succeeded: int
    failed: int
    skipped: int = 0
    permission_denied: int = 0

    @property
    def is_all_success(self) -> bool:
        return self.attempted > 0 and self.succeeded == self.attempted

    @property
    def is_partial(self) -> bool:
        return self.succeeded > 0 and self.succeeded < self.attempted

    @property
    def overall_status(self) -> ResultStatus:
        if self.attempted == 0:
            return ResultStatus.SKIPPED
        if self.is_all_success:
            return ResultStatus.SUCCESS
        if self.is_partial:
            return ResultStatus.PARTIAL
        if self.permission_denied == self.attempted:
            return ResultStatus.PERMISSION_DENIED
        return ResultStatus.FAILED


@dataclass(frozen=True)
class DatabaseResultData:
    """Diagnostic data for database storage operations."""
    operation: str
    incident_id: Optional[str] = None
    affected_rows: int = 0
    success: bool = True
    table: Optional[str] = None
