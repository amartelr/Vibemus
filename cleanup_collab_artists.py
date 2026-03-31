import sys
import re
from src.config import Config
from src.services.yt_service import YTMusicService
from src.services.sheets_service import SheetsService
from src.services.lastfm_service import LastFMService
from src.core.manager import Manager

def main():
    Config.validate()
    print("Iniciando servicios...")
    yt = YTMusicService()
    sheets = SheetsService()
    manager = Manager(yt, sheets, LastFMService())

    print("Obteniendo artistas y canciones...")
    artists = sheets.get_artists()
    songs = sheets.get_songs_records()

    # Identificamos artistas que parecen colaboraciones
    collab_pattern = re.compile(r'\b(y|and|&|,)\b', re.IGNORECASE)
    
    collab_artists = []
    for a in artists:
        name = a.get("Artist Name", "")
        if collab_pattern.search(name) or "," in name:
            collab_artists.append(a)

    if not collab_artists:
        print("No se encontraron artistas que parezcan colaboraciones.")
        return

    print(f"\nSe han encontrado {len(collab_artists)} artistas que parecen colaboraciones.")

    artists_to_remove = []
    songs_to_archive = []

    # Map playlist names to their YT playlist IDs
    resolved_playlist_ids = {}
    print("\nResolviendo IDs de playlists...")
    for pl_name in Config.SOURCE_PLAYLISTS:
        if pl_name == '#':
            resolved_playlist_ids['#'] = Config.PLAYLIST_ID
            continue
        try:
            search_res = yt.yt.search(pl_name, filter='playlists', scope='library')
            for r in search_res:
                if r.get('title', '').lower().strip() == pl_name.lower().strip():
                    pid = r.get('playlistId') or r.get('browseId', '').replace('VL', '')
                    resolved_playlist_ids[pl_name] = pid
                    break
        except Exception as e:
            pass

    for a in collab_artists:
        artist_name = a.get("Artist Name", "")
        
        # Encontramos sus canciones
        artist_songs = [s for s in songs if s.get("Artist") == artist_name or artist_name in s.get("Artist", "").split(", ")]
        
        print(f"\n========================================")
        print(f"Artista: {artist_name}")
        if artist_songs:
            print(f"Canciones asociadas ({len(artist_songs)}):")
            for s in artist_songs:
                print(f"  - {s.get('Title')} (Playlist: {s.get('Playlist')})")
        else:
            print("No tiene canciones registradas en la hoja 'Songs'.")
        
        ans = input(f"¿Eliminar este artista y todas las canciones listadas arriba? [S/n]: ").strip().lower()
        if ans == 'n':
            continue

        artists_to_remove.append(artist_name)

        if artist_songs:
            for s in artist_songs:
                pl_name = s.get("Playlist", "")
                vid = s.get("Video ID")
                if pl_name and vid:
                    pid = resolved_playlist_ids.get(pl_name)
                    # We might need the setVideoId or full item to remove. If we just have videoId, 
                    # ytmusicapi remove_playlist_items expects a list of dicts with 'videoId' and 'setVideoId'.
                    # We can fetch the playlist items to find the setVideoId.
                    if pid:
                        try:
                            # It's an extra API call per playlist, but we can do it if needed. For Inbox '#', we can try.
                            # Getting setVideoId:
                            pl_items = yt.get_playlist_items_with_status(pid)
                            yt_items_to_remove = [item for item in pl_items if item.get('videoId') == vid]
                            if yt_items_to_remove:
                                yt.remove_playlist_items(pid, yt_items_to_remove)
                                print(f"    ✓ Eliminada de YouTube de la playlist '{pl_name}'")
                            else:
                                print(f"    ⚠ No se encontró en la playlist de YT.")
                        except Exception as e:
                            print(f"    ✗ Error al borrar de YT: {e}")
                
                songs_to_archive.append(s)

    # Actualizar Sheets
    if artists_to_remove:
        print("\nActualizando Google Sheets...")
        
        # 1. Eliminar artistas de "Artists"
        new_artists = [a for a in artists if a.get("Artist Name") not in artists_to_remove]
        sheets.save_artists(new_artists)
        print(f"✓ {len(artists_to_remove)} artistas eliminados de la pestaña 'Artists'.")

        # 2. Archivar canciones y eliminarlas de "Songs"
        if songs_to_archive:
            vids_to_archive = {s.get('Video ID') for s in songs_to_archive}
            new_songs = [s for s in songs if s.get('Video ID') not in vids_to_archive]
            sheets.overwrite_songs(new_songs)
            sheets.add_to_archived_batch(songs_to_archive)
            print(f"✓ {len(songs_to_archive)} canciones movidas a 'Archived'.")

    print("\nLimpieza interactiva completada.")

if __name__ == "__main__":
    main()
