import os
import sys
import json
from datetime import datetime

# Añadir src al path para poder importar los módulos del proyecto
sys.path.append(os.path.join(os.getcwd(), "src"))

try:
    from core.manager import Manager
    from config import Config
except ImportError as e:
    print(f"Error importando módulos: {e}")
    sys.exit(1)

def main():
    # Inicializamos el Manager (esto carga automáticamente Config, YouTube, Sheets y Last.fm)
    manager = Manager()
    
    print("\033[1;94m📊 Cargando registros de la Google Sheet...\033[0m")
    all_songs = manager.sheets.get_songs_records()
    
    # Filtramos las canciones de la lista 'Pop' que es donde ocurrió el problema
    pop_songs = [s for s in all_songs if s.get('Playlist') == 'Pop']
    print(f"🔎 Se han encontrado {len(pop_songs)} canciones en la playlist 'Pop'.")
    
    if not pop_songs:
        print("⚠ No se encontraron canciones en 'Pop'. Abortando.")
        return

    # Cargamos cache de Last.fm para recuperar Géneros y Scrobbles
    lastfm_cache = {}
    if os.path.exists("data/lastfm_cache.json"):
        with open("data/lastfm_cache.json", "r", encoding='utf-8') as f:
            lastfm_cache = json.load(f)
            print("✅ Cache de Last.fm cargada.")

    modified_count = 0
    fixed_years = 0
    fixed_genres = 0
    
    print("\033[1;93m🛠  Iniciando proceso de restauración...\033[0m")
    
    for i, s in enumerate(pop_songs, 1):
        vid = s.get('Video ID')
        artist = s.get('Artist', '')
        title = s.get('Title', '')
        
        # Identificamos si le faltan datos críticos
        needs_year = not str(s.get('Year', '')).strip()
        needs_genre = not str(s.get('Genre', '')).strip()
        needs_scrobbles = not s.get('Scrobble') or not s.get('LastfmScrobble')
        
        if needs_year or needs_genre or needs_scrobbles:
            # 1. Recuperar de Last.fm Cache (Genre, Scrobble)
            cache_key = f"{str(artist).lower().strip()}||{str(title).lower().strip()}"
            if cache_key in lastfm_cache:
                info = lastfm_cache[cache_key]
                if needs_genre and info.get('genre'):
                    s['Genre'] = info['genre']
                    fixed_genres += 1
                if needs_scrobbles:
                    s['Scrobble'] = info.get('scrobble', 0)
                    s['LastfmScrobble'] = info.get('lastfm_listeners', 0) or info.get('lastfm_scrobble', 0)
            
            # 2. Recuperar Año (Year)
            # Primero intentamos usar la lógica interna del Manager que consulta YT Music adecuadamente
            if needs_year:
                # Opción: Si el Year está en la cache de origen, lo tomamos de ahí (más rápido)
                # Pero si no, usamos el método _fetch_song_year del manager
                print(f"  [{i}/{len(pop_songs)}] 🌐 Buscando año para: {artist} - {title}...", end='\r')
                year = manager._fetch_song_year(vid, title, artist)
                if year:
                    s['Year'] = year
                    fixed_years += 1
            
            modified_count += 1
            if i % 10 == 0:
                print(f"  Progress: {i}/{len(pop_songs)} songs checked. Fixed: {modified_count}")

    print(f"\n\n\033[1;92m✅ Restauración local completada.\033[0m")
    print(f"   - Canciones analizadas: {len(pop_songs)}")
    print(f"   - Canciones con datos recuperados: {modified_count}")
    print(f"   - Años recuperados: {fixed_years}")
    print(f"   - Géneros recuperados: {fixed_genres}")

    if modified_count > 0:
        confirm = input("\n¿Deseas guardar los cambios en la Google Sheet? (y/n): ").lower()
        if confirm == 'y':
            print("💾 Guardando todos los registros en Google Sheets... (esto puede tardar un momento)")
            try:
                manager.sheets.save_songs(all_songs)
                print("\033[1;92m✨ ¡Google Sheet actualizada con éxito!\033[0m")
                print("\nPróximo paso sugerido: ejecuta 'vibemus playlist split --name Pop' de nuevo.")
            except Exception as e:
                print(f"\033[1;91m❌ Error guardando en la Sheet: {e}\033[0m")
        else:
            print("🚫 Operación cancelada. No se han guardado cambios.")
    else:
        print("ℹ No se encontró información faltante que pudiera ser recuperada.")

if __name__ == "__main__":
    main()
