"""
Phase 2 UI Design System & Navigation Verification Tests
Validates the MusicMaid 2.0 design tokens, animations, responsive navigation,
and Discord authentication gating.
"""

import re
import pytest
from web.ui import UI_HTML


def test_phase2_design_tokens_present():
    """Verify that MusicMaid 2.0 matte-black and neon-purple design tokens exist."""
    assert "--bg-dark: #07060d;" in UI_HTML
    assert "--bg-sidebar: #0b0914;" in UI_HTML
    assert "--bg-surface: #100d1e;" in UI_HTML
    assert "--bg-card:" in UI_HTML
    assert "--primary: #a855f7;" in UI_HTML
    assert "--card-border:" in UI_HTML
    assert "--card-border-hover:" in UI_HTML
    assert "--text: #f8fafc;" in UI_HTML


def test_phase2_reduced_motion_and_accessibility():
    """Verify reduced-motion media queries and accessible focus indicators exist."""
    assert "@media (prefers-reduced-motion: reduce)" in UI_HTML
    assert "animation-duration: 0.01ms !important;" in UI_HTML
    assert ":focus-visible" in UI_HTML
    assert "outline: 2px solid var(--primary);" in UI_HTML


def test_phase2_skeleton_and_animations():
    """Verify skeleton loader shimmer and page transition keyframes exist."""
    assert ".skeleton-box" in UI_HTML
    assert "@keyframes shimmerAnim" in UI_HTML
    assert ".view-fade-in" in UI_HTML
    assert "@keyframes viewFadeIn" in UI_HTML
    assert ".album-art-wrap" in UI_HTML


def test_phase2_navigation_structure():
    """Verify all 11 Master Plan navigation items exist in the sidebar DOM."""
    expected_nav_ids = [
        'id="nav-dashboard"',
        'id="nav-search"',
        'id="nav-player"',
        'id="nav-queue"',
        'id="nav-canvas"',
        'id="nav-library"',
        'id="nav-playlists"',
        'id="nav-history"',
        'id="nav-autodj"',
        'id="nav-audio"',
        'id="nav-analytics"',
        'id="nav-guilds"',
        'id="nav-settings"',
        'id="nav-system"',
    ]
    for nav_id in expected_nav_ids:
        assert nav_id in UI_HTML, f"Missing navigation element: {nav_id}"


def test_phase2_client_router_coverage():
    """Verify client-side router handleRoute supports all navigation paths."""
    expected_paths = [
        "path === '/player'",
        "path === '/playlists'",
        "path === '/history'",
        "path === '/analytics'",
        "path === '/settings'",
        "path === '/system'",
    ]
    for path_check in expected_paths:
        assert path_check in UI_HTML, f"Router missing path branch: {path_check}"


def test_phase2_view_renderers_exist():
    """Verify Phase 2 view functions exist in JavaScript."""
    expected_functions = [
        "function renderPlayer()",
        "function renderPlaylists()",
        "function renderHistory()",
        "function renderAnalytics()",
        "function renderSettings()",
        "function renderSystemHealth()",
        "function renderAuthGate(",
    ]
    for fn in expected_functions:
        assert fn in UI_HTML, f"Missing view function: {fn}"


def test_phase2_server_routes_registered():
    """Verify web/server.py registers all Phase 2 UI routes."""
    from web.server import RaiCommunityOSServer
    # Inspect server.py source directly to verify routes are registered for handle_ui
    with open("web/server.py", "r", encoding="utf-8") as f:
        src = f.read()

    for path in ["/player", "/playlists", "/history", "/analytics", "/system"]:
        assert f'"{path}"' in src, f"Route {path} missing from server.py ui_routes"
