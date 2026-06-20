import sys
import os

# Add root directory to path
sys.path.append(os.getcwd())

from src.services.sheets_service import SheetsService
from src.services.yt_service import YTMusicService

TARGET_DUPLICATES = [
    ("Andrew Garden", "In My Dream"),
    ("Andrew Garden", "heartbreaker"),
    ("Big Thief", "Mythological Beauty"),
    ("Camp Blu", "idk why!"),
    ("Charmer", "Roy's Our Boy"),
    ("Closed Tear", "Waste Away"),
    ("Death Cab for Cutie", "Riptides"),
    ("Faye Webster", "But Not Kiss"),
    ("Gurriers", "Top Of The Bill"),
    ("Jfarrari", "The Unknowing"),
    ("Mareux", "The Perfect Girl"),
    ("Mt. Joy", "More More More"),
    ("Palace", "Forever Ever After"),
    ("Protomartyr", "Elimination Dances"),
    ("Protomartyr", "Jumbo’s"),
    ("Protomartyr", "Make Way"),
    ("Protomartyr", "Processed By The Boys"),
    ("Protomartyr", "Worm In Heaven"),
    ("Radio Free Alice", "Empty Words"),
    ("Seahaven", "Andreas"),
    ("Shrimp", "The Old"),
    ("Wet Leg", "davina mccall"),
    ("Wombo", "Ugly Room"),
    ("Worry Club", "Anything Else"),
    ("bar italia", "omni shambles"),
    ("bby", "Voices In My Head, Pt. 2 (feat. Betty)")
]

def normalize(text):
    if not text:
        return ""
    # Lowercase, strip, and replace smart quotes with straight ones
    return str(text).lower().strip().replace("’", "'").replace("`", "'")

def get_best_record(records):
    # Determine the "best" record among duplicates (e.g. has more populated columns)
    best_rec = records[0]
    best_score = 0
    for r in records:
        score = sum(1 for k, v in r.items() if v != "" and v is not None)
        # Extra points if chord/tonality are populated
        if r.get("Chord"): score += 5
        if r.get("Tonality"): score += 5
        if score > best_score:
            best_score = score
            best_rec = r
    return best_rec

def run_dedup(dry_run=True):
    print(f"--- DEDUPLICATION RUN (DRY RUN = {dry_run}) ---")
    
    # 1. Initialize Services
    sheets = SheetsService()
    yt_service = YTMusicService()
    yt = yt_service.yt
    
    # Get all records from Songs sheet
    print("Reading Songs sheet...")
    all_songs = sheets.get_songs_records()
    print(f"Total songs in sheet: {len(all_songs)}")
    
    # Build normalize targets lookup
    targets = {(normalize(a), normalize(t)): (a, t) for a, t in TARGET_DUPLICATES}
    
    # Group songs from sheet by normalized key
    grouped_songs = {}
    for r in all_songs:
        artist_norm = normalize(r.get("Artist", ""))
        title_norm = normalize(r.get("Title", ""))
        key = (artist_norm, title_norm)
        if key in targets:
            if key not in grouped_songs:
                grouped_songs[key] = []
            grouped_songs[key].append(r)
            
    print(f"Found {len(grouped_songs)} of our target songs in the sheet.")
    
    new_songs_records = []
    removed_sheet_count = 0
    
    # Map from normalized key to the one record we will keep
    songs_to_keep = {}
    
    # We will rebuild the Songs list
    # For target duplicates, we keep only the best one.
    # For others, we keep them as is.
    seen_keys = set()
    for r in all_songs:
        artist_norm = normalize(r.get("Artist", ""))
        title_norm = normalize(r.get("Title", ""))
        key = (artist_norm, title_norm)
        
        if key in targets:
            if key not in seen_keys:
                # Find the best record among all duplicates of this key
                duplicates = grouped_songs[key]
                best_rec = get_best_record(duplicates)
                songs_to_keep[key] = best_rec
                new_songs_records.append(best_rec)
                seen_keys.add(key)
                removed_sheet_count += (len(duplicates) - 1)
                print(f"  Song '{best_rec.get('Artist')} - {best_rec.get('Title')}' has {len(duplicates)} occurrences in sheet. Keeping one (Playlist: '{best_rec.get('Playlist')}', Video ID: {best_rec.get('Video ID')}).")
        else:
            new_songs_records.append(r)
            
    # 2. Check and deduplicate YouTube playlists
    # Cache for playlist name -> playlistId
    print("Fetching library playlists...")
    playlists = yt.get_library_playlists(limit=None)
    playlist_map = {p['title']: p['playlistId'] for p in playlists}
    
    yt_removals = {} # playlistId -> list of track dictionaries to remove
    
    for key, duplicates in grouped_songs.items():
        if len(duplicates) <= 1:
            continue
        
        # We need to look up these tracks in their playlist
        # Usually they should belong to the same playlist
        best_rec = songs_to_keep[key]
        playlist_name = best_rec.get("Playlist", "")
        video_id = best_rec.get("Video ID", "")
        
        if not playlist_name:
            print(f"  ⚠ Song '{best_rec.get('Artist')} - {best_rec.get('Title')}' has no playlist assigned.")
            continue
            
        pid = playlist_map.get(playlist_name)
        if not pid:
            print(f"  ⚠ Playlist '{playlist_name}' not found in YouTube Music.")
            continue
            
        print(f"  Checking YT playlist '{playlist_name}' for duplicates of '{best_rec.get('Artist')} - {best_rec.get('Title')}'...")
        try:
            yt_playlist = yt.get_playlist(pid, limit=None)
            tracks = yt_playlist.get('tracks', [])
            
            # Find all track instances matching our video_id or artist/title
            matching_tracks = []
            for t in tracks:
                t_vid = t.get('videoId')
                t_artist = normalize(t.get('artists', [{}])[0].get('name', '')) if t.get('artists') else ""
                t_title = normalize(t.get('title', ''))
                
                # Match by video_id (very precise) or by artist & title if video_id is missing
                if (video_id and t_vid == video_id) or (normalize(best_rec.get('Artist')) == t_artist and normalize(best_rec.get('Title')) == t_title):
                    matching_tracks.append(t)
            
            if len(matching_tracks) > 1:
                print(f"    Found {len(matching_tracks)} instances of the song on YT Music playlist '{playlist_name}'.")
                # Keep the first instance, remove the rest
                to_remove = matching_tracks[1:]
                if pid not in yt_removals:
                    yt_removals[pid] = []
                yt_removals[pid].extend(to_remove)
                for tr in to_remove:
                    print(f"    [To Remove] Video ID: {tr.get('videoId')}, Set Video ID: {tr.get('setVideoId')}")
            else:
                print(f"    No duplicate instances found on YT Music playlist for this song (Count: {len(matching_tracks)}).")
        except Exception as e:
            print(f"    ⚠ Error retrieving/processing playlist '{playlist_name}': {e}")
            
    # 3. Apply Changes
    if not dry_run:
        # Overwrite sheet
        if removed_sheet_count > 0:
            print(f"Overwriting Songs sheet with {len(new_songs_records)} records...")
            sheets.overwrite_songs(new_songs_records)
            print(f"✅ Removed {removed_sheet_count} duplicates from Google Sheet.")
        else:
            print("No duplicates to remove from Google Sheet.")
            
        # Overwrite YT playlists
        for pid, tracks_to_remove in yt_removals.items():
            pl_title = next((title for title, id in playlist_map.items() if id == pid), pid)
            print(f"Removing {len(tracks_to_remove)} duplicate items from YT playlist '{pl_title}'...")
            try:
                # remove_playlist_items expects batching
                for i in range(0, len(tracks_to_remove), 50):
                    batch = tracks_to_remove[i:i+50]
                    yt.remove_playlist_items(pid, batch)
                print(f"✅ Successfully removed duplicates from YT playlist '{pl_title}'.")
            except Exception as e:
                print(f"❌ Error removing duplicates from YT playlist '{pl_title}': {e}")
    else:
        print("\n--- DRY RUN SUMMARY ---")
        print(f"Google Sheets: Would remove {removed_sheet_count} duplicate rows.")
        total_yt_removals = sum(len(v) for v in yt_removals.values())
        print(f"YouTube Music: Would remove {total_yt_removals} duplicate tracks across {len(yt_removals)} playlists.")
        print("Set dry_run=False to apply these changes.")

if __name__ == "__main__":
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == "--execute":
        dry_run = False
    run_dedup(dry_run=dry_run)
