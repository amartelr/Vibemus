import sys
from src.services.yt_service import YTMusicService

try:
    ytm = YTMusicService()
    res = ytm.yt.get_playlist("VLWL")
    print(f"VLWL items: {len(res.get('tracks', []))}")
except Exception as e:
    print(f"Error: {e}")
