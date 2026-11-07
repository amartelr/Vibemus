"""Evalúa la tonalidad (audio, acordes, método actual y fusión) contra la tonalidad guardada de las Liked (revisada a mano).
Necesita data/audio_chroma_cache.json (scratch/cache_liked_chroma.py). Solo lectura.
Las canciones se reparten en dos mitades por hash: los parámetros se ajustan en 'ajuste' y se miden en 'evaluación'.
Uso: python scratch/eval_key_fusion.py"""
import hashlib, itertools, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.services.sheet_gateway import SongSheet
from src.web import key_fusion
from src.web.audio_key import _key_id, chord_chroma, key_candidates
from src.web.harmony import (NOTE_MAP, SEMITONES, clean_and_extract_chords, detect_key_from_chords, key_scores_from_chords,
                             parse_tonality)

cache = json.load(open("data/audio_chroma_cache.json"))
header, rows, cm = SongSheet().read()
cell = lambda r, k: r[cm[k]].strip() if cm.get(k, -1) != -1 and cm[k] < len(r) else ""

def _chords_arbitrate(ranked, chord_text):
    """Método anterior de estimate_key: la tonalidad de los acordes pasa al primer puesto (línea base de la evaluación)."""
    chords = clean_and_extract_chords(chord_text or "")
    if not chords:
        return ranked
    chord_key = _key_id(detect_key_from_chords(chords))
    for i, cand in enumerate(ranked):
        if _key_id(cand["tonality"]) == chord_key:
            return [cand] + ranked[:i] + ranked[i + 1:]
    return ranked

def kid(t):
    root, mode = parse_tonality(t)
    return (SEMITONES.index(NOTE_MAP[root]), mode) if root in NOTE_MAP else None

songs = []
for r in rows:
    if cell(r, "liked").upper() not in ("TRUE", "1", "YES", "SÍ", "SI") or not cell(r, "chord"):
        continue
    name = f"{cell(r, 'artist')}||{cell(r, 'title')}"
    entry = cache.get(name)
    truth = kid(cell(r, "tonality")) if cell(r, "tonality") else None
    if not entry or not entry["chroma"] or truth is None:
        continue
    chroma, chord_text = np.array(entry["chroma"]), cell(r, "chord")
    chords = clean_and_extract_chords(chord_text)
    audio_only = key_candidates(chroma)
    audio_scores = {_key_id(c["tonality"]): c["audio"] for c in audio_only}
    chord_scores, _ = key_scores_from_chords(chords)
    current = _chords_arbitrate(key_candidates(chroma, chord_chroma(chord_text)), chord_text)
    songs.append({"name": name, "truth": truth, "audio": audio_scores, "chords": chord_scores or None,
                  "audio_rank": [_key_id(c["tonality"]) for c in audio_only],
                  "current_rank": [_key_id(c["tonality"]) for c in current],
                  "half": int(hashlib.md5(name.encode()).hexdigest(), 16) % 2})
print(f"{len(songs)} canciones Liked con audio, acordes y tonalidad guardada "
      f"(ajuste: {sum(s['half'] == 0 for s in songs)}, evaluación: {sum(s['half'] == 1 for s in songs)})\n")

def rank_chords(s): return sorted(s["chords"], key=lambda k: -s["chords"][k]) if s["chords"] else []
def rank_fused(s, **kw):
    f = key_fusion.fuse(s["audio"], s["chords"], **kw)
    return [r["key"] for r in f["keys"]]
def top(rank, truth, n): return truth in rank[:n]
def acc(group, fn, n=1): return 100 * sum(top(fn(s), s["truth"], n) for s in group) / max(len(group), 1)

groups = {"todas": songs, "ajuste": [s for s in songs if s["half"] == 0], "evaluación": [s for s in songs if s["half"] == 1]}
base = {"solo audio": lambda s: s["audio_rank"], "solo acordes": rank_chords, "actual (acordes mandan)": lambda s: s["current_rank"]}
print(f"{'método':34}" + "".join(f"{g:>22}" for g in groups))
for name, fn in base.items():
    print(f"{name:34}" + "".join(f"  top1 {acc(g, fn):5.1f}% top3 {acc(g, fn, 3):5.1f}%" for g in groups.values()))

grid = list(itertools.product([0.2, 0.3, 0.4, 0.5, 0.6, 0.7], [0.02, 0.04, 0.07, 0.12], [1.0, 2.0, 3.0, 5.0, 8.0]))
tune = groups["ajuste"]
scored = sorted(((acc(tune, lambda s, p=p: rank_fused(s, weight_audio=p[0], temp_audio=p[1], temp_chords=p[2])), p) for p in grid),
                key=lambda x: (-x[0], abs(x[1][0] - 0.5)))
best = scored[0][1]
kw = dict(weight_audio=best[0], temp_audio=best[1], temp_chords=best[2])
fn = lambda s: rank_fused(s, **kw)
print(f"{'fusión (ajustada)':34}" + "".join(f"  top1 {acc(g, fn):5.1f}% top3 {acc(g, fn, 3):5.1f}%" for g in groups.values()))
print(f"\nParámetros elegidos en 'ajuste': peso audio={best[0]}, T audio={best[1]}, T acordes={best[2]}")
print("Los 5 mejores del ajuste:", [(round(a, 1), p) for a, p in scored[:5]])
print("Con los parámetros por defecto del módulo:", f"{acc(groups['evaluación'], lambda s: rank_fused(s)):.1f}% en evaluación")

# Tipos de error de la fusión en 'evaluación'
def rel(a, b):
    (pa, ma), (pb, mb) = a, b
    if ma != mb: return "relativa" if (ma == "Major" and (pa - pb) % 12 == 3) or (ma == "Minor" and (pb - pa) % 12 == 3) else ("paralela" if pa == pb else "otra (distinto modo)")
    return "quinta/cuarta" if (pa - pb) % 12 in (5, 7) else "otra"
errs = {}
for s in groups["evaluación"]:
    r = rank_fused(s, **kw)
    if r[0] != s["truth"]: errs[rel(r[0], s["truth"])] = errs.get(rel(r[0], s["truth"]), 0) + 1
print("Errores de la fusión en evaluación por tipo:", errs)

# Calibración de la confianza en 'evaluación'
print("\nConfianza (probabilidad de la 1ª) frente a acierto, en evaluación:")
cal = [(key_fusion.fuse(s["audio"], s["chords"], **kw), s) for s in groups["evaluación"]]
cuts = [0, 0.4, 0.55, 0.7, 0.85, 1.01]
for lo, hi in zip(cuts, cuts[1:]):
    sel = [(f, s) for f, s in cal if lo <= f["keys"][0]["probability"] < hi]
    if sel: print(f"  {lo:.2f}-{min(hi,1):.2f}: {len(sel):3d} canciones, acierto {100*sum(f['keys'][0]['key']==s['truth'] for f,s in sel)/len(sel):5.1f}%")
agree = [(f, s) for f, s in cal if f["agree"]]; dis = [(f, s) for f, s in cal if f["agree"] is False]
print(f"  audio y acordes coinciden: {len(agree)} (acierto {100*sum(f['keys'][0]['key']==s['truth'] for f,s in agree)/max(len(agree),1):.1f}%) | discrepan: {len(dis)} (acierto {100*sum(f['keys'][0]['key']==s['truth'] for f,s in dis)/max(len(dis),1):.1f}%)")
json.dump({"weight_audio": best[0], "temp_audio": best[1], "temp_chords": best[2]}, open("data/key_fusion_params.json", "w"))
