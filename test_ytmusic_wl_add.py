import sys
from src.services.yt_service import YTMusicService

try:
    ytm = YTMusicService()
    # Let's see if we can add a video to WL
    res = ytm.yt.add_playlist_items("WL", ["dQw4w9WgXcQ"])
    print(f"Added? {res}")
    
    # Try removing it immediately if it succeeded
    if res.get('status') == 'STATUS_SUCCEEDED':
        # Removing from WL in ytmusicapi is tricky because we need the setVideoId
        pass
except Exception as e:
    print(f"Error: {e}")
