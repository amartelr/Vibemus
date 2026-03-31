
import sys
import os
from datetime import datetime

# Add the project root to sys.path to import our modules
sys.path.append(os.getcwd())

from src.core.manager import Manager
from src.config import Config

def rescue_library():
    print("\n" + "="*60)
    print("🚨 VIBEMUS EMERGENCY RESCUE SCRIPT")
    print("="*60)
    
    manager = Manager()
    
    # 1. Refresh cache first to see current mess on YT
    print("\n1️⃣ Refreshing YouTube Music cache...")
    manager.refresh_source_cache_only()
    source_cache = manager._load_source_cache()
    
    # 2. Map current YT locations: vid -> set of playlist_names
    # This helps us find where a song ended up.
    yt_locations = {}
    for pl_name, items in source_cache.items():
        for it in items:
            vid = it.get('videoId')
            if not vid: continue
            if vid not in yt_locations:
                yt_locations[vid] = set()
            yt_locations[vid].add(pl_name.lower())

    # 3. Read the restored Google Sheet
    print("\n2️⃣ Reading restored Google Sheet...")
    sheet_songs = manager.sheets.get_songs_records()
    print(f"   Found {len(sheet_songs)} total songs in Sheet.")

    # 4. Resolve Playlist IDs from YouTube for moving
    print("\n3️⃣ Resolving YouTube Playlist IDs...")
    library_playlists = manager.yt.get_library_playlists()
    playlist_map = {p['title'].strip().lower(): p['playlistId'] for p in library_playlists if 'title' in p}
    
    inbox_pid = Config.PLAYLIST_ID
    if not inbox_pid:
        print("❌ Error: PLAYLIST_ID not found in Config.")
        return

    # Counter for stats
    stats = {"restored_to_inbox": 0, "moved_to_target": 0, "errors": 0, "no_action": 0}

    # 5. Process every song in the Sheet and enforce its location
    print("\n4️⃣ Synchronizing YouTube Music with Sheet state...")
    
    for i, song in enumerate(sheet_songs):
        vid = song.get('Video ID')
        if not vid: continue
        
        expected_pl = str(song.get('Playlist', '')).strip()
        expected_pl_lower = expected_pl.lower()
        title = song.get('Title', vid)
        artist = song.get('Artist', 'Unknown')
        
        current_pls = yt_locations.get(vid, set())
        
        # Scenario A: Song SHOULD be in Inbox (#)
        if expected_pl == '#':
            if '#' in current_pls:
                stats["no_action"] += 1
                continue # Already in inbox
            
            print(f"  [INBOX] Restoring '{artist} - {title}' to #")
            try:
                # Add to inbox
                manager.yt.add_playlist_items(inbox_pid, [vid])
                # Remove from wherever else it was (except # which we just added)
                for other_pl in list(current_pls):
                    if other_pl == '#': continue
                    other_pid = playlist_map.get(other_pl)
                    if other_pid:
                        # Find the correct item object to remove
                        items_in_other = [it for it in source_cache.get(other_pl, []) if it.get('videoId') == vid]
                        if items_in_other:
                            manager.yt.remove_playlist_items(other_pid, [items_in_other[0]])
                
                stats["restored_to_inbox"] += 1
            except Exception as e:
                print(f"    ❌ Error restoring to inbox: {e}")
                stats["errors"] += 1

        # Scenario B: Song SHOULD be in a specific playlist (Indie Pop, etc.)
        elif expected_pl and expected_pl != '#':
            target_pid = playlist_map.get(expected_pl_lower)
            if not target_pid:
                # Target playlist not found on YT
                stats["errors"] += 1
                continue
                
            if expected_pl_lower in current_pls:
                stats["no_action"] += 1
                continue # Already in the right place
            
            print(f"  [MOVE] Returning '{artist} - {title}' to '{expected_pl}'")
            try:
                # Add to target
                manager.yt.add_playlist_items(target_pid, [vid])
                # Remove from other places
                for other_pl in list(current_pls):
                    if other_pl == expected_pl_lower: continue
                    # Get correct PID (Inbox or other)
                    other_pid = inbox_pid if other_pl == '#' else playlist_map.get(other_pl)
                    if other_pid:
                        items_in_other = [it for it in source_cache.get(other_pl, []) if it.get('videoId') == vid]
                        if items_in_other:
                            manager.yt.remove_playlist_items(other_pid, [items_in_other[0]])
                
                stats["moved_to_target"] += 1
            except Exception as e:
                print(f"    ❌ Error moving song: {e}")
                stats["errors"] += 1
        
        # Log progress every 100 songs
        if (i+1) % 100 == 0:
            print(f"   Progress: {i+1}/{len(sheet_songs)}Processed...")

    print("\n" + "="*60)
    print("🏁 RESCUE COMPLETED")
    print("-" * 60)
    print(f"✅ Restored to Inbox (#): {stats['restored_to_inbox']}")
    print(f"✅ Returned to Folders:   {stats['moved_to_target']}")
    print(f"ℹ️ Already correct:       {stats['no_action']}")
    print(f"❌ Errors:                {stats['errors']}")
    print("=" * 60)
    
    # Final cache refresh to be clean
    print("\nPerforming final cache refresh...")
    manager.refresh_source_cache_only()
    print("Done! Your library should now match your restored Sheet exactly.")

if __name__ == "__main__":
    rescue_library()
