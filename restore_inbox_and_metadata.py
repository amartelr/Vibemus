import os
import sys
import json

# Añadir src al path
sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from src.services.yt_service import YTMusicService
from src.services.sheets_service import SheetsService
from src.services.lastfm_service import LastFMService
from src.services.musicbrainz_service import MusicBrainzService
from src.core.manager import Manager

def main():
    print("🚀 Inicializando servicios de Vibemus...")
    try:
        yt = YTMusicService()
        sheets = SheetsService()
        lastfm = LastFMService()
        musicbrainz = MusicBrainzService()
        manager = Manager(yt, sheets, lastfm, musicbrainz)
    except Exception as e:
        print(f"❌ Error de inicialización: {e}")
        return

    print("📊 Leyendo registros actuales de Google Sheets...")
    all_songs = manager.sheets.get_songs_records()
    existing_vids = {s.get('Video ID') for s in all_songs if s.get('Video ID')}
    
    # 1. Recuperar la playlist # desde source_cache.json
    print("📂 Recuperando playlist '#' desde cache local...")
    recovered_inbox = []
    if os.path.exists("data/source_cache.json"):
        with open("data/source_cache.json", "r", encoding='utf-8') as f:
            source_cache = json.load(f)
            inbox_items = source_cache.get("#", [])
            
            for it in inbox_items:
                vid = it.get('videoId')
                if vid and vid not in existing_vids:
                    # Lo añadimos a la lista de recuperación
                    artist_str = ", ".join([a.get('name', '') for a in it.get('artists', [])])
                    recovered_inbox.append({
                        'Playlist': '#',
                        'Artist': artist_str,
                        'Title': it.get('title', ''),
                        'Album': (it.get('album') or {}).get('name', ''),
                        'Year': str(it.get('year', '')),
                        'Genre': '',
                        'Scrobble': 0,
                        'LastfmScrobble': 0,
                        'Video ID': vid
                    })
    
    print(f"✅ Se han encontrado {len(recovered_inbox)} canciones para restaurar en el Inbox (#).")
    
    # Unimos las canciones actuales con las recuperadas
    final_songs = all_songs + recovered_inbox

    # 2. Restaurar metadatos de Last.fm para TODAS las canciones
    print("🔍 Restaurando campos de Last.fm (Genre, Scrobbles) desde cache...")
    lastfm_cache = {}
    if os.path.exists("data/lastfm_cache.json"):
        with open("data/lastfm_cache.json", "r", encoding='utf-8') as f:
            lastfm_cache = json.load(f)
            
    restored_metadata = 0
    for s in final_songs:
        artist = str(s.get('Artist', '')).lower().strip()
        title = str(s.get('Title', '')).lower().strip()
        key = f"{artist}||{title}"
        
        if key in lastfm_cache:
            info = lastfm_cache[key]
            # Solo restauramos si el campo está vacío en el sheet
            if not s.get('Genre') and info.get('genre'):
                s['Genre'] = info['genre']
                restored_metadata += 1
            if not s.get('Scrobble') and info.get('scrobble'):
                s['Scrobble'] = info['scrobble']
            if not s.get('LastfmScrobble'):
                s['LastfmScrobble'] = info.get('lastfm_listeners', 0) or info.get('lastfm_scrobble', 0)

    print(f"✅ Metadatos restaurados para {restored_metadata} canciones.")

    # 3. Guardar cambios
    if len(final_songs) > 0:
        print(f"💾 Guardando {len(final_songs)} canciones en Google Sheets...")
        try:
            manager.sheets.overwrite_songs(final_songs)
            print("\033[1;92m✨ ¡Recuperación completada con éxito!\033[0m")
            print("El Inbox (#) ha vuelto y los campos de Last.fm se han rellenado.")
        except Exception as e:
            print(f"❌ Error al guardar en Sheets: {e}")
    else:
        print("ℹ No se encontró nada que recuperar o restaurar.")

if __name__ == "__main__":
    main()
