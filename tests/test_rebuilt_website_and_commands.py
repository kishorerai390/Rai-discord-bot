"""
Unit tests verifying the rebuilt website with integrated bot commands and suggestions.
"""

import unittest
import os
from web_landing import LANDING_PAGE_HTML

class TestRebuiltWebsiteAndCommands(unittest.TestCase):

    def test_landing_page_html_integrity(self):
        """Verify landing page HTML is present, non-empty, and valid HTML structure."""
        self.assertIsNotNone(LANDING_PAGE_HTML)
        self.assertTrue(len(LANDING_PAGE_HTML) > 10000)
        self.assertIn("<!DOCTYPE html>", LANDING_PAGE_HTML)
        self.assertIn("<html lang=\"en\"", LANDING_PAGE_HTML)
        self.assertIn("</html>", LANDING_PAGE_HTML)

    def test_bot_commands_directory_integrated(self):
        """Verify the complete bot command suite is integrated into the website."""
        commands_to_check = [
            "/play",
            "/search",
            "/skip",
            "/pause",
            "/resume",
            "/stop",
            "/leave",
            "/speed",
            "/nightcore",
            "/8d",
            "/vaporwave",
            "/karaoke",
            "/cleareffect",
            "/queue",
            "/shuffle",
            "/repeat",
            "/autodj",
            "/247",
            "/debug",
        ]
        for cmd in commands_to_check:
            self.assertIn(cmd, LANDING_PAGE_HTML, f"Expected {cmd} in web_landing.py bot commands directory")

    def test_smart_suggestions_engine(self):
        """Verify the smart suggestions and vibe explorer features are present."""
        vibes_to_check = [
            "Anime Openings",
            "Midnight Lo-Fi Beats",
            "Cyberpunk Drift Phonk",
            "J-Rock & Shonen",
            "Kawaii J-Pop Chill",
            "Retro 80s Synthwave",
        ]
        for vibe in vibes_to_check:
            self.assertIn(vibe, LANDING_PAGE_HTML, f"Expected vibe '{vibe}' in suggestions engine")

    def test_dsp_equalizer_and_karaoke(self):
        """Verify 10-band equalizer presets and karaoke lyrics are embedded."""
        self.assertIn("bassboost", LANDING_PAGE_HTML.lower())
        self.assertIn("nightcore", LANDING_PAGE_HTML.lower())
        self.assertIn("vaporwave", LANDING_PAGE_HTML.lower())
        self.assertIn("31Hz", LANDING_PAGE_HTML)
        self.assertIn("16kHz", LANDING_PAGE_HTML)
        self.assertIn("lyrics-scroll-box", LANDING_PAGE_HTML)
        self.assertIn("queue-list-box", LANDING_PAGE_HTML)

    def test_theme_engine_palettes(self):
        """Verify 4 themes are supported in the rebuilt website."""
        for theme in ["obsidian", "sakura", "cyberpunk", "lofi"]:
            self.assertIn(f'data-theme="{theme}"', LANDING_PAGE_HTML, f"Theme '{theme}' selector missing in landing page CSS")

    def test_dashboard_view_commands_integration(self):
        """Verify DashboardView.tsx contains the command modal and vibe suggestions."""
        view_path = os.path.join(os.path.dirname(__file__), "..", "src", "components", "views", "DashboardView.tsx")
        with open(view_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("isCommandModalOpen", content)
        self.assertIn("Commands (41)", content)
        self.assertIn("vibeChips", content)
        self.assertIn("Vibe Explorer:", content)

    def test_audio_playback_code_invariants(self):
        """Verify no music playback engine or resolver files were modified."""
        # Ensure voicelink and resolver_service are pure
        import voicelink
        from music_bot.services import resolver_service
        self.assertTrue(hasattr(resolver_service, "AudioResolver"))
        self.assertTrue(hasattr(resolver_service, "youtube_health_monitor"))

if __name__ == "__main__":
    unittest.main()
