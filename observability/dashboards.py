"""
Grafana Dashboard Generator for 『RΛI』.
Exports production-grade Grafana dashboard JSON models with panels for:
- Overall Bot Status & Health Matrix
- Security Engine, Incidents, and Threat Mitigation
- Multi-Database Latency & Sync Queue Telemetry (SQLite, PostgreSQL, Redis, Firebase)
- System Resources (CPU, Memory, Event Loop Latency)
- Music & AI Subsystem Telemetry
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional


def generate_grafana_dashboard() -> Dict[str, Any]:
    """Generates a complete Grafana dashboard specification in JSON format."""
    return {
        "annotations": {
            "list": [
                {
                    "builtIn": 1,
                    "datasource": "-- Grafana --",
                    "enable": True,
                    "hide": True,
                    "name": "Annotations & Alerts",
                    "type": "dashboard",
                }
            ]
        },
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
            # Row 1: Overall System Status
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
                "id": 100,
                "title": "『RΛI』 CORE PLATFORM OVERVIEW",
                "type": "row",
            },
            {
                "id": 1,
                "title": "Active Security Incidents",
                "type": "stat",
                "gridPos": {"h": 4, "w": 4, "x": 0, "y": 1},
                "targets": [{"expr": "rai_security_incidents_active", "refId": "A"}],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 1},
                                {"color": "red", "value": 5},
                            ],
                        },
                    }
                },
            },
            {
                "id": 2,
                "title": "Emergency Mode Active",
                "type": "stat",
                "gridPos": {"h": 4, "w": 4, "x": 4, "y": 1},
                "targets": [{"expr": "rai_emergency_mode_active", "refId": "A"}],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "red", "value": 1},
                            ],
                        },
                        "mappings": [
                            {"type": "value", "options": {"0": {"text": "NORMAL"}, "1": {"text": "EMERGENCY"}}}
                        ],
                    }
                },
            },
            {
                "id": 3,
                "title": "Sync Queue Backlog",
                "type": "stat",
                "gridPos": {"h": 4, "w": 4, "x": 8, "y": 1},
                "targets": [{"expr": "sum(rai_sync_queue_size)", "refId": "A"}],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "yellow", "value": 50},
                                {"color": "red", "value": 200},
                            ],
                        },
                    }
                },
            },
            {
                "id": 4,
                "title": "Active Music Sessions",
                "type": "stat",
                "gridPos": {"h": 4, "w": 4, "x": 12, "y": 1},
                "targets": [{"expr": "rai_music_sessions", "refId": "A"}],
            },
            {
                "id": 5,
                "title": "Discord API Errors / min",
                "type": "stat",
                "gridPos": {"h": 4, "w": 4, "x": 16, "y": 1},
                "targets": [{"expr": "sum(rate(rai_discord_api_errors_total[1m])) * 60", "refId": "A"}],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "yellow", "value": 2},
                                {"color": "red", "value": 10},
                            ],
                        },
                    }
                },
            },
            {
                "id": 6,
                "title": "Discord 429 Rate Limits / min",
                "type": "stat",
                "gridPos": {"h": 4, "w": 4, "x": 20, "y": 1},
                "targets": [{"expr": "sum(rate(rai_discord_rate_limits_total[1m])) * 60", "refId": "A"}],
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "red", "value": 1},
                            ],
                        },
                    }
                },
            },
            # Row 2: Security Subsystem
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 5},
                "id": 101,
                "title": "🛡️ SECURITY & THREAT CONTAINMENT",
                "type": "row",
            },
            {
                "id": 10,
                "title": "Security Events by Type",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 6},
                "targets": [
                    {
                        "expr": "sum by (event_type) (rate(rai_security_events_total[5m]))",
                        "legendFormat": "{{event_type}}",
                        "refId": "A",
                    }
                ],
            },
            {
                "id": 11,
                "title": "Mitigation Actions Executed",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 6},
                "targets": [
                    {
                        "expr": "sum by (action, status) (rate(rai_security_actions_total[5m]))",
                        "legendFormat": "{{action}} ({{status}})",
                        "refId": "A",
                    }
                ],
            },
            # Row 3: Multi-Database & Sync Architecture
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 14},
                "id": 102,
                "title": "💾 MULTI-DATABASE TELEMETRY & SYNC QUEUES",
                "type": "row",
            },
            {
                "id": 20,
                "title": "Database Operations Rate",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 15},
                "targets": [
                    {"expr": "sum(rate(rai_sqlite_operations_total[1m]))", "legendFormat": "SQLite", "refId": "A"},
                    {"expr": "sum(rate(rai_postgres_operations_total[1m]))", "legendFormat": "PostgreSQL", "refId": "B"},
                    {"expr": "sum(rate(rai_redis_operations_total[1m]))", "legendFormat": "Redis", "refId": "C"},
                    {"expr": "sum(rate(rai_firebase_operations_total[1m]))", "legendFormat": "Firebase", "refId": "D"},
                ],
            },
            {
                "id": 21,
                "title": "Pending Sync Queue Backlog by Target",
                "type": "timeseries",
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 15},
                "targets": [
                    {
                        "expr": "rai_sync_queue_size",
                        "legendFormat": "Queue: {{target}}",
                        "refId": "A",
                    }
                ],
            },
            # Row 4: Workers & AI
            {
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": 23},
                "id": 103,
                "title": "⚙️ WORKERS & ARTIFICIAL INTELLIGENCE",
                "type": "row",
            },
            {
                "id": 30,
                "title": "Self-Healing Worker Restarts",
                "type": "timeseries",
                "gridPos": {"h": 7, "w": 12, "x": 0, "y": 24},
                "targets": [
                    {
                        "expr": "sum by (worker_name) (increase(rai_worker_restarts_total[1h]))",
                        "legendFormat": "{{worker_name}}",
                        "refId": "A",
                    }
                ],
            },
            {
                "id": 31,
                "title": "AI Latency (p95)",
                "type": "timeseries",
                "gridPos": {"h": 7, "w": 12, "x": 12, "y": 24},
                "targets": [
                    {
                        "expr": "histogram_quantile(0.95, sum by (le, provider) (rate(rai_ai_latency_seconds_bucket[5m])))",
                        "legendFormat": "{{provider}} p95",
                        "refId": "A",
                    }
                ],
            },
        ],
        "refresh": "10s",
        "schemaVersion": 38,
        "style": "dark",
        "tags": ["rai", "discord-bot", "security", "production"],
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m"]},
        "timezone": "browser",
        "title": "『RΛI』 Autonomous Production Dashboard",
        "uid": "rai-production-overview",
        "version": 1,
    }


def export_grafana_dashboard(output_path: Optional[Path] = None) -> Path:
    """Exports dashboard JSON to specified path or default config location."""
    path = output_path or Path("config/grafana_dashboard.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(generate_grafana_dashboard(), f, indent=2)
    return path
