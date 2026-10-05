"""
Core package for Rai.
Exports primary bot runner, supervisor, rate limiter, circuit breakers, and error taxonomy.
"""

from core.bot import SentinelBot
from core.supervisor import SystemSupervisor, SubsystemHealth
from core.rate_limiter import GlobalRateLimiter, ResourcePriority, ExponentialBackoff
from core.circuit_breaker import CircuitBreaker, CircuitBreakerRegistry, CircuitState
from core.health import HealthService
from core.errors import (
    RaiBaseException,
    RecoverableError,
    CriticalError,
    TransientAPIError,
    CircuitBreakerOpenError,
    MusicPlaybackError,
    DatabaseUnavailableError,
    SecurityPolicyViolation,
    generate_error_id,
    isolated_boundary,
)
from core.tasks import BackgroundTaskManager, safe_task_loop, TaskTelemetry
from core.permission_safety import (
    PermissionFailureType,
    PermissionResult,
    PermissionFailureTracker,
    permission_safe_execute,
    audit_guild_permissions,
    create_permission_audit_embed,
)
from core.interaction_manager import InteractionManager, InteractionState

__all__ = [
    "SentinelBot",
    "SystemSupervisor",
    "SubsystemHealth",
    "GlobalRateLimiter",
    "ResourcePriority",
    "ExponentialBackoff",
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "CircuitState",
    "HealthService",
    "RaiBaseException",
    "RecoverableError",
    "CriticalError",
    "TransientAPIError",
    "CircuitBreakerOpenError",
    "MusicPlaybackError",
    "DatabaseUnavailableError",
    "SecurityPolicyViolation",
    "generate_error_id",
    "isolated_boundary",
    "BackgroundTaskManager",
    "safe_task_loop",
    "TaskTelemetry",
    "PermissionFailureType",
    "PermissionResult",
    "PermissionFailureTracker",
    "permission_safe_execute",
    "audit_guild_permissions",
    "create_permission_audit_embed",
    "InteractionManager",
    "InteractionState",
]
