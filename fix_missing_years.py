import os
import sys
import json
import time

# Añadir el directorio raíz al path para importar src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from src.services.yt_service import YTMusicService
from src.services.sheets_service import SheetsService
from src.services.lastfm_service import LastFMService
from src.services.musicbrainz_service import MusicBrainzService
from src.core.manager import Manager

def fix_missing_years():
    print("🚀 Inicializando servicios de Vibemus para recuperar años perdidos...")
    yt = YTMusicService()
    sheets = SheetsService()
    lastfm = LastFMService()
    musicbrainz = MusicBrainzService()
    manager = Manager(yt, sheets, lastfm, musicbrainz)
    
    print("📊 Leyendo canciones actuales de Google Sheets...")
    all_songs = manager.sheets.get_songs_records()
    
    songs_needing_year = [s for s in all_songs if not str(s.get('Year', '')).strip()]
    total = len(songs_needing_year)
    
    if total == 0:
        print("✅ No se han encontrado canciones con el año faltante.")
        return

    print(f"🔍 Se han encontrado {total} canciones sin año. Iniciando recuperación...")
    print("⚠️  Este proceso puede ser lento ya que consulta la API de YouTube Music por cada canción.")

    count = 0
    start_time = time.time()
    
    try:
        for s in songs_needing_year:
            vid = s.get('Video ID')
            title = s.get('Title')
            artist = s.get('Artist')
            
            if not vid or not title or not artist:
                continue
                
            count += 1
            # Mostrar progreso cada 5 canciones
            if count % 5 == 1 or count == total:
                elapsed = time.time() - start_time
                avg_time = elapsed / count if count > 0 else 0
                remaining = (total - count) * avg_time
                print(f"[{count}/{total}] Recuperando: {artist} - {title} ... (Aprox: {remaining/60:.1f} min restantes)")
            
            year = manager._fetch_song_year(vid, title, artist)
            if year:
                s['Year'] = year
                # print(f"   ✅ Encontrado: {year}")
            
            # Guardar cada 50 canciones para no perder progreso
            if count % 50 == 0:
                print(f"💾 Guardando progreso parcial ({count} canciones)...")
                manager.sheets.overwrite_songs(all_songs)
                
        print(f"\n✅ Recuperación completada. Se han procesado {count} canciones.")
        print("💾 Guardando resultados finales en Google Sheets...")
        manager.sheets.overwrite_songs(all_songs)
        print("✨ ¡Listo! Los años han sido restaurados.")
        
    except KeyboardInterrupt:
        print("\n🛑 Proceso interrumpido por el usuario. Guardando lo recuperado hasta ahora...")
        manager.sheets.overwrite_songs(all_songs)
        print("💾 Progreso guardado.")
    except Exception as e:
        print(f"\n❌ Error durante la recuperación: {e}")
        import traceback
        traceback.print_exc()
        print("💾 Intentando guardar el progreso actual...")
        manager.sheets.overwrite_songs(all_songs)

if __name__ == "__main__":
    fix_missing_years()
