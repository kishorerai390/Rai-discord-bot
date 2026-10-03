import yt_dlp

opts = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}
ytdl = yt_dlp.YoutubeDL(opts)
try:
    print("Testing search...")
    data = ytdl.extract_info('ytsearch5:kalyani', download=False)
    for idx, entry in enumerate(data.get('entries', [])):
        print(f"Entry {idx}: title={entry.get('title')}")
        stream_url = entry.get('url')
        print(f"  stream_url={stream_url[:60] if stream_url else None}")
        print(f"  webpage_url={entry.get('webpage_url')}")
        print(f"  formats count={len(entry.get('formats', []))}")
except Exception as e:
    print("Search error:", e)

try:
    print("\nTesting single create query 'kalyani'...")
    data2 = ytdl.extract_info('kalyani', download=False)
    if 'entries' in data2:
        entry2 = data2['entries'][0]
    else:
        entry2 = data2
    print(f"Single title: {entry2.get('title')}")
    print(f"Single stream_url: {entry2.get('url')[:60] if entry2.get('url') else None}")
except Exception as e:
    print("Single error:", e)

try:
    print("\nTesting URL 'https://youtu.be/xvT1jH8B9AM'...")
    data3 = ytdl.extract_info('https://youtu.be/xvT1jH8B9AM', download=False)
    print(f"URL title: {data3.get('title')}")
    print(f"URL stream_url: {data3.get('url')[:60] if data3.get('url') else None}")
except Exception as e:
    print("URL error:", e)
