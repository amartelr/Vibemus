
import sys
import os
from datetime import datetime

# Add the project root to sys.path
sys.path.append(os.getcwd())

from src.services.yt_service import YTMusicService
from src.services.sheets_service import SheetsService
from src.services.lastfm_service import LastFMService
from src.services.musicbrainz_service import MusicBrainzService
from src.core.manager import Manager

def cleanup_library():
    print("\n" + "━"*60)
    print("🧹 VIBEMUS LIBRARY CLEANUP (Source: Google Sheet 'Songs')")
    print("━"*60)

    # 1. Initialize services
    print("Initializing services...")
    yt = YTMusicService()
    sheets = SheetsService()
    lastfm = LastFMService()
    musicbrainz = MusicBrainzService()
    manager = Manager(yt, sheets, lastfm, musicbrainz)
    
    # 2. Get Authorized set from Google Sheet
    print("\n1. Scanning Google Sheet (Songs)...")
    all_songs_in_sheet = manager.sheets.get_songs_records()
    
    sheet_vids = set()
    for s in all_songs_in_sheet:
        vid = s.get('Video ID')
        pl = s.get('Playlist')
        if vid and pl != '#':
            sheet_vids.add(vid)
    
    print(f"   Collected {len(sheet_vids)} unique songs from the 'Songs' sheet (excluding '#').")

    # 3. Get total library scan
    print("\n2. Scanning YouTube Music Library (Songs section)...")
    library_songs = yt.get_library_songs(limit=None)
    print(f"   Found {len(library_songs)} songs in the Library.")

    # 4. Identify candidates for removal
    print("\n3. Identifying items to remove...")
    to_remove = []
    liked_to_keep = 0
    for s in library_songs:
        vid = s.get('videoId')
        if not vid: continue
        
        # Rule: Not in our Sheets AND not Liked
        in_sheet = vid in sheet_vids
        is_liked = s.get('likeStatus') == 'LIKE'
        
        if not in_sheet:
            if is_liked:
                liked_to_keep += 1
            else:
                to_remove.append(s)

    print(f"   Songs in Library NOT found in Sheet: {len(to_remove) + liked_to_keep}")
    print(f"   - To keep (Liked): {liked_to_keep}")
    print(f"   - To remove:      {len(to_remove)}")

    if not to_remove:
        print("\n✨ Library is already clean! No songs to remove.")
        return

    # 5. Show Preview (Top 20)
    print("\n4. Preview of removal list:")
    for s in to_remove[:20]:
        artist = s.get('artists', [{}])[0].get('name', 'Unknown')
        title = s.get('title', 'Unknown')
        print(f"   - {artist} - {title}")
    
    if len(to_remove) > 20:
        print(f"   ... and {len(to_remove) - 20} more.")

    # 6. Final Confirmation
    confirm = input(f"\n👉 Do you want to REMOVE {len(to_remove)} songs from your library? (s/n): ").strip().lower()
    if confirm not in ['s', 'si', 'y', 'yes', '']:
        print("🛑 Cleanup cancelled.")
        return

    # 7. Execute removal in batches
    print(f"\n5. Executing removal of {len(to_remove)} songs...")
    batch_size = 25
    
    for i in range(0, len(to_remove), batch_size):
        batch_items = to_remove[i:i+batch_size]
        batch_tokens = [it.get('feedbackTokens', {}).get('remove') for it in batch_items if it.get('feedbackTokens', {}).get('remove')]
        batch_vids = [it['videoId'] for it in batch_items if not it.get('feedbackTokens', {}).get('remove')]
        
        try:
            print(f"   Removing batch {i//batch_size + 1}/{(len(to_remove)-1)//batch_size + 1}...")
            if batch_tokens:
                yt.edit_song_library_status(feedback_tokens=batch_tokens)
            if batch_vids:
                yt.edit_song_library_status(video_ids=batch_vids)
        except Exception as e:
            print(f"   ❌ Error removing batch starting at {i}: {e}")

    print("\n" + "━"*60)
    print(f"✅ CLEANUP COMPLETED: {len(vids_to_remove)} songs removed.")
    print("━"*60 + "\n")

if __name__ == "__main__":
    cleanup_library()
