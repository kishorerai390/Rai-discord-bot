import yt_dlp
opts = {
    'quiet': True,
    'extract_flat': 'in_playlist',
    'extractor_args': {
        'youtube': {
            'player_client': ['ios', 'android', 'web']
        }
    }
}
ydl = yt_dlp.YoutubeDL(opts)
try:
    info = ydl.extract_info('https://www.youtube.com/watch?v=xvT1jH8B9AM', download=False)
    print("Direct URL extract title:", info.get('title'))
    print("Entries count:", len(info.get('entries', [])) if 'entries' in info else "No entries key")
except Exception as e:
    print("Error:", e)
