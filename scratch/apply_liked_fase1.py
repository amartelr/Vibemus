"""Actualiza Progression y Emotional (y Style si existe y reflejaba lo mismo) de las canciones Liked con la teoría de la Fase 1.
No toca Tonality (revisada a mano), Complex ni nada más. Simulación por defecto; --apply escribe.
Antes de escribir guarda copia en data/ y vuelve a leer la hoja comprobando artista/título de cada fila."""
import argparse, json, os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.services.sheet_gateway import SongSheet
from src.web.harmony import infer_emotional_style, infer_progression

LIKED = ("TRUE", "1", "YES", "SÍ", "SI")

def _old_harmony():
    """harmony.py de HEAD (anterior a la Fase 1): sus resultados son lo que la web generó automáticamente."""
    import importlib.util, subprocess, tempfile
    src = subprocess.run(["git", "show", "HEAD:src/web/harmony.py"], capture_output=True, text=True, check=True).stdout
    path = os.path.join(tempfile.mkdtemp(), "old_harmony.py")
    open(path, "w").write(src)
    spec = importlib.util.spec_from_file_location("old_harmony", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

OLD = _old_harmony()
MANUAL = []     # (fila, artista, título, columna) con un valor que la función antigua no habría generado

def in_scope(r, cell, scope):
    liked = cell(r, "liked").upper() in LIKED
    if scope == "liked":
        return liked
    if liked:
        return False
    return bool(cell(r, "lyrics")) == (scope == "rest-with-lyrics")   # rest-with-lyrics / rest-no-lyrics


def plan(rows, cm, scope):
    cell = lambda r, k: r[cm[k]].strip() if cm.get(k, -1) != -1 and cm[k] < len(r) else ""
    out = []
    for i, r in enumerate(rows):
        if not in_scope(r, cell, scope) or not cell(r, "chord") or not cell(r, "tonality"):
            continue
        chord, ton = cell(r, "chord"), cell(r, "tonality")
        new = {"progression": infer_progression(chord, ton), "emotional": infer_emotional_style(chord, ton)}
        if cm.get("style", -1) != cm.get("emotional", -2) and cell(r, "style") == cell(r, "emotional"):
            new["style"] = new["emotional"]       # la columna Style duplicaba a Emotional: se mantiene igual
        old_auto = {"progression": OLD.infer_progression(chord, ton), "emotional": OLD.infer_emotional_style(chord, ton)}
        diff = {}
        for k, v in new.items():
            cur = cell(r, k)
            if cm.get(k, -1) == -1 or cur == v:
                continue
            ref = old_auto["emotional" if k == "style" else k]
            if cur and cur != ref:          # valor editado a mano (o de otra fuente): no se pisa
                MANUAL.append((i + 2, cell(r, "artist"), cell(r, "title"), k)); continue
            diff[k] = (cur, v)
        if diff:
            out.append((i + 2, cell(r, "artist"), cell(r, "title"), diff))
    return out

ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
ap.add_argument("--scope", choices=["liked", "rest-with-lyrics", "rest-no-lyrics"], default="liked")
args = ap.parse_args()
sheet = SongSheet(); header, rows, cm = sheet.read()
changes = plan(rows, cm, args.scope)
cols = {k: header[cm[k]] for k in ("progression", "emotional", "style") if cm.get(k, -1) != -1}
print(f"Columnas: {cols} | canciones a cambiar (alcance: {args.scope}): {len(changes)}")
count = {}
for _, _, _, d in changes:
    for k in d: count[k] = count.get(k, 0) + 1
print("Celdas por columna:", count)
print(f"Omitidas por no ser salida automática (posible edición manual): {len(MANUAL)} celdas en {len({m[0] for m in MANUAL})} canciones")
if not args.apply:
    print("[SIMULACIÓN] No se ha escrito nada."); sys.exit()

backup = f"data/fase1_{args.scope}_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
os.makedirs("data", exist_ok=True)
json.dump([{"row": r, "artist": a, "title": t, "old": {k: o for k, (o, _) in d.items()}} for r, a, t, d in changes],
          open(backup, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("Copia de seguridad:", backup)
header2, rows2, cm2 = sheet.read()                 # relectura: las filas cambian de sitio si la CLI sincroniza
cell2 = lambda r, k: r[cm2[k]].strip() if cm2.get(k, -1) != -1 and cm2[k] < len(r) else ""
for row, artist, title, _ in changes:
    r = rows2[row - 2] if row - 2 < len(rows2) else []
    if cell2(r, "artist") != artist or cell2(r, "title") != title:
        sys.exit(f"Abortado: la fila {row} ya no es '{artist} - {title}'. No se ha escrito nada.")
cells = [(row, k, new) for row, _, _, d in changes for k, (_, new) in d.items()]
print(f"Escritas {sheet.write_cells(cells, cm2)} celdas en {len(changes)} canciones.")
