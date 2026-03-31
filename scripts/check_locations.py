import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.services.sheets_service import SheetsService
s = SheetsService()
songs = s.get_songs_records()
archived = s.get_archived_records()

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
    "Cary Brothers - Ghost Town"
]

lost_keys = { (p.split(' - ')[0].strip().lower(), p.split(' - ')[1].strip().lower()) for p in LOST_SONGS if ' - ' in p }
in_songs = [r for r in songs if (str(r.get('Artist','')).strip().lower(), str(r.get('Title','')).strip().lower()) in lost_keys]
in_archived = [r for r in archived if (str(r.get('Artist','')).strip().lower(), str(r.get('Title','')).strip().lower()) in lost_keys]

print("--- SONGS ---")
for r in in_songs: print(f"{r.get('Artist')} - {r.get('Title')} -> {r.get('Playlist')}")
print("--- ARCHIVED ---")
for r in in_archived: print(f"{r.get('Artist')} - {r.get('Title')}")
