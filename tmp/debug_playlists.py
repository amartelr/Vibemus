from src.services.yt_service import YTMusicService
from src.config import Config

def debug_playlists():
    yt = YTMusicService()
    playlists = yt.get_library_playlists()
    print(f"Total playlists found: {len(playlists)}")
    for p in playlists:
        title = p.get('title', '')
        count = p.get('count', 'N/A')
        print(f"'{title}': {count}")
        if 'shoegaze' in title.lower():
            print(f"  --> MATCH FOUND: '{title}' with count {count}")

if __name__ == '__main__':
    debug_playlists()
