import sys
import os
sys.path.append(os.getcwd())
from src.services.sheets_service import SheetsService

def cleanup():
    sheets = SheetsService()
    artists = sheets.get_artists()
    
    to_clean = [
        'Canserbero & Afromak', 
        'Dean Blunt & Panda Bear, Dean Blunt, & Panda Bear', 
        'Ghouljaboy & Depresión Sonora', 
        'Skinshape & Aaron Taylor', 
        'Winter & Tanukichan'
    ]
    
    cleaned = []
    # Use normalized names for lookup
    seen_names = {a.get('Artist Name', '').strip().lower() for a in artists if a.get('Artist Name')}
    
    for a in artists:
        name = a.get('Artist Name', '').strip()
        if name in to_clean:
            # Get the first artist
            first_artist = name.replace(',', '&').split('&')[0].strip()
            print(f"Processing '{name}' -> '{first_artist}'")
            
            if first_artist.lower() not in seen_names:
                # Rename the existing row and clear ID so it gets re-searched if needed
                a['Artist Name'] = first_artist
                a['Artist ID'] = ''
                cleaned.append(a)
                seen_names.add(first_artist.lower())
                print(f"  Renamed to '{first_artist}'")
            else:
                # Already exists, just drop this row
                print(f"  '{first_artist}' already tracked, removing compound entry.")
        else:
            cleaned.append(a)
            
    sheets.save_artists(cleaned)
    print("✅ Artist list cleanup complete.")

if __name__ == '__main__':
    cleanup()
