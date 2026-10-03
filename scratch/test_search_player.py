import yt_dlp

opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch5',
    'extractor_args': {
        'youtube': {
            'player_client': ['ios', 'android', 'web']
        }
    }
}
ydl = yt_dlp.YoutubeDL(opts)
info = ydl.extract_info('kalyani', download=False)
entries = info.get('entries', [])
print(f"Found count: {len(entries)}")
for idx, e in enumerate(entries[:5]):
    title = e.get('title')
    has_url = bool(e.get('url'))
    webpage = e.get('webpage_url')
    print(f"{idx+1}. {title} | has_stream_url={has_url} | webpage={webpage}")
