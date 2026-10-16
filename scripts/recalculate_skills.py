#!/usr/bin/env python3
"""
recalculate_skills.py
Recalcula y actualiza la columna 'Skill' (o 'Complejidad') en la hoja Google Sheets ('Songs').

Modos de uso:
  1. Modo armónico (por defecto):
     python3 scripts/recalculate_skills.py
     Lee los acordes ya guardados en cada fila y recalcula la dificultad según el
     algoritmo armónico recalibrado (infer_complexity). Es ultra rápido y no requiere scraping.

  2. Modo Ultimate Guitar (Punto 2 por defecto, Punto 1 como fallback):
     python3 scripts/recalculate_skills.py --mode ug
     Consulta Ultimate Guitar para buscar la dificultad nativa (novice/intermediate/advanced);
     si la tablatura no tiene dificultad declarada o falla la consulta, usa infer_complexity.

  3. Modo simulación (Dry-Run):
     python3 scripts/recalculate_skills.py --dry-run
     Muestra qué canciones cambiarían de nivel sin escribir nada en Google Sheets.

  4. Filtrar por artista específico:
     python3 scripts/recalculate_skills.py --artist "Freedom Fry"
"""

import sys
import os
import argparse
import time

# Run from anywhere: put the repo root on the path so `src.web.server` resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.sheet_gateway import SongSheet, get_column_mapping, col_idx_to_letter
from src.web.harmony import infer_complexity
from src.web.ultimate_guitar import map_native_difficulty, fetch_ug_chords

def run_recalculation(mode="harmonic", dry_run=False, artist_filter=None, force=False, limit=None):
    print("=" * 60)
    print(" RECALCULANDO COLUMNA 'SKILL' EN GOOGLE SHEETS")
    print(f" Modo: {'Armónico rápido (infer_complexity)' if mode == 'harmonic' else 'Ultimate Guitar con fallback armónico'}")
    print(f" Dry Run: {'SÍ (no se guardarán cambios)' if dry_run else 'NO (se actualizará Google Sheets)'}")
    if artist_filter:
        print(f" Filtro de artista: {artist_filter}")
    if limit:
        print(f" Límite: {limit} canciones")
    print("=" * 60)

    try:
        sheet = SongSheet()
        print("Conectado a Google Sheets. Leyendo datos...")
        values = sheet.ws.get_all_values()
    except Exception as e:
        print(f"Error al conectar con Google Sheets: {e}")
        return

    if not values or len(values) < 2:
        print("No se encontraron filas en la hoja Songs.")
        return

    headers = values[0]
    col_map = get_column_mapping(headers)
    
    artist_idx = col_map.get("artist", -1)
    title_idx = col_map.get("title", -1)
    chord_idx = col_map.get("chord", -1)
    tonality_idx = col_map.get("tonality", -1)
    skill_idx = col_map.get("skill", -1)
    complex_idx = col_map.get("complex", -1)

    # Identificar columnas a actualizar
    target_cols = set()
    if skill_idx != -1:
        target_cols.add(skill_idx)
    if complex_idx != -1:
        target_cols.add(complex_idx)

    if not target_cols:
        print("Error: No se encontró la columna 'skill' o 'complejidad' en la cabecera de la hoja.")
        print(f"Cabeceras encontradas: {headers}")
        return

    col_letters = [col_idx_to_letter(idx) for idx in target_cols]
    print(f"Columnas detectadas para Skill/Complejidad: {col_letters} (índices {list(target_cols)})")

    total_rows = len(values) - 1
    processed = 0
    updated_count = 0
    unchanged_count = 0
    no_chords_count = 0
    skipped_filter = 0

    updates = []
    level_counts = {"Baja": 0, "Media": 0, "Media-Alta": 0, "Alta": 0}

    print(f"\nProcesando {total_rows} canciones...")

    for idx, row in enumerate(values[1:]):
        row_num = idx + 2
        processed += 1

        artist = row[artist_idx].strip() if artist_idx != -1 and artist_idx < len(row) else ""
        title = row[title_idx].strip() if title_idx != -1 and title_idx < len(row) else ""
        chord = row[chord_idx].strip() if chord_idx != -1 and chord_idx < len(row) else ""
        tonality = row[tonality_idx].strip() if tonality_idx != -1 and tonality_idx < len(row) else ""

        # Valor actual en la hoja
        current_skill = ""
        for c_idx in target_cols:
            if c_idx < len(row) and row[c_idx].strip():
                current_skill = row[c_idx].strip()
                break

        if artist_filter and artist_filter.lower() not in artist.lower():
            skipped_filter += 1
            continue

        if not chord:
            no_chords_count += 1
            continue

        if limit and (updated_count + unchanged_count) >= limit:
            print(f"Alcanzado el límite configurado de {limit} canciones procesadas.")
            break

        # Cálculo según el modo
        new_skill = None
        source_note = ""

        if mode == "ug":
            # Intentar consultar UG
            try:
                ug_res = fetch_ug_chords(artist, title)
                if ug_res and ug_res.get("complex"):
                    new_skill = ug_res.get("complex")
                    source_note = f"UG ({ug_res.get('source', '')})"
            except Exception:
                pass
            time.sleep(0.3)  # Evitar rate-limiting si se consulta UG

        if not new_skill:
            new_skill = infer_complexity(chord, tonality)
            source_note = "Armónico recalibrado"

        level_counts[new_skill] = level_counts.get(new_skill, 0) + 1

        # ¿Ha cambiado?
        if current_skill.lower() != new_skill.lower() or force:
            updated_count += 1
            print(f"  [Fila {row_num:4d}] {artist} - {title}")
            print(f"           '{current_skill or '(vacío)'}'  -->  '{new_skill}'  [{source_note}]")

            for c_idx in target_cols:
                letter = col_idx_to_letter(c_idx)
                if letter:
                    updates.append({
                        "range": f"Songs!{letter}{row_num}",
                        "values": [[new_skill]]
                    })
        else:
            unchanged_count += 1

    print("\n" + "=" * 60)
    print(" RESUMEN DEL PROCESO")
    print("=" * 60)
    print(f"Total canciones en hoja:     {total_rows}")
    if artist_filter:
        print(f"Omitidas por filtro artista: {skipped_filter}")
    print(f"Canciones sin acordes:       {no_chords_count}")
    print(f"Canciones analizadas:        {updated_count + unchanged_count}")
    print(f"Canciones con cambio:        {updated_count}")
    print(f"Canciones sin cambio:        {unchanged_count}")
    print("\nDistribución de nuevos niveles:")
    for lvl, cnt in level_counts.items():
        print(f"  - {lvl:12s}: {cnt}")

    if dry_run:
        print("\n[DRY RUN] No se ha modificado Google Sheets.")
        return

    if not updates:
        print("\nNo hay actualizaciones que realizar. Todas las canciones ya tenían el valor correcto.")
        return

    print(f"\nEscribiendo {len(updates)} celdas en Google Sheets en lotes...")
    # Escribir en lotes de 500 para respetar límites de Google Sheets API
    batch_size = 500
    for i in range(0, len(updates), batch_size):
        chunk = updates[i:i + batch_size]
        try:
            sheet.ws.batch_update(
                [{"range": u["range"].split("!", 1)[-1], "values": u["values"]} for u in chunk],
                value_input_option="RAW")
            print(f"  Lote {i // batch_size + 1} ({len(chunk)} celdas) guardado.")
        except Exception as e:
            print(f"  Error al guardar lote {i // batch_size + 1}: {e}")

    print("\nActualización en Google Sheets completada exitosamente.")


def main():
    parser = argparse.ArgumentParser(
        description="Recalcula la columna Skill en Google Sheets con la nueva calibración."
    )
    parser.add_argument(
        "--mode",
        choices=["harmonic", "ug"],
        default="harmonic",
        help="Modo de cálculo: 'harmonic' (rápido por acordes, por defecto) o 'ug' (consulta Ultimate Guitar)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulación: muestra los cambios sin escribirlos en Google Sheets."
    )
    parser.add_argument(
        "--artist",
        type=str,
        default=None,
        help="Filtrar por artista (por ejemplo --artist 'Freedom Fry')."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Fuerza la sobreescritura incluso si el valor no cambia."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Límite máximo de canciones a procesar (por ejemplo --limit 100)."
    )
    args = parser.parse_args()

    run_recalculation(
        mode=args.mode,
        dry_run=args.dry_run,
        artist_filter=args.artist,
        force=args.force,
        limit=args.limit
    )

if __name__ == "__main__":
    main()
