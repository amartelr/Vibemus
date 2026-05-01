import sys
from src.services.youtube_data_service import YouTubeDataService

try:
    svc = YouTubeDataService()
    # Try getting items from WL
    items = svc._get_all_playlist_items("WL")
    print(f"Watch later items: {len(items)}")
    
    # Try adding a video to WL (e.g., some public video like rickroll or just an empty check)
    # To be safe, let's just see if we can read it.
except Exception as e:
    print(f"Error: {e}")
