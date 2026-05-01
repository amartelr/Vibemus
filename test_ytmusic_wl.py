import sys
from src.services.yt_service import YTMusicService

try:
    ytm = YTMusicService()
    # Let's see if we can get Watch Later items via ytmusicapi
    res = ytm.yt.get_playlist("WL")
    print(f"WL items: {len(res.get('tracks', []))}")
except Exception as e:
    print(f"Error: {e}")
