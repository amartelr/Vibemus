"""Guarda el chroma medio de cada ventana de 2 s del preview de las Liked (para calibrar el reconocimiento de acordes).
-> data/audio_windows_cache.json {"artista||título": [[12 valores], ...]}. Reanudable. Uso: python scratch/cache_liked_windows.py"""
import json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.services.sheet_gateway import SongSheet
from src.web.audio_key import _preview_frames, chroma_windows

PATH = "data/audio_windows_cache.json"
cache = json.load(open(PATH)) if os.path.exists(PATH) else {}
lock = threading.Lock()
header, rows, cm = SongSheet().read()
cell = lambda r, k: r[cm[k]].strip() if cm.get(k, -1) != -1 and cm[k] < len(r) else ""
todo = [f"{cell(r, 'artist')}||{cell(r, 'title')}" for r in rows
        if cell(r, "liked").upper() in ("TRUE", "1", "YES", "SÍ", "SI") and cell(r, "chord")
        and f"{cell(r, 'artist')}||{cell(r, 'title')}" not in cache]
print(f"{len(todo)} por descargar ({len(cache)} en caché)", flush=True)

def work(key):
    artist, title = key.split("||", 1)
    try:
        frames = _preview_frames(artist, title)
        value = None if frames is None else [[float(x) for x in w] for w in chroma_windows(frames)]
    except Exception:
        value = None
    with lock:
        cache[key] = value
        if len(cache) % 10 == 0:
            json.dump(cache, open(PATH, "w")); print(f"  {len(cache)}", flush=True)

with ThreadPoolExecutor(4) as ex:
    list(ex.map(work, todo))
json.dump(cache, open(PATH, "w"))
print(f"Hecho: {sum(1 for v in cache.values() if v)} con audio de {len(cache)}")
