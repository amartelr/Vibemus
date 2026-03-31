
import sys
import os

# Add the project root to sys.path to import our modules
sys.path.append(os.getcwd())

from src.core.manager import Manager
from src.config import Config

def dry_run_apply_moves():
    print("\n" + "="*60)
    print("🧪 DRY RUN: APPLY MANUAL PLAYLIST MOVES")
    print("="*60)
    print("  (Nothing will be changed on YouTube or Google Sheets)")
    
    manager = Manager()
    
    # 1. Load songs from sheet
    print("\n1️⃣ Loading songs from Google Sheets...")
    songs = manager.sheets.get_songs_records()
    print(f"   Total songs in sheet: {len(songs)}")

    # 2. Get cache (state in YouTube Music)
    print("\n2️⃣ Loading local YouTube Music cache...")
    source_cache = manager._load_source_cache()
    if not source_cache:
        print("❌ Source cache is empty! Run system refresh-cache first.")
        return

    # 3. Map out current positions in YouTube Music (according to cache)
    cache_vids = {}
    vid_to_cache_keys = {}
    
    for cache_key, items in source_cache.items():
        pl_lower = cache_key.lower()
        if pl_lower not in cache_vids:
            cache_vids[pl_lower] = set()
        for it in items:
            vid = it.get('videoId')
            if not vid: continue
            cache_vids[pl_lower].add(vid)
            if vid not in vid_to_cache_keys:
                vid_to_cache_keys[vid] = []
            vid_to_cache_keys[vid].append(cache_key)

    # 4. Resolve Playlist Names
    print("\n3️⃣ Resolving Playlist Names...")
    all_configured_playlists = {p.lower() for p in Config.SOURCE_PLAYLISTS}

    moves_counter = 0

    # 5. Review Moves
    print("\n4️⃣ Detected Changes (Excel vs YouTube Cache):")
    
    for song in songs:
        vid = song.get('Video ID')
        if not vid: continue
        
        target_pl = str(song.get('Playlist', '')).strip()
        if not target_pl or target_pl == '#':
            continue
            
        target_pl_lower = target_pl.lower()
        if target_pl_lower not in all_configured_playlists:
            continue
            
        # Is the song already where the excel says it should be?
        already_there = vid in cache_vids.get(target_pl_lower, set())
        if already_there:
            continue
            
        # Move detected!
        current_locations = vid_to_cache_keys.get(vid, [])
        artist = song.get('Artist', 'Unknown')
        title = song.get('Title', vid)
        
        moves_counter += 1
        
        if not current_locations:
            print(f"  [RESTORATION] '{artist} - {title}'")
            print(f"    - Current state: Missing from YouTube Music playlists")
            print(f"    - Action: Will add to '{target_pl}'")
        else:
            print(f"  [MOVE] '{artist} - {title}'")
            print(f"    - Current state: In {current_locations}")
            print(f"    - Action: Move to '{target_pl}' (will add to destination and remove from source)")
            
    print("\n" + "="*60)
    print(f"📊 SUMMARY OF DETECTED MOVES: {moves_counter}")
    print("="*60)
    if moves_counter == 0:
        print("  Everything is already in sync! No moves needed.")
    else:
        print("  Run 'vibemus playlist apply-moves' to execute these changes.")

if __name__ == "__main__":
    dry_run_apply_moves()
