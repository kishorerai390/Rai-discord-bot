import time
import yt_dlp

t0 = time.time()
opts = {
    'extract_flat': 'in_playlist',
    'quiet': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['ios', 'android', 'web']
        }
    }
}
ydl = yt_dlp.YoutubeDL(opts)
res = ydl.extract_info('ytsearch5:kalyani', download=False)
entries = res.get('entries', [])
print(f"Time: {time.time()-t0:.2f}s, Count: {len(entries)}")
for e in entries:
    print(f" - {e.get('title')} ({e.get('duration')}s) -> {e.get('url')}")
