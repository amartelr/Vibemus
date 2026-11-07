"""Solo lectura: calcula tonalidad/progresión/complejidad/estilo de las canciones Liked con el código actual
y lo vuelca a JSON. Uso: python scratch/snapshot_liked.py <etiqueta>   (-> data/liked_<etiqueta>.json)
Compara con la tonalidad guardada en la hoja (revisada a mano en las Liked)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.services.sheet_gateway import SongSheet
from src.web.harmony import (clean_and_extract_chords, detect_key_from_chords, infer_complexity,
                             infer_emotional_style, infer_progression, NOTE_MAP, SEMITONES, parse_tonality)

def key_id(t):
    r, m = parse_tonality(t)
    return (SEMITONES.index(NOTE_MAP[r]), m) if r in NOTE_MAP else None

header, rows, cm = SongSheet().read()
cell = lambda row, k: row[cm[k]].strip() if cm.get(k, -1) != -1 and cm[k] < len(row) else ""
out = []
for row in rows:
    if cell(row, "liked").upper() not in ("TRUE", "1", "YES", "SÍ", "SI"):
        continue
    chord, stored = cell(row, "chord"), cell(row, "tonality")
    if not chord:
        continue
    chords = clean_and_extract_chords(chord)
    detected = detect_key_from_chords(chords)
    out.append({"artist": cell(row, "artist"), "title": cell(row, "title"), "stored_tonality": stored,
                "detected": detected, "match": bool(stored) and key_id(stored) == key_id(detected),
                "chords": chords, "progression": infer_progression(chord, stored or detected),
                "complex": infer_complexity(chord, stored or detected),
                "style": infer_emotional_style(chord, stored or detected)})
os.makedirs("data", exist_ok=True)
path = f"data/liked_{sys.argv[1]}.json"
json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
n = len(out); ok = sum(o["match"] for o in out)
print(f"{n} canciones Liked con acordes; tonalidad detectada = guardada en {ok} ({100*ok/max(n,1):.0f} %) -> {path}")
