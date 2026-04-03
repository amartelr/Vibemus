import os
import sys
import json
import gspread

# Añadir el directorio raíz al path para importar src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from src.core.manager import Manager
from src.services.yt_service import YTMusicService
from src.services.sheets_service import SheetsService
from src.services.lastfm_service import LastFMService
from src.services.musicbrainz_service import MusicBrainzService

def merge_years_from_copy():
    COPY_TITLE = "Copia de YouTube Music Vibemus - 3 de abril, 13:49"
    
    print(f"🚀 Iniciando restauración desde: '{COPY_TITLE}'")
    
    # 1. Inicializar servicios locales
    yt = YTMusicService()
    sheets = SheetsService()
    lastfm = LastFMService()
    musicbrainz = MusicBrainzService()
    manager = Manager(yt, sheets, lastfm, musicbrainz)
    
    # 2. Abrir la copia
    try:
        copy_ss = sheets.client.open(COPY_TITLE)
        copy_ws = copy_ss.worksheet("Songs")
        copy_records = copy_ws.get_all_records()
        print(f"✅ Copia abierta. Se han encontrado {len(copy_records)} canciones en la copia.")
    except Exception as e:
        print(f"❌ Error al abrir la copia: {e}")
        print("💡 Asegúrate de haber compartido el archivo con: vibemus-bot@mi-yt-music-app.iam.gserviceaccount.com")
        return

    # 3. Crear mapa de años (Video ID -> Year)
    # Usamos Video ID como clave principal por ser unívoco
    year_map = {}
    for r in copy_records:
        vid = r.get('Video ID')
        year = r.get('Year')
        if vid and year:
            year_map[vid] = year
            
    print(f"📊 Mapa de años creado con {len(year_map)} entradas.")

    # 4. Cargar canciones actuales
    current_songs = sheets.get_songs_records()
    restored_count = 0
    already_had_count = 0
    missing_count = 0
    
    for s in current_songs:
        vid = s.get('Video ID')
        if not str(s.get('Year', '')).strip():
            if vid in year_map:
                s['Year'] = year_map[vid]
                restored_count += 1
            else:
                missing_count += 1
        else:
            already_had_count += 1
            
    print(f"✨ Resultados:")
    print(f"   - Canciones que ya tenían año: {already_had_count}")
    print(f"   - Años restaurados desde la copia: {restored_count}")
    print(f"   - Canciones que siguen sin año: {missing_count}")

    # 5. Guardar cambios
    if restored_count > 0:
        print(f"💾 Guardando {len(current_songs)} canciones actualizadas en la hoja principal...")
        sheets.overwrite_songs(current_songs)
        print("🎉 ¡Restauración completada con éxito!")
    else:
        print("ℹ️ No se han encontrado nuevos años para restaurar.")

if __name__ == "__main__":
    merge_years_from_copy()
