import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.services.sheets_service import SheetsService
s = SheetsService()
songs = s.get_songs_records()
archived = s.get_archived_records()
print(f"Total in Songs: {len(songs)}")
print(f"Total in Archived: {len(archived)}")

# Check where the 16 songs are:
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
lost_keys = { (p.split(' - ')[0].strip().lower(), p.split(' - ')[1].strip().lower()) for p in LOST_SONGS if ' - ' in p }

in_songs = 0
for r in songs:
    if (r.get('Artist','').strip().lower(), r.get('Title','').strip().lower()) in lost_keys:
        in_songs += 1
        print(f"In Songs: {r.get('Artist')} - {r.get('Title')} -> {r.get('Playlist')}")

in_archived = 0
for r in archived:
    if (r.get('Artist','').strip().lower(), r.get('Title','').strip().lower()) in lost_keys:
        in_archived += 1

print(f"\nTarget songs in Songs: {in_songs}")
print(f"Target songs in Archived: {in_archived}")
