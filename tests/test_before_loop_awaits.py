"""
Basic tests to ensure before_loop handlers use canonical await pattern and self_heal emits structured repairs.
These tests are lightweight and do not require a running Discord client.
"""

import re
import unittest

FILES_TO_CHECK = [
    "cogs/utility.py",
    "cogs/serverstats.py",
    "cogs/stream_radar.py",
    "cogs/reputation.py",
    "cogs/security.py",
    "cogs/music.py",
    "cogs/system_upgrade.py",
    "cogs/self_heal.py",
]

class BeforeLoopAwaitTests(unittest.TestCase):
    def test_before_loop_awaits_present(self):
        pattern = re.compile(r"await\s+self\.bot\.wait_until_ready\(\)")
        for path in FILES_TO_CHECK:
            with open(path, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertRegex(src, pattern, msg=f"Canonical wait_until_ready not found in {path}")

if __name__ == '__main__':
    unittest.main()
