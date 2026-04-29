from src.services.yt_service import YTMusicService
from src.config import Config

def test():
    yt = YTMusicService()
    pid = Config.PLAYLIST_ID
    print(f"Testing Playlist ID: {pid}")
    items = yt.get_playlist_items_with_status(pid, limit=5)
    for i, item in enumerate(items):
        print(f"Item {i}: {item.get('title')}")
        print(f"  videoId: {item.get('videoId')}")
        print(f"  setVideoId: {item.get('setVideoId')}")
        print(f"  Keys: {list(item.keys())}")

if __name__ == '__main__':
    test()
