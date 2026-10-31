"""
Rai Music Official Single-Page Platform.
Identical compiled React SPA from the AppDeploy production application with complete
audio control, Discord auth, voice channel selection, and real-time playback.
"""

from pathlib import Path

_STATIC_PATH = Path(__file__).resolve().parent / "static" / "rai_music.html"

if _STATIC_PATH.is_file():
    RAI_MUSIC_HTML = _STATIC_PATH.read_text(encoding="utf-8")
else:
    RAI_MUSIC_HTML = """<!doctype html><html lang="en"><head><title>Rai Music — Your Server, Your Soundtrack</title></head><body><div id="root"></div></body></html>"""

__all__ = ["RAI_MUSIC_HTML"]
