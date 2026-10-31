"""MIT License

Copyright (c) 2023 - present MusicMaid Development

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import json
import datetime
from pathlib import Path

BOND_FILE = Path("data/server_bonds.json")

# Milestone definitions: days -> (title, message, color)
MILESTONES = {
    7: (
        "🌱 One Week Together",
        "We've been together for a week~ Time flies when music is playing 🎵",
        0x5865F2,
    ),
    30: (
        "🌸 One Month Anniversary",
        "A whole month of music together! You're one of my favourites now 💜",
        0xa855f7,
    ),
    90: (
        "🌟 Three Months Strong",
        "Three months! That's hundreds of songs, thousands of memories. Thank you for keeping me around 🎧",
        0xF1C40F,
    ),
    180: (
        "💎 Half a Year",
        "Six months. I've watched this server grow. I'm so proud of you all 🥺💜",
        0x57F287,
    ),
    365: (
        "👑 One Year Anniversary!",
        "A FULL YEAR together! Do you know we've shared this journey for 365 days? I love you guys so much 💜🎶\n\n*- Rem 🎧*",
        0xFF69B4,
    ),
}


def load_bonds() -> dict:
    """Load server bond data from the JSON store."""
    if BOND_FILE.exists():
        try:
            return json.loads(BOND_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_bonds(data: dict):
    """Persist server bond data to the JSON store."""
    BOND_FILE.parent.mkdir(parents=True, exist_ok=True)
    BOND_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def check_milestone(guild_id: int) -> tuple | None:
    """Return (days, title, message, color) if a new milestone was just hit, else None."""
    data = load_bonds()
    gid = str(guild_id)
    now = datetime.datetime.utcnow()

    if gid not in data:
        data[gid] = {"first_seen": now.isoformat(), "milestones_hit": []}
        save_bonds(data)
        return None

    first = datetime.datetime.fromisoformat(data[gid]["first_seen"])
    days = (now - first).days
    hit = data[gid].get("milestones_hit", [])

    for milestone_days, (title, msg, color) in MILESTONES.items():
        if days >= milestone_days and milestone_days not in hit:
            hit.append(milestone_days)
            data[gid]["milestones_hit"] = hit
            save_bonds(data)
            return (milestone_days, title, msg, color)
    return None


def touch_server(guild_id: int):
    """Register a server as seen today, initialising its bond record if needed."""
    data = load_bonds()
    gid = str(guild_id)
    if gid not in data:
        data[gid] = {
            "first_seen": datetime.datetime.utcnow().isoformat(),
            "milestones_hit": [],
        }
        save_bonds(data)
