import os
import sys
import json
from src.services.yt_service import YTMusicService
from src.services.sheets_service import SheetsService
from src.services.lastfm_service import LastFMService
from src.services.musicbrainz_service import MusicBrainzService
from src.core.manager import Manager

def main():
    yt = YTMusicService()
    sheets = SheetsService()
    lastfm = LastFMService()
    mb = MusicBrainzService()
    manager = Manager(yt, sheets, lastfm, mb)

    mapping = {
        "Indie Rock": "Rock",
        "Indie Pop": "Pop",
        "Indie Folk": "Folk",
        "Crank Wave": "Crank",
        "Garage Rock": "Garage",
        "Synthpop": "Pop"
    }

    print("🚀 Iniciando migración y fusión de playlists...")

    # 1. Actualizar Configuración (archiving.json)
    print("\n📁 Actualizando configuración local...")
    config_changed = False
    for old_name, new_name in mapping.items():
        if old_name in manager._archiving_config:
            print(f"   - Transfiriendo reglas: '{old_name}' -> '{new_name}'")
            if new_name in manager._archiving_config:
                # Merge logic for rules: we take the most expansive set
                # (Simple overwrite for now as they usually match)
                manager._archiving_config[new_name].extend(manager._archiving_config.pop(old_name))
            else:
                manager._archiving_config[new_name] = manager._archiving_config.pop(old_name)
            config_changed = True
    
    if config_changed:
        manager._save_archiving_config()
        print("   ✅ archiving.json actualizado.")

    # 2. Descargar catálogo para detectar fusiones
    print("\n📦 Analizando playlists en YouTube Music...")
    library_pls = yt.yt.get_library_playlists(limit=100)
    name_to_pid = {p['title']: p['playlistId'] for p in library_pls}

    # 3. YouTube Music Rename / Merge
    for old_name, new_name in mapping.items():
        print(f"   🔎 Procesando '{old_name}'...")
        try:
            # Buscar playlists que empiecen por old_name
            for title, pid in list(name_to_pid.items()):
                target_title = None
                if title == old_name:
                    target_title = new_name
                elif title.startswith(f"{old_name} (") and title.endswith(")"):
                    target_title = title.replace(old_name, new_name, 1)
                
                if target_title:
                    if target_title in name_to_pid and name_to_pid[target_title] != pid:
                        # MERGE
                        print(f"      🔄 FUSIONANDO: '{title}' en '{target_title}'...")
                        items = yt.get_playlist_items(pid, limit=1000)
                        vids = [it['videoId'] for it in items]
                        if vids:
                            yt.add_playlist_items(name_to_pid[target_title], vids)
                        yt.delete_playlist(pid)
                        # No removemos de name_to_pid para permitir múltiples merges si fuera necesario
                    else:
                        # RENAME
                        if title != target_title:
                           print(f"      ✏️  RENOMBRANDO: '{title}' -> '{target_title}'...")
                           yt.edit_playlist(pid, title=target_title)
                           name_to_pid[target_title] = pid
        except Exception as e:
            print(f"      ✗ Error al procesar '{old_name}': {e}")

    # 4. Actualizar Google Sheets
    print("\n📊 Actualizando base de datos en Google Sheets...")
    
    print("   📝 Procesando hoja 'Songs'...")
    all_songs = sheets.get_songs_records()
    songs_changed = 0
    for s in all_songs:
        p = s.get('Playlist', '')
        for old_n, new_n in mapping.items():
            if p == old_n:
                s['Playlist'] = new_n
                songs_changed += 1
            elif p.startswith(f"{old_n} (") and p.endswith(")"):
                s['Playlist'] = p.replace(old_n, new_n, 1)
                songs_changed += 1
    
    if songs_changed > 0:
        sheets.overwrite_songs(all_songs)
        print(f"      ✅ Se han actualizado {songs_changed} filas.")
    else:
        print("      ℹ️ No se encontraron cambios necesarios en 'Songs'.")

    print("   📝 Procesando hoja 'Artists'...")
    all_artists = sheets.get_artists()
    artists_changed = 0
    for a in all_artists:
        p = a.get('Playlist', '')
        for old_n, new_n in mapping.items():
            if p == old_n:
                a['Playlist'] = new_n
                artists_changed += 1
    
    if artists_changed > 0:
        sheets.save_artists(all_artists)
        print(f"      ✅ Se han actualizado {artists_changed} artistas.")
    else:
        print("      ℹ️ No se encontraron cambios necesarios en 'Artists'.")

    print("\n✨ Proceso completado con éxito.")

if __name__ == "__main__":
    main()
