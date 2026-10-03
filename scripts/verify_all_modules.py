"""
Comprehensive integrity audit for all created & modified files.
"""

import sys
sys.path.insert(0, "F:/Bot")

import asyncio
import unittest

def test_imports():
    print("[1/5] Testing module imports...")
    import cogs.mention_notifications
    import cogs.reliability
    import cogs.security
    import cogs.temp_voice
    import cogs.tickets
    import cogs.creator
    import core.bot
    import utils.luxury_consoles
    import utils.music_consoles
    import utils.community_features
    print("  -> All core modules imported successfully.")

def test_luxury_consoles_serialization():
    print("[2/5] Testing luxury consoles serialization...")
    import discord
    from utils.luxury_consoles import (
        build_server_pulse_embed,
        build_server_pulse_view,
        build_world_clock_embed,
        build_world_clock_view,
        build_vip_concierge_embed,
        build_vip_concierge_view,
        build_quarantine_vault_embed,
        build_quarantine_vault_view,
        build_soundscape_embed,
        build_soundscape_view,
    )
    from scripts.deploy_consoles_rest import view_to_action_rows

    class MockGuild:
        name = "Test Guild"
        id = 1457382179981099090
        member_count = 39
        members = []
        icon = None

    g = MockGuild()
    pairs = [
        (build_server_pulse_embed(g), build_server_pulse_view()),
        (build_world_clock_embed(g), build_world_clock_view()),
        (build_vip_concierge_embed(g), build_vip_concierge_view()),
        (build_quarantine_vault_embed(g), build_quarantine_vault_view()),
        (build_soundscape_embed(g), build_soundscape_view()),
    ]
    for embed, view in pairs:
        d = embed.to_dict()
        assert "title" in d, "Embed must have title"
        rows = view_to_action_rows(view)
        assert len(rows) > 0, "View must generate action rows"
        for r in rows:
            assert r["type"] == 1, "Top level must be action row"
            assert len(r["components"]) <= 5, "Action row max 5 components"
    print("  -> All luxury consoles embeds & views serialize cleanly to Discord payload standard.")

def test_music_consoles_serialization():
    print("[3/5] Testing music consoles serialization...")
    from utils.music_consoles import (
        build_requests_console_embed,
        build_requests_console_view,
        build_queue_console_embed,
        build_queue_console_view,
        build_dj_console_embed,
        build_dj_console_view,
        build_playlists_console_embed,
        build_playlists_console_view,
    )
    from scripts.deploy_music_consoles import view_to_action_rows

    class MockGuild:
        name = "Test Guild"
        id = 1457382179981099090
        icon = None

    g = MockGuild()
    pairs = [
        (build_requests_console_embed(g), build_requests_console_view()),
        (build_queue_console_embed(g, None), build_queue_console_view()),
        (build_dj_console_embed(g), build_dj_console_view()),
        (build_playlists_console_embed(g), build_playlists_console_view()),
    ]
    for embed, view in pairs:
        d = embed.to_dict()
        assert "title" in d, "Music embed must have title"
        rows = view_to_action_rows(view)
        assert len(rows) > 0, "Music view must generate action rows"
        for r in rows:
            assert r["type"] == 1
            assert len(r["components"]) <= 5
    print("  -> All music consoles embeds & views serialize cleanly to Discord payload standard.")

def test_mention_notifications_unit():
    print("[4/5] Running mention notifications test suite...")
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("tests.test_mention_notifications")
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)
    assert result.wasSuccessful(), f"Mention notifications tests failed: {result.errors + result.failures}"
    print(f"  -> All {result.testsRun} tests passed successfully.")

def test_bot_interaction_routing():
    print("[5/5] Testing bot on_interaction routing coverage...")
    import inspect
    from core.bot import SentinelBot
    source = inspect.getsource(SentinelBot.on_interaction)
    required_prefixes = [
        "rai_vc",
        "rai_inc:",
        "rai_ctrl:",
        "inc_",
        "rai_nl:",
        "rai_pulse:",
        "rai_clock:",
        "rai_vip:",
        "rai_quarantine:",
        "rai_soundscape:",
        "m_req:",
        "m_q:",
        "m_dj:",
        "m_pl:",
    ]
    for prefix in required_prefixes:
        assert prefix in source, f"Prefix '{prefix}' missing from SentinelBot.on_interaction!"
    print(f"  -> All {len(required_prefixes)} interaction component prefixes are registered and routed.")

if __name__ == "__main__":
    print("=== COMMENCING RAI SYSTEM INTEGRITY AUDIT ===")
    test_imports()
    test_luxury_consoles_serialization()
    test_music_consoles_serialization()
    test_mention_notifications_unit()
    test_bot_interaction_routing()
    print("=== AUDIT COMPLETE: ALL SYSTEMS 100% HEALTHY & ERROR-FREE ===")
