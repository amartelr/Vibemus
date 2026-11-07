"""Calibra el umbral de "sin acorde" (N) de chords_in_frames con las Liked. Solo lectura.
Indicador indirecto (no hay acordes alineados en el tiempo con un preview de 30 s): una ventana es plausible si el acorde
que se le asigna (a nivel de tríada: raíz + mayor/menor) está entre los de la hoja de esa canción.
Necesita data/audio_windows_cache.json (scratch/cache_liked_windows.py). Uso: python scratch/eval_chord_threshold.py"""
import hashlib, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.services.sheet_gateway import SongSheet
from src.web.audio_key import _key_id, chord_templates
from src.web.harmony import NOTE_MAP, SEMITONES, clean_and_extract_chords, parse_chord_root_and_quality

cache = json.load(open("data/audio_windows_cache.json"))
header, rows, cm = SongSheet().read()
cell = lambda r, k: r[cm[k]].strip() if cm.get(k, -1) != -1 and cm[k] < len(r) else ""
samples = []   # (canción, mitad, similitud del mejor, margen sobre el segundo, energía relativa, ¿plausible?)
for r in rows:
    name = f"{cell(r, 'artist')}||{cell(r, 'title')}"
    wins, ton = cache.get(name), cell(r, "tonality")
    if not wins or not ton:
        continue
    sheet = set()
    for c in clean_and_extract_chords(cell(r, "chord")):
        root, q, _ = parse_chord_root_and_quality(c)
        if root in NOTE_MAP and q in ("major", "minor"):
            sheet.add((SEMITONES.index(NOTE_MAP[root]), q))
    templates = chord_templates(ton)     # [(raíz, calidad, vector)]
    wins = [np.array(w) for w in wins]
    mean_energy = np.mean([w.sum() for w in wins]) or 1.0
    half = int(hashlib.md5(name.encode()).hexdigest(), 16) % 2
    for w in wins:
        if w.sum() <= 0:
            samples.append((name, half, 0.0, 0.0, 0.0, False)); continue
        sims = sorted(((float(np.dot(v, w) / (np.linalg.norm(v) * np.linalg.norm(w))), root, q) for root, q, v in templates), reverse=True)
        samples.append((name, half, sims[0][0], sims[0][0] - sims[1][0], w.sum() / mean_energy, (sims[0][1], sims[0][2]) in sheet))
a = np.array([(s[1], s[2], s[3], s[4], s[5]) for s in samples], dtype=float)
print(f"{len(samples)} ventanas de {len({s[0] for s in samples})} canciones; plausibles sin filtro: {100*a[:,4].mean():.1f}%")
print("Similitud del mejor: percentiles 5/25/50/75/95 =", np.round(np.percentile(a[:, 1], [5, 25, 50, 75, 95]), 3))
print("Margen sobre el 2º:  percentiles 5/25/50/75/95 =", np.round(np.percentile(a[:, 2], [5, 25, 50, 75, 95]), 3))
for col, label in ((1, "similitud"), (2, "margen")):
    print(f"\nFiltrando por {label} (conserva las ventanas con valor >= umbral):")
    print("  umbral | conserva | plausibles entre las conservadas | plausibles entre las descartadas")
    for q in (0, 10, 20, 30, 40, 50):
        t = np.percentile(a[:, col], q); keep = a[:, col] >= t
        pk = 100 * a[keep, 4].mean(); pd = 100 * a[~keep, 4].mean() if (~keep).any() else float("nan")
        print(f"  {t:6.3f} | {100*keep.mean():5.1f}%   | {pk:5.1f}%                          | {pd:5.1f}%")
# ¿discrimina? AUC de cada señal para predecir "plausible"
def auc(x, y):
    pos, neg = x[y == 1], x[y == 0]
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())
for col, label in ((1, "similitud"), (2, "margen"), (3, "energía relativa")):
    print(f"AUC {label:17}: {auc(a[:, col], a[:, 4]):.3f}  (0.5 = no sirve)")

# ¿Generaliza el umbral? Mismo umbral medido por separado en las dos mitades de canciones
T = float(os.environ.get("NO_CHORD_T", "0.62"))
print(f"\nUmbral {T}: resultado por mitad de canciones")
for half in (0, 1):
    m = a[:, 0] == half; keep = m & (a[:, 1] >= T); drop = m & (a[:, 1] < T)
    print(f"  mitad {half}: ventanas {m.sum()}, plausibles sin filtro {100*a[m,4].mean():.1f}% | conserva {100*keep.sum()/m.sum():.1f}% "
          f"con {100*a[keep,4].mean():.1f}% plausibles | descarta {100*drop.sum()/m.sum():.1f}% con {100*a[drop,4].mean():.1f}%")
