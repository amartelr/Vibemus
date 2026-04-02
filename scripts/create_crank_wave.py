import sys
import os

# Base directory in path
sys.path.append(os.getcwd())

from src.core.manager import Manager
from src.services.yt_service import YTMusicService
from src.services.sheets_service import SheetsService
from src.services.lastfm_service import LastFMService
from src.services.musicbrainz_service import MusicBrainzService
from src.config import Config

def main():
    # Initialize services
    yt = YTMusicService()
    sheets = SheetsService()
    lastfm = LastFMService()
    mb = MusicBrainzService()
    
    manager = Manager(yt, sheets, lastfm, mb)
    
    print("\n📝 Updating Google Sheets records (Case-Insensitive Search)...")
    records = manager.sheets.get_songs_records()
    if not records:
        print("  ⚠ No songs found in 'Songs' sheet.")
        return

    updated_count = 0
    # Search for 'crank wave' anywhere in the genre field
    for r in records:
        genre = r.get('Genre', '')
        if not genre:
            continue
            
        if 'crank wave' in genre.lower():
            if r.get('Playlist') != 'Crank Wave':
                r['Playlist'] = 'Crank Wave'
                updated_count += 1
            
            # Bonus: ensure the Genre field itself is Title Cased
            # e.g. "Crank wave" -> "Crank Wave"
            import string
            parts = [string.capwords(p.strip().lower()) for p in genre.split(',')]
            normalized_genre = ", ".join(parts)
            if r['Genre'] != normalized_genre:
                r['Genre'] = normalized_genre
                # Note: if we only update the Genre field, it still counts as an update
                updated_count = updated_count if r.get('Playlist') == 'Crank Wave' else updated_count + 1

    if updated_count > 0:
        print(f"  ✓ Found and updated {updated_count} records.")
        print("  📝 Saving changes to spreadsheet...")
        manager.sheets.overwrite_songs(records)
        print(f"✅ Successfully updated {updated_count} tracks to playlist 'Crank Wave' in the spreadsheet.")
    else:
        print("  🔎 No tracks found with 'Crank wave' in the Genre field.")

    print("\n💡 Recommendation: Run 'vibemus sync genre' to update your summary, then 'vibemus playlist apply-moves' to carry out these changes on YouTube Music.")

if __name__ == "__main__":
    main()
