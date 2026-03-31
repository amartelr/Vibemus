"""
Cleans up duplicates and synchronizes `recover_songs` changes.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.sheets_service import SheetsService

LOST_SONGS = [
    "Fenne Lily - Car Park",
    "Hollow Coves - These Memories",
    "Fionn Regan - Hunters Map",
    "Owen - Bags of Bones",
    "José González - Down the Line",
    "Hollow Coves - Hello",
    "Fionn Regan - The Underwood Typewriter",
    "George Ogilvie - Better Man",
    "Hollow Coves - The Woods",
    "Hollow Coves - Lonely Nights (feat. Priscilla Ahn)",
    "Houndmouth - Miracle Mile",
    "Daughter - Medicine",
    "Fenne Lily - Three Oh Nine",
    "Hollow Coves - Coastline",
    "Cary Brothers - Ghost Town",
]

def main():
    sheets = SheetsService()
    
    # Target video IDs for our 15 songs:
    lost_keys = set()
    for entry in LOST_SONGS:
        parts = entry.split(" - ", 1)
        if len(parts) == 2:
            lost_keys.add((parts[0].strip().lower(), parts[1].strip().lower()))

    # Build unique songs
    songs = sheets.get_songs_records()
    unique_songs = {}
    for r in songs:
        vid = r.get('Video ID')
        if not vid: continue
        unique_songs[vid] = r
    
    sheets.overwrite_songs(list(unique_songs.values()))
    print(f"Removed {(len(songs) - len(unique_songs))} duplicate lines from Songs.")

    # Remove from Archived sheet
    archived = sheets.get_archived_records()
    new_archived = []
    removed_vids = set()
    for r in archived:
        vid = r.get('Video ID')
        key = (r.get('Artist', '').strip().lower(), r.get('Title', '').strip().lower())
        if key in lost_keys:
            removed_vids.add(vid)
        else:
            new_archived.append(r)
    
    # Further deduplicate new_archived just in case
    unique_archived = {}
    for r in new_archived:
        vid = r.get('Video ID')
        if vid:
            unique_archived[vid] = r
            
    sheets.overwrite_archived(list(unique_archived.values()))
    print(f"Removed {(len(archived) - len(unique_archived))} lines from Archived.")
    print("Done cleaning sheets.")

if __name__ == "__main__":
    main()
