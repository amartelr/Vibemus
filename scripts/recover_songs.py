"""
Recover the 16 songs that were incorrectly archived from 'Indie Folk $'.
1. Find them in the Archived sheet
2. Move them back to Songs with playlist 'Indie Folk $'
3. Add them back to the YouTube 'Indie Folk $' playlist
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.sheets_service import SheetsService
from src.services.yt_service import YTMusicService

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
    yt = YTMusicService()
    
    # Build lookup set
    lost_keys = set()
    for entry in LOST_SONGS:
        parts = entry.split(" - ", 1)
        if len(parts) == 2:
            lost_keys.add((parts[0].strip().lower(), parts[1].strip().lower()))
    
    # 1. Find them in Archived
    archived = sheets.get_archived_records()
    to_recover = []
    for r in archived:
        key = (r.get('Artist', '').strip().lower(), r.get('Title', '').strip().lower())
        if key in lost_keys:
            to_recover.append(r)
    
    print(f"\n🔍 Found {len(to_recover)} of {len(LOST_SONGS)} songs in Archived sheet:\n")
    for r in to_recover:
        print(f"  ✓ {r.get('Artist')} - {r.get('Title')} (VID: {r.get('Video ID')}, Year: {r.get('Year')})")
    
    if len(to_recover) != len(LOST_SONGS):
        missing = lost_keys - {(r.get('Artist','').strip().lower(), r.get('Title','').strip().lower()) for r in to_recover}
        print(f"\n  ⚠ No encontradas en Archived: {missing}")
    
    if not to_recover:
        print("No hay nada que recuperar.")
        return
    
    # 2. Get YouTube Indie Folk $ playlist ID
    library_playlists = yt.yt.get_library_playlists(limit=100)
    archive_pid = None
    for lp in library_playlists:
        if lp.get('title', '').lower() == 'indie folk $':
            archive_pid = lp.get('playlistId')
            break
    
    if not archive_pid:
        print("\n✗ No se encontró la playlist 'Indie Folk $' en YouTube Music")
        return
    
    print(f"\n📋 Playlist 'Indie Folk $' encontrada: {archive_pid}")
    
    # 3. Check which video IDs are already in the YT playlist
    yt_tracks = yt.get_playlist_items(archive_pid, limit=5000)
    yt_vids = {t.get('videoId') for t in yt_tracks if t.get('videoId')}
    
    vids_to_add = []
    for r in to_recover:
        vid = r.get('Video ID')
        if vid and vid not in yt_vids:
            vids_to_add.append(vid)
            print(f"  ➕ Falta en YT: {r.get('Artist')} - {r.get('Title')} ({vid})")
        elif vid and vid in yt_vids:
            print(f"  ✓ Ya en YT: {r.get('Artist')} - {r.get('Title')}")
    
    # 4. Add missing songs back to YouTube playlist
    if vids_to_add:
        print(f"\n  Añadiendo {len(vids_to_add)} canciones a 'Indie Folk $' en YouTube...")
        try:
            yt.add_playlist_items(archive_pid, vids_to_add)
            print(f"  ✓ Añadidas correctamente.")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return
    
    # 5. Remove from Archived and add back to Songs
    recover_vids = {r.get('Video ID') for r in to_recover}
    new_archived = [r for r in archived if r.get('Video ID') not in recover_vids]
    
    # Set playlist to Indie Folk $
    for r in to_recover:
        r['Playlist'] = 'Indie Folk $'
    
    # Read current songs and add recovered ones
    songs = sheets.get_songs_records()
    songs.extend(to_recover)
    
    print(f"\n  📝 Actualizando Songs sheet (+{len(to_recover)} recuperadas)...")
    sheets.overwrite_songs(songs)
    
    print(f"  📝 Actualizando Archived sheet (-{len(to_recover)} devueltas)...")
    sheets.overwrite_archived(new_archived)
    
    print(f"\n✅ {len(to_recover)} canciones recuperadas a 'Indie Folk $'.")

if __name__ == "__main__":
    main()
