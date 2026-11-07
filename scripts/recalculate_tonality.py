#!/usr/bin/env python3
"""
recalculate_tonality.py
Recalcula Tonalidad, Progresión, Complejidad y Estilo de las canciones de la hoja 'Songs' a partir de sus acordes,
con el mismo cálculo que /api/analyze-chords. Solo toca canciones que NO están marcadas como favoritas (Liked):
esas tonalidades se revisaron a mano.

Modos de uso:
  python3 scripts/recalculate_tonality.py            # simulación (por defecto): muestra los cambios, no escribe
  python3 scripts/recalculate_tonality.py --apply    # escribe en Google Sheets, solo las celdas que cambian
  python3 scripts/recalculate_tonality.py --artist "Freedom Fry"   # filtra por artista
  python3 scripts/recalculate_tonality.py --with-lyrics            # solo canciones con letra

Compara la tonalidad por nota y modo, así que 'D# Minor' y 'Eb Minor' no cuentan como cambio.
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.sheet_gateway import SongSheet, col_idx_to_letter  # noqa: E402
from src.web.harmony import (NOTE_MAP, SEMITONES, clean_and_extract_chords, detect_key_from_chords,  # noqa: E402
                             infer_complexity, infer_emotional_style, infer_progression, parse_tonality)

RECALC_KEYS = ("tonality", "progression", "complex", "style")


def _key_id(tonality):
    """(pitch class, mode) of a tonality string, so that enharmonic spellings compare equal."""
    try:
        root, mode = parse_tonality(tonality)
    except Exception:
        return None
    if root not in NOTE_MAP:
        return None
    return SEMITONES.index(NOTE_MAP[root]), mode


def _is_liked(row, col_map):
    idx = col_map.get("liked", -1)
    return idx != -1 and idx < len(row) and row[idx].strip().upper() in ("TRUE", "1", "YES", "SÍ", "SI")


def plan_changes(header, rows, col_map, artist_filter=None, with_lyrics=False):
    """[(row_number, artist, title, {key: (old, new)})] for every non-favourite song whose key changes."""
    cell = lambda row, key: row[col_map[key]].strip() if col_map.get(key, -1) != -1 and col_map[key] < len(row) else ""
    changes, skipped_liked, no_chords = [], 0, 0
    for i, row in enumerate(rows):
        artist, title = cell(row, "artist"), cell(row, "title")
        if artist_filter and artist_filter.lower() not in artist.lower():
            continue
        if _is_liked(row, col_map):
            skipped_liked += 1
            continue
        if with_lyrics and not cell(row, "lyrics"):
            continue
        chord = cell(row, "chord")
        if not chord:
            no_chords += 1
            continue
        old_tonality = cell(row, "tonality")
        new_tonality = detect_key_from_chords(clean_and_extract_chords(chord))
        if _key_id(old_tonality) == _key_id(new_tonality):
            continue  # same key: leave progression, complexity and style alone as well
        new_values = {
            "tonality": new_tonality,
            "progression": infer_progression(chord, new_tonality),
            "complex": infer_complexity(chord, new_tonality),
            "style": infer_emotional_style(chord, new_tonality),
        }
        diff = {k: (cell(row, k), new_values[k]) for k in RECALC_KEYS
                if col_map.get(k, -1) != -1 and cell(row, k) != new_values[k]}
        changes.append((i + 2, artist, title, diff))
    return changes, skipped_liked, no_chords


def main():
    parser = argparse.ArgumentParser(description="Recalcula la tonalidad (y lo que depende de ella) de las no favoritas.")
    parser.add_argument("--apply", action="store_true", help="Escribe en Google Sheets (por defecto solo simula).")
    parser.add_argument("--artist", default=None, help="Filtrar por artista.")
    parser.add_argument("--with-lyrics", action="store_true", help="Solo canciones con letra (columna Lyrics).")
    args = parser.parse_args()

    sheet = SongSheet()
    header, rows, col_map = sheet.read()
    if col_map.get("tonality", -1) == -1 or col_map.get("chord", -1) == -1:
        sys.exit("No se encontraron las columnas Chord y Tonality en la cabecera.")

    changes, skipped_liked, no_chords = plan_changes(header, rows, col_map, args.artist, args.with_lyrics)
    print(f"Canciones: {len(rows)} | favoritas omitidas: {skipped_liked} | sin acordes: {no_chords} "
          f"| con tonalidad distinta: {len(changes)}\n")
    for row_num, artist, title, diff in changes:
        print(f"[Fila {row_num:4d}] {artist} - {title}")
        for key, (old, new) in diff.items():
            print(f"           {key:12s} '{old or '(vacío)'}' -> '{new}'")

    if not args.apply:
        print("\n[SIMULACIÓN] No se ha escrito nada. Vuelve a ejecutar con --apply para guardar.")
        return
    if not changes:
        print("\nNada que escribir.")
        return

    # Backup of the values being replaced, so the run can be undone by hand
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(backup_dir, exist_ok=True)
    backup = os.path.join(backup_dir, f"recalc_tonality_backup_{datetime.now():%Y%m%d_%H%M%S}.json")
    with open(backup, "w", encoding="utf-8") as f:
        json.dump([{"row": r, "artist": a, "title": t, "old": {k: old for k, (old, _) in d.items()}}
                   for r, a, t, d in changes], f, ensure_ascii=False, indent=2)
    print(f"Copia de seguridad de los valores anteriores: {backup}")

    cells = [(row_num, key, new) for row_num, _, _, diff in changes for key, (_, new) in diff.items()]
    written = sheet.write_cells(cells, col_map)
    print(f"\nEscritas {written} celdas en {len(changes)} canciones ({', '.join(col_idx_to_letter(col_map[k]) for k in RECALC_KEYS if col_map.get(k, -1) != -1)}).")


if __name__ == "__main__":
    main()
