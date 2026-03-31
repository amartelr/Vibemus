
import sys
import os

sys.path.append(os.getcwd())
from src.core.manager import Manager
from src.config import Config

def force_sync():
    print("="*60)
    print("🚨 VIBEMUS BRUTE-FORCE YT-SYNC")
    print("="*60)
    
    manager = Manager()
    
    # 1. Refresh YT cache to know exactly where everything is right now
    print("\n1️⃣ Refreshing YouTube Music cache...")
    manager.refresh_source_cache_only()
    source_cache = manager._load_source_cache()
    
    # Map current YT locations: vid -> {pl_lower: item, pl_lower2: item}
    yt_locations = {}
    for pl_name, items in source_cache.items():
        pl_lower = pl_name.lower()
        for it in items:
            vid = it.get('videoId')
            if not vid: continue
            if vid not in yt_locations:
                yt_locations[vid] = {}
            yt_locations[vid][pl_lower] = it

    # 2. Read the PERFECT Google Sheet
    print("\n2️⃣ Reading master Google Sheet (Truth)...")
    sheet_songs = manager.sheets.get_songs_records()
    print(f"   Found {len(sheet_songs)} total songs in Sheet.")

    # 3. Resolve Playlist IDs from YouTube for moving
    print("\n3️⃣ Resolving YouTube Playlist IDs...")
    library_playlists = manager.yt.get_library_playlists()
    playlist_map = {p['title'].strip().lower(): p['playlistId'] for p in library_playlists if 'title' in p}
    playlist_map['#'] = Config.PLAYLIST_ID

    stats = {"added": 0, "removed": 0, "errors": 0}

    # 4. Synchronize
    print("\n4️⃣ Synchronizing YouTube Music with Sheet state...")
    
    for i, song in enumerate(sheet_songs):
        vid = song.get('Video ID')
        if not vid: continue
        
        expected_pl = str(song.get('Playlist', '')).strip()
        expected_pl_lower = expected_pl.lower()
        title = song.get('Title', vid)
        artist = song.get('Artist', 'Unknown')
        
        target_pid = playlist_map.get(expected_pl_lower)
        if not target_pid:
            continue
            
        current_locations = yt_locations.get(vid, {})
        
        # A) Is it missing from where it SHOULD be?
        if expected_pl_lower not in current_locations:
            print(f"  [ADD] '{artist} - {title}' missing from '{expected_pl}'... adding.")
            try:
                manager.yt.add_playlist_items(target_pid, [vid])
                stats["added"] += 1
            except Exception as e:
                print(f"    ❌ Error adding: {e}")
                stats["errors"] += 1
                
        # B) Is it located where it SHOULD NOT be?
        for current_pl_lower, item in current_locations.items():
            if current_pl_lower != expected_pl_lower:
                remove_pid = playlist_map.get(current_pl_lower)
                if not remove_pid: continue
                # It's in the wrong place! Remove it!
                print(f"  [REMOVE] '{artist} - {title}' is in '{current_pl_lower}' instead of '{expected_pl}'... removing.")
                try:
                    manager.yt.remove_playlist_items(remove_pid, [item])
                    stats["removed"] += 1
                except Exception as e:
                    print(f"    ❌ Error removing: {e}")
                    stats["errors"] += 1

    print("\n" + "="*60)
    print("🏁 FORCE SYNC COMPLETED")
    print(f"✅ Added to correct playlists: {stats['added']}")
    print(f"🗑️ Cleaned from wrong playlists: {stats['removed']}")
    print(f"❌ Errors: {stats['errors']}")
    print("="*60)
    print("\nPerforming final cache refresh...")
    manager.refresh_source_cache_only()

if __name__ == "__main__":
    force_sync()
