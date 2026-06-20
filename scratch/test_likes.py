"""
Investigación:
1. ¿Existe "Death Cab for Cutie - Riptides" en YouTube Music con otro ID?
2. ¿Cuántas canciones del Sheet tienen Video IDs que apuntan a contenido diferente?
"""
import sys, json, os, time
sys.path.insert(0, '.')
from src.services.yt_service import YTMusicService
from src.services.sheets_service import SheetsService

yt = YTMusicService()
sheets = SheetsService()

# --- PARTE 1: Buscar "Riptides" de Death Cab ---
print("=" * 60)
print("PARTE 1: Buscando 'Death Cab for Cutie - Riptides' en YouTube Music")
print("=" * 60)

results = yt.yt.search("Death Cab for Cutie Riptides", filter='songs')
for r in results[:5]:
    artists = ', '.join([a.get('name', '') for a in r.get('artists', [])])
    print(f"  🎵 {artists} - {r.get('title')} | videoId: {r.get('videoId')} | album: {r.get('album', {}).get('name', '')}")

# --- PARTE 2: Detectar IDs desactualizados ---
print("\n" + "=" * 60)
print("PARTE 2: Verificando Video IDs del Sheet contra YouTube")
print("=" * 60)

songs = sheets.get_songs_records()
# Solo verificar canciones en playlists activas (no archivadas, no #)
from src.config import Config
active_songs = [s for s in songs if s.get('Playlist') in Config.SOURCE_PLAYLISTS and s.get('Playlist') != '#' and s.get('Video ID')]

print(f"Total canciones activas a verificar: {len(active_songs)}")
print("Verificando en lotes (esto puede tardar unos minutos)...\n")

mismatches = []
errors = []
checked = 0

# Verificamos por lotes usando get_song (más fiable que buscar en playlists)
for song in active_songs:
    vid = song.get('Video ID')
    sheet_artist = song.get('Artist', '').strip().lower()
    sheet_title = song.get('Title', '').strip().lower()
    
    try:
        yt_song = yt.get_song(vid)
        vd = yt_song.get('videoDetails', {})
        yt_title = (vd.get('title') or '').strip().lower()
        yt_author = (vd.get('author') or '').strip().lower()
        
        # Comparación fuzzy: si ni el título ni el artista coinciden, es un mismatch
        title_match = sheet_title in yt_title or yt_title in sheet_title
        artist_match = sheet_artist in yt_author or yt_author in sheet_artist
        # También verificar artistas parciales (colaboraciones)
        if not artist_match:
            sheet_parts = [p.strip().lower() for p in sheet_artist.replace('&', ',').replace(' x ', ',').split(',')]
            artist_match = any(part in yt_author for part in sheet_parts if len(part) > 2)
        
        if not title_match and not artist_match:
            mismatches.append({
                'sheet_artist': song.get('Artist'),
                'sheet_title': song.get('Title'),
                'sheet_playlist': song.get('Playlist'),
                'yt_artist': vd.get('author'),
                'yt_title': vd.get('title'),
                'video_id': vid,
            })
    except Exception as e:
        err_str = str(e)
        if 'Video unavailable' in err_str or 'not available' in err_str.lower():
            errors.append({
                'sheet_artist': song.get('Artist'),
                'sheet_title': song.get('Title'),
                'sheet_playlist': song.get('Playlist'),
                'video_id': vid,
                'error': 'Video no disponible'
            })
        else:
            errors.append({
                'sheet_artist': song.get('Artist'),
                'sheet_title': song.get('Title'),
                'sheet_playlist': song.get('Playlist'),
                'video_id': vid,
                'error': str(e)[:80]
            })
    
    checked += 1
    if checked % 100 == 0:
        print(f"  ... verificadas {checked}/{len(active_songs)} ({len(mismatches)} mismatches, {len(errors)} errores)")
    
    time.sleep(0.15)  # Rate limiting

print(f"\n{'=' * 60}")
print(f"RESULTADOS: {checked} canciones verificadas")
print(f"{'=' * 60}")

if mismatches:
    print(f"\n🔴 MISMATCHES ({len(mismatches)}) — Video ID apunta a contenido diferente:")
    for m in mismatches:
        print(f"\n  [{m['sheet_playlist']}] Sheet: {m['sheet_artist']} - {m['sheet_title']}")
        print(f"  {'':>13} YT:    {m['yt_artist']} - {m['yt_title']}")
        print(f"  {'':>13} VID:   {m['video_id']}")
else:
    print("\n✅ No se encontraron mismatches de Video ID")

if errors:
    print(f"\n🟡 VIDEOS NO DISPONIBLES ({len(errors)}):")
    for e in errors:
        print(f"  [{e['sheet_playlist']}] {e['sheet_artist']} - {e['sheet_title']} ({e['video_id']}) — {e['error']}")
else:
    print("\n✅ Todos los videos están disponibles")
