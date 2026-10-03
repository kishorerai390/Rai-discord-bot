import yt_dlp

opts = {
    'extract_flat': 'in_playlist',
    'quiet': True,
}
ydl = yt_dlp.YoutubeDL(opts)
try:
    res = ydl.extract_info('scsearch3:kalyani', download=False)
    entries = res.get('entries', [])
    print(f"Soundcloud count: {len(entries)}")
    for e in entries:
        print(f" - {e.get('title')}")
except Exception as e:
    print(f"Soundcloud error: {e}")
