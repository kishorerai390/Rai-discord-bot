"""
Phase 9 Production Hardening Tests — MusicMaid Web Platform.
Validates:
1. PWA manifest completeness (shortcuts, categories, icons, theme).
2. Offline network status bar HTML element existence.
3. Duplicate keydown handler removal (only one 'keydown' listener per page).
4. Keyboard shortcut engine completeness (all hotkeys wired).
5. Request deduplication guard (pendingActions Set) in dispatchCmd.
6. Enhanced manifest.json fields (start_url, scope, dir, lang, orientation).
"""

from __future__ import annotations

import json
import os
import re
import unittest


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(BASE_DIR, "public", "manifest.json")
UI_PY_PATH = os.path.join(BASE_DIR, "web", "ui.py")


def load_ui_src() -> str:
    with open(UI_PY_PATH, encoding="utf-8") as f:
        return f.read()


def load_manifest() -> dict:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestPhase9PWAManifest(unittest.TestCase):
    """PWA Manifest completeness checks."""

    def setUp(self):
        self.manifest = load_manifest()

    def test_manifest_has_name_and_short_name(self):
        self.assertIn("name", self.manifest)
        self.assertIn("short_name", self.manifest)
        self.assertTrue(len(self.manifest["name"]) > 0)

    def test_manifest_has_correct_start_url(self):
        self.assertEqual(self.manifest.get("start_url"), "/dashboard")

    def test_manifest_has_scope(self):
        self.assertIn("scope", self.manifest)
        self.assertEqual(self.manifest["scope"], "/")

    def test_manifest_has_standalone_display(self):
        self.assertEqual(self.manifest.get("display"), "standalone")

    def test_manifest_has_theme_and_background_color(self):
        self.assertIn("theme_color", self.manifest)
        self.assertIn("background_color", self.manifest)
        # Must be valid hex colors
        self.assertRegex(self.manifest["theme_color"], r"^#[0-9a-fA-F]{3,8}$")
        self.assertRegex(self.manifest["background_color"], r"^#[0-9a-fA-F]{3,8}$")

    def test_manifest_has_icons(self):
        icons = self.manifest.get("icons", [])
        self.assertTrue(len(icons) >= 1, "Manifest must have at least 1 icon")
        for icon in icons:
            self.assertIn("src", icon)
            self.assertIn("sizes", icon)
            self.assertIn("type", icon)

    def test_manifest_has_app_shortcuts(self):
        shortcuts = self.manifest.get("shortcuts", [])
        self.assertTrue(len(shortcuts) >= 2, "PWA manifest should have ≥2 app shortcuts")
        for s in shortcuts:
            self.assertIn("name", s)
            self.assertIn("url", s)

    def test_manifest_has_categories(self):
        cats = self.manifest.get("categories", [])
        self.assertIn("music", cats)

    def test_manifest_has_lang_and_dir(self):
        self.assertEqual(self.manifest.get("lang"), "en")
        self.assertIn(self.manifest.get("dir"), ["ltr", "rtl", "auto"])

    def test_manifest_has_description(self):
        desc = self.manifest.get("description", "")
        self.assertTrue(len(desc) > 10, "Manifest description should be informative")


class TestPhase9NetworkStatusBar(unittest.TestCase):
    """Verify offline banner is present in the HTML."""

    def setUp(self):
        self.ui_src = load_ui_src()

    def test_network_status_bar_html_exists(self):
        self.assertIn('id="network-status-bar"', self.ui_src)

    def test_network_status_bar_has_aria_role(self):
        # Should be role=alert for immediate announcement
        idx = self.ui_src.find('id="network-status-bar"')
        snippet = self.ui_src[max(0, idx - 50): idx + 200]
        self.assertIn('role="alert"', snippet)

    def test_network_status_bar_hidden_by_default(self):
        idx = self.ui_src.find('id="network-status-bar"')
        snippet = self.ui_src[max(0, idx - 50): idx + 300]
        self.assertIn("display:none", snippet)

    def test_online_offline_event_listeners_present(self):
        self.assertIn("window.addEventListener('offline'", self.ui_src)
        self.assertIn("window.addEventListener('online'", self.ui_src)

    def test_navigator_online_check_on_boot(self):
        self.assertIn("navigator.onLine", self.ui_src)


class TestPhase9KeyboardShortcutEngine(unittest.TestCase):
    """Verify Phase 8 keyboard shortcut engine completeness."""

    def setUp(self):
        self.ui_src = load_ui_src()

    def test_shortcut_space_toggles_play_pause(self):
        self.assertIn("togglePlayPause()", self.ui_src)

    def test_shortcut_arrow_right_skips(self):
        # dispatchCmd('SKIP') should be present
        self.assertIn("dispatchCmd('SKIP')", self.ui_src)

    def test_shortcut_arrow_left_goes_previous(self):
        self.assertIn("dispatchCmd('PREVIOUS')", self.ui_src)

    def test_shortcut_m_quick_mute(self):
        self.assertIn("quickMute()", self.ui_src)

    def test_shortcut_l_opens_lyrics(self):
        self.assertIn("openLyricsModal()", self.ui_src)

    def test_shortcut_question_opens_shortcuts_modal(self):
        self.assertIn("openShortcutsModal()", self.ui_src)

    def test_shortcut_f_fullscreen(self):
        self.assertIn("toggleFullscreenPlayer()", self.ui_src)

    def test_escape_closes_all_modals(self):
        # Escape handler should close multiple modals
        idx = self.ui_src.find("case 'Escape':")
        self.assertGreater(idx, 0, "Escape case must be in shortcut switch")
        snippet = self.ui_src[idx: idx + 500]
        self.assertIn("closeMobileSidebar", snippet)

    def test_input_guard_prevents_hotkeys_while_typing(self):
        # Must guard against input/textarea focus
        self.assertIn("tag === 'input'", self.ui_src)
        self.assertIn("tag === 'textarea'", self.ui_src)

    def test_no_duplicate_space_keydown_listener(self):
        # Old standalone spacebar listener should be removed
        # Count occurrences of "e.code === 'Space'" — should be 0 after cleanup
        count = self.ui_src.count("e.code === 'Space'")
        self.assertEqual(count, 0, "Duplicate spacebar listener must be removed")


class TestPhase9RequestDeduplication(unittest.TestCase):
    """Verify dispatchCmd has deduplication guard."""

    def setUp(self):
        self.ui_src = load_ui_src()

    def test_pending_actions_set_declared(self):
        self.assertIn("const pendingActions = new Set()", self.ui_src)

    def test_dispatch_checks_pending_before_sending(self):
        self.assertIn("pendingActions.has(action)", self.ui_src)

    def test_dispatch_adds_to_pending_set(self):
        self.assertIn("pendingActions.add(action)", self.ui_src)

    def test_dispatch_removes_from_pending_in_finally(self):
        self.assertIn("pendingActions.delete(action)", self.ui_src)


class TestPhase9PulseAnimation(unittest.TestCase):
    """Verify pulse-danger CSS keyframe exists for offline bar."""

    def setUp(self):
        self.ui_src = load_ui_src()

    def test_pulse_danger_keyframe_exists(self):
        self.assertIn("@keyframes pulse-danger", self.ui_src)

    def test_pulse_danger_used_on_network_bar(self):
        self.assertIn("animation:pulse-danger", self.ui_src)


if __name__ == "__main__":
    unittest.main()
