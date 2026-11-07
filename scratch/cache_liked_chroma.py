"""Descarga el preview de Deezer de las canciones Liked con acordes y guarda su cromagrama medio (12 valores) en
data/audio_chroma_cache.json, para poder evaluar la tonalidad por audio sin repetir descargas. Reanudable.
Uso: python scratch/cache_liked_chroma.py"""
import json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.services.sheet_gateway import SongSheet
from src.web.audio_key import _preview_chroma

PATH = "data/audio_chroma_cache.json"
cache = json.load(open(PATH)) if os.path.exists(PATH) else {}
lock = threading.Lock()
header, rows, cm = SongSheet().read()
cell = lambda r, k: r[cm[k]].strip() if cm.get(k, -1) != -1 and cm[k] < len(r) else ""
todo = []
for r in rows:
    if cell(r, "liked").upper() in ("TRUE", "1", "YES", "SÍ", "SI") and cell(r, "chord"):
        key = f"{cell(r, 'artist')}||{cell(r, 'title')}"
        if key not in cache:
            todo.append(key)
print(f"{len(todo)} canciones por descargar ({len(cache)} ya en caché)", flush=True)

def work(key):
    artist, title = key.split("||", 1)
    try:
        c = _preview_chroma(artist, title)
        entry = {"chroma": None if c is None else [float(x) for x in c], "error": None if c is not None else "sin preview"}
    except Exception as e:
        entry = {"chroma": None, "error": str(e)[:120]}
    with lock:
        cache[key] = entry
        if len(cache) % 10 == 0:
            json.dump(cache, open(PATH, "w"))
            print(f"  {len(cache)} en caché", flush=True)

with ThreadPoolExecutor(4) as ex:
    list(ex.map(work, todo))
json.dump(cache, open(PATH, "w"))
ok = sum(1 for v in cache.values() if v["chroma"])
print(f"Hecho: {ok} con audio, {len(cache) - ok} sin audio de {len(cache)}")
