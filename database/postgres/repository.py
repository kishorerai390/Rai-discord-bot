"""
PostgreSQL Production Storage Repository for 『RΛI』.
Handles multi-guild long-term historical records with parameterized queries.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from database.postgres.connection import PostgresConnectionPool
from core.results import Result, ResultStatus, ErrorCodes, DatabaseResultData

logger = logging.getLogger("Rai.Database.Postgres.Repo")


class PostgresRepository:
    """
    Manages long-term permanent storage of incidents, security events,
    guild configurations, and audit telemetry in PostgreSQL.
    """

    def __init__(self, pool_manager: Optional[PostgresConnectionPool] = None):
        self.pool = pool_manager or PostgresConnectionPool.get_instance()

    async def init_schema(self) -> bool:
        """Initializes PostgreSQL production schema if not already present."""
        if not self.pool.is_connected:
            return False

        schema_sql = """
        CREATE TABLE IF NOT EXISTS pg_guild_configs (
            guild_id BIGINT PRIMARY KEY,
            security_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            automod_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            emergency_stop BOOLEAN NOT NULL DEFAULT FALSE,
            config_data JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS pg_security_incidents (
            incident_id VARCHAR(64) PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            severity VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'OPEN',
            user_id BIGINT,
            channels_affected BIGINT[],
            messages_affected INT DEFAULT 1,
            actions_attempted TEXT[],
            actions_successful TEXT[],
            actions_failed TEXT[],
            permission_failures TEXT[],
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        );

        CREATE INDEX IF NOT EXISTS idx_pg_incidents_guild
        ON pg_security_incidents(guild_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS pg_security_events (
            event_id VARCHAR(64) PRIMARY KEY,
            incident_id VARCHAR(64),
            guild_id BIGINT NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            severity VARCHAR(32) NOT NULL,
            actor_id BIGINT,
            channel_id BIGINT,
            action VARCHAR(64) NOT NULL,
            result VARCHAR(32) NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        );

        CREATE INDEX IF NOT EXISTS idx_pg_events_guild
        ON pg_security_events(guild_id, timestamp DESC);
        """
        try:
            async with self.pool._pool.acquire() as conn:
                await conn.execute(schema_sql)
            logger.info("PostgreSQL production schema initialized.")
            return True
        except Exception as e:
            self.pool.record_failure(e)
            logger.error(f"Failed to initialize PostgreSQL schema: {e}")
            return False

    async def save_incident(self, incident_data: Dict[str, Any]) -> Result[DatabaseResultData]:
        """Saves or updates security incident in PostgreSQL."""
        if not self.pool.is_connected:
            return Result.database_error(
                message="PostgreSQL connection offline. Sync queued locally.",
                code=ErrorCodes.DATABASE_ERROR,
                retryable=True,
            )

        inc_id = incident_data.get("incident_id")
        sql = """
        INSERT INTO pg_security_incidents (
            incident_id, guild_id, event_type, severity, status,
            user_id, channels_affected, messages_affected,
            actions_attempted, actions_successful, actions_failed,
            permission_failures, created_at, updated_at, metadata
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
            COALESCE($13, NOW()), NOW(), $14
        )
        ON CONFLICT (incident_id) DO UPDATE SET
            status = EXCLUDED.status,
            actions_successful = EXCLUDED.actions_successful,
            actions_failed = EXCLUDED.actions_failed,
            updated_at = NOW(),
            metadata = EXCLUDED.metadata;
        """
        try:
            async with self.pool._pool.acquire() as conn:
                await conn.execute(
                    sql,
                    inc_id,
                    incident_data.get("guild_id"),
                    incident_data.get("event_type", "SECURITY"),
                    incident_data.get("severity", "MEDIUM"),
                    incident_data.get("status", "RESOLVED"),
                    incident_data.get("user_id"),
                    incident_data.get("channels_affected", []),
                    incident_data.get("messages_affected", 1),
                    incident_data.get("actions_attempted", []),
                    incident_data.get("actions_successful", []),
                    incident_data.get("actions_failed", []),
                    incident_data.get("permission_failures", []),
                    incident_data.get("created_at"),
                    json.dumps(incident_data.get("metadata", {})),
                )
            return Result.ok(
                data=DatabaseResultData(
                    operation="save_incident",
                    incident_id=inc_id,
                    affected_rows=1,
                    table="pg_security_incidents",
                ),
                incident_id=inc_id,
            )
        except Exception as e:
            self.pool.record_failure(e)
            logger.error(f"PostgreSQL write failed for incident '{inc_id}': {e}")
            return Result.database_error(
                message=f"PostgreSQL incident save error: {e}",
                code=ErrorCodes.DATABASE_ERROR,
                retryable=True,
                incident_id=inc_id,
            )

    async def save_security_event(self, event_data: Dict[str, Any]) -> Result[DatabaseResultData]:
        """Saves security event to PostgreSQL."""
        if not self.pool.is_connected:
            return Result.database_error(
                message="PostgreSQL connection offline. Sync queued locally.",
                code=ErrorCodes.DATABASE_ERROR,
                retryable=True,
            )

        event_id = event_data.get("event_id")
        sql = """
        INSERT INTO pg_security_events (
            event_id, incident_id, guild_id, event_type, severity,
            actor_id, channel_id, action, result, timestamp, metadata
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), $10)
        ON CONFLICT (event_id) DO NOTHING;
        """
        try:
            async with self.pool._pool.acquire() as conn:
                await conn.execute(
                    sql,
                    event_id,
                    event_data.get("incident_id"),
                    event_data.get("guild_id"),
                    event_data.get("event_type", "SECURITY"),
                    event_data.get("severity", "MEDIUM"),
                    event_data.get("actor_id"),
                    event_data.get("channel_id"),
                    event_data.get("action", "unknown"),
                    event_data.get("result", "success"),
                    json.dumps(event_data.get("metadata", {})),
                )
            return Result.ok(
                data=DatabaseResultData(
                    operation="save_security_event",
                    incident_id=event_data.get("incident_id"),
                    affected_rows=1,
                    table="pg_security_events",
                )
            )
        except Exception as e:
            self.pool.record_failure(e)
            return Result.database_error(
                message=f"PostgreSQL event save error: {e}",
                code=ErrorCodes.DATABASE_ERROR,
                retryable=True,
            )
