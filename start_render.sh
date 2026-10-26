#!/bin/bash
set -e

echo "=== Starting Rem (Your Anime Music Companion) on Render ==="

# 1. Update settings.json from environment variables or defaults
python -c "
import json, os

settings_path = 'settings.json'
try:
    with open(settings_path, 'r', encoding='utf-8') as f:
        s = json.load(f)
except Exception:
    s = {}

s['token'] = os.getenv('MUSIC_BOT_TOKEN') or os.getenv('TOKEN') or s.get('token', '')
s['client_id'] = int(os.getenv('DISCORD_CLIENT_ID') or os.getenv('CLIENT_ID') or s.get('client_id') or 1556676516274905218)
s['mongodb_url'] = os.getenv('MONGODB_URL') or s.get('mongodb_url', 'mongodb+srv://kishorerai390_db_user:MusicMaid1@musicmaid.8gj5cff.mongodb.net/?retryWrites=true&w=majority')
s['mongodb_name'] = os.getenv('MONGODB_NAME') or s.get('mongodb_name', 'MusicMaid')

s['nodes'] = {
    'SERENETIA_V4': {
        'host': 'lavalinkv4.serenetia.com',
        'port': 443,
        'password': 'https://seretia.link/discord',
        'secure': True,
        'identifier': 'SERENETIA_V4'
    },
    'MILLOHOST_V4': {
        'host': 'lava-v4.millohost.my.id',
        'port': 443,
        'password': 'https://discord.gg/mjS5J2K3ep',
        'secure': True,
        'identifier': 'MILLOHOST_V4'
    },
    'LOCAL_LAVALINK': {
        'host': '127.0.0.1',
        'port': 2333,
        'password': 'youshallnotpass',
        'secure': False,
        'identifier': 'LOCAL_LAVALINK'
    }
}
s['embed_color'] = '0xa855f7'
s['activity'] = [
    {
        'type': 'listening',
        'name': '/play | Rem 🎧💜',
        'status': 'online'
    },
    {
        'type': 'listening',
        'name': '/help | Your Anime Music Companion 💜',
        'status': 'online'
    },
    {
        'type': 'watching',
        'name': 'your voice channels 🎵',
        'status': 'online'
    }
]

if not s.get('default_controller'):
    s['default_controller'] = {
        'embeds': {
            'active': {
                'title': {
                    'name': '🎵 Now Playing in @@channel_name@@',
                    'url': '@@track_url@@'
                },
                'description': '### [@@track_name@@](@@track_url@@)\n> 👤 **Artist:** `@@track_author@@`\n> 🎧 **Requester:** @@track_requester_mention@@\n> 🎚️ **Volume:** `@@volume@@%` • 🔁 **Loop:** `@@loop_mode@@`',
                'thumbnail': '@@track_thumbnail@@',
                'footer': {
                    'text': 'Queue: @@queue_length@@ tracks • Rem 🎧💜',
                    'icon_url': 'https://rai-discord-bot.onrender.com/public/musicmaid_avatar.jpg'
                }
            },
            'inactive': {
                'title': {
                    'name': '💜 Rem — Your Anime Music Companion',
                    'url': 'https://rai-discord-bot.onrender.com'
                },
                'description': '### Ready for music! (•ᴗ•) 🌸\nJoin a voice channel and type `/play <song name or link>` to stream with Rem!',
                'thumbnail': 'https://rai-discord-bot.onrender.com/public/musicmaid_avatar.jpg',
                'image': 'https://rai-discord-bot.onrender.com/public/musicmaid_banner.jpg',
                'footer': {
                    'text': 'Rem 🎧💜 • Your Anime Music Companion',
                    'icon_url': 'https://rai-discord-bot.onrender.com/public/musicmaid_avatar.jpg'
                }
            }
        }
    }

if 'logging' not in s:
    s['logging'] = {}
if 'level' not in s['logging']:
    s['logging']['level'] = {}
s['logging']['level']['musicmaid'] = 'INFO'

with open(settings_path, 'w', encoding='utf-8') as f:
    json.dump(s, f, indent=4)
print('Configured settings.json successfully!')
"

# 2. Ensure Lavalink.jar exists
mkdir -p lavalink
if [ ! -f "lavalink/Lavalink.jar" ]; then
    echo "Downloading Lavalink v4.2.2..."
    curl -L -o lavalink/Lavalink.jar https://github.com/lavalink-devs/Lavalink/releases/download/4.2.2/Lavalink.jar
fi

# 3. Determine Java executable
JAVA_CMD="java"
if [ -d "jre/bin" ]; then
    chmod +x jre/bin/* 2>/dev/null || true
    JAVA_CMD="$(pwd)/jre/bin/java"
fi
echo "Using Java: $($JAVA_CMD -version 2>&1 | head -n 1)"

# 4. Start Lavalink in background with capped heap
echo "Starting Lavalink server..."
cd lavalink
$JAVA_CMD -Xmx192m -Xms64m -jar Lavalink.jar &
LAVALINK_PID=$!
cd ..

echo "Waiting for Lavalink on port 2333..."
for i in {1..45}; do
    if curl -s -H "Authorization: youshallnotpass" http://127.0.0.1:2333/v4/info >/dev/null 2>&1; then
        echo "Lavalink is ready! (PID: $LAVALINK_PID)"
        break
    fi
    sleep 1
done

# 5. Start MusicMaid Bot
echo "Starting MusicMaid Bot..."
exec python -u main.py
