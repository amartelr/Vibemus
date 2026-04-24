
import sys
import os

# Añadir el directorio raíz al path
sys.path.append(os.getcwd())

from src.services.yt_service import YTMusicService
from src.config import Config

def clear_pendiente():
    yt_service = YTMusicService()
    yt = yt_service.yt
    
    # Buscar la playlist "Pendiente"
    playlists = yt.get_library_playlists(limit=None)
    target_pid = next((p['playlistId'] for p in playlists if p['title'] == 'Pendiente'), None)
    
    if not target_pid:
        print("❌ No se encontró la playlist 'Pendiente'.")
        return

    print(f"🧹 Obteniendo items de la playlist 'Pendiente' ({target_pid})...")
    playlist = yt.get_playlist(target_pid, limit=None)
    items = playlist.get('tracks', [])
    
    if not items:
        print("✨ La playlist ya está vacía.")
        return

    print(f"🗑️ Eliminando {len(items)} canciones de 'Pendiente'...")
    # remove_playlist_items espera una lista de diccionarios con setVideoId y videoId
    # El método get_playlist ya devuelve los objetos con estos campos
    for i in range(0, len(items), 50):
        batch = items[i:i+50]
        try:
            yt.remove_playlist_items(target_pid, batch)
        except Exception as e:
            print(f"  ⚠ Error en batch: {e}")
    
    print("✅ Proceso de limpieza finalizado.")

if __name__ == "__main__":
    clear_pendiente()
