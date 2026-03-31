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
    
    # Target keys
    lost_keys = { (p.split(' - ')[0].strip().lower(), p.split(' - ')[1].strip().lower()) for p in LOST_SONGS if ' - ' in p }
    
    # 1. Gather all songs and archived
    songs = sheets.get_songs_records()
    archived = sheets.get_archived_records()
    
    # Make sure we don't have them in songs
    songs_vids = {s.get('Video ID') for s in songs if s.get('Video ID')}
    
    to_recover = {}
    new_archived = []
    
    for r in archived:
        key = (str(r.get('Artist','')).strip().lower(), str(r.get('Title','')).strip().lower())
        vid = r.get('Video ID')
        if key in lost_keys:
            if vid not in songs_vids:
                # Store the record for recovery. If we have duplicates in Archived, we only keep one.
                to_recover[vid] = r
        else:
            new_archived.append(r)
            
    if not to_recover:
        print("No se encontraron canciones para recuperar (ya están en Songs o no en Archived).")
        return
        
    print(f"Recuperando {len(to_recover)} canciones únicas del archivo...")
    
    # Format them for Songs sheet
    for vid, r in to_recover.items():
        r['Playlist'] = 'Indie Folk $'
        songs.append(r)
        
    # Check YouTube
    library_playlists = yt.yt.get_library_playlists(limit=100)
    archive_pid = None
    for lp in library_playlists:
        if lp.get('title', '').lower() == 'indie folk $':
            archive_pid = lp.get('playlistId')
            break
            
    if archive_pid:
        print(f"Comprobando playlist YT: {archive_pid}")
        yt_tracks = yt.get_playlist_items(archive_pid, limit=5000)
        yt_vids = {t.get('videoId') for t in yt_tracks if t.get('videoId')}
        
        vids_to_add = [vid for vid in to_recover.keys() if vid not in yt_vids]
        if vids_to_add:
            print(f"Añadiendo {len(vids_to_add)} canciones que faltan a YT...")
            try:
                yt.add_playlist_items(archive_pid, vids_to_add)
                print("Añadidas a YT OK.")
            except Exception as e:
                print(f"Aviso: error añadiendo a YT: {e}")
        else:
            print("Las canciones ya están en la playlist de YT.")
            
    # Finally: VERY CAREFULLY overwrite Sheets
    print(f"Grabando {len(songs)} registros en Songs...")
    sheets.overwrite_songs(songs)
    print("Grabadas en Songs OK.")
    
    # Deduplicate new_archived just logically
    unique_new_archived = []
    seen_vids = set()
    for r in new_archived:
        vid = r.get('Video ID')
        if not vid or vid not in seen_vids:
            unique_new_archived.append(r)
            if vid: seen_vids.add(vid)
            
    print(f"Grabando {len(unique_new_archived)} registros en Archived...")
    sheets.overwrite_archived(unique_new_archived)
    print("Grabadas en Archived OK.")
    
    print("\\n✅ ¡Proceso finalizado correctamente! Listas sincronizadas.")

if __name__ == "__main__":
    main()
