#!/usr/bin/env python3
"""
migrate_archives_to_1900.py
----------------------------
Renombra las playlists de archivo cuyo intervalo más antiguo no empieza
en 1900, tanto en YouTube Music como en el Google Sheet (Songs).

Ejecución:
    cd /Users/alfredomartel/dev/antigravity/workspaces/Vibemus
    python scripts/migrate_archives_to_1900.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.manager import Manager

# Mapa de renombres: old_name -> new_name
RENAMES = {
    "Crank (2012-2021)":     "Crank (1900-2021)",
    "Emo (2006-2022)":       "Emo (1900-2022)",
    "Español (1994-2021)":   "Español (1900-2021)",
    "Folk (2001-2014)":      "Folk (1900-2014)",
    "Pop (1994-2018)":       "Pop (1900-2018)",
    "Post-punk (1979-2021)": "Post-punk (1900-2021)",
    "Rock (1993-2014)":      "Rock (1900-2014)",
}


def main():
    print("\n" + "━"*60)
    print("🔄 MIGRACIÓN DE PLAYLISTS DE ARCHIVO → inicio 1900")
    print("━"*60)

    from src.services.yt_service import YTMusicService
    from src.services.sheets_service import SheetsService
    from src.services.lastfm_service import LastFMService
    from src.services.musicbrainz_service import MusicBrainzService

    yt = YTMusicService()
    sheets = SheetsService()
    lastfm = LastFMService()
    musicbrainz = MusicBrainzService()
    manager = Manager(yt, sheets, lastfm, musicbrainz)

    errors = 0
    success = 0

    for old_name, new_name in RENAMES.items():
        print(f"\n  📂 {old_name}  →  {new_name}")

        # 1. Buscar el ID de la playlist en YouTube Music
        pid = manager._resolve_playlist_id(old_name)
        if not pid:
            print(f"    ⚠  No encontrada en YouTube Music — puede que ya esté renombrada o no exista.")
            # Intentar de todos modos actualizar el Sheet si la nueva ya existe
        else:
            # 2. Renombrar en YouTube Music
            try:
                manager.yt.edit_playlist(pid, title=new_name)
                print(f"    ✅ YouTube Music: renombrada correctamente.")
                success += 1
            except Exception as e:
                print(f"    ✗  Error al renombrar en YouTube Music: {e}")
                errors += 1
                continue  # No actualizamos el Sheet si YTM falló

        # 3. Actualizar el Google Sheet (columna 'Playlist' de las canciones)
        all_songs = manager.sheets.get_songs_records()
        updated = 0
        for s in all_songs:
            if s.get('Playlist') == old_name:
                s['Playlist'] = new_name
                updated += 1

        if updated:
            manager.sheets.overwrite_songs(all_songs)
            print(f"    ✅ Google Sheet: {updated} canciones actualizadas de '{old_name}' → '{new_name}'.")
        else:
            print(f"    ℹ  Google Sheet: ninguna canción con playlist '{old_name}'.")

    print("\n" + "━"*60)
    print(f"✅ Completado: {success} renombradas, {errors} errores.")
    print("━"*60 + "\n")


if __name__ == "__main__":
    main()
