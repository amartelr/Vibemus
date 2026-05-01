import sys
from src.services.youtube_data_service import YouTubeDataService

try:
    svc = YouTubeDataService()
    # Try adding a video to WL
    res = svc._add_video_to_playlist("WL", "dQw4w9WgXcQ")
    print(f"Added? {res}")
except Exception as e:
    print(f"Error: {e}")
