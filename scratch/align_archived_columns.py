import sys
import os
sys.path.append(os.getcwd())

from src.services.sheets_service import SheetsService

def main():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🔄 ALINEANDO COLUMNAS: SONGS ➔ ARCHIVED")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    sheets = SheetsService()
    
    # 1. Obtener hojas de cálculo
    print("Conectando con Google Sheets...")
    songs_ws = sheets._get_worksheet("Songs")
    archived_ws = sheets._get_worksheet("Archived")
    
    # 2. Leer encabezados actuales
    songs_headers = songs_ws.row_values(1)
    archived_headers = archived_ws.row_values(1)
    
    print(f"Columnas en Songs ({len(songs_headers)}): {songs_headers}")
    print(f"Columnas en Archived ({len(archived_headers)}): {archived_headers}")
    
    if songs_headers == archived_headers:
        print("\n✅ ¡Las columnas ya coinciden perfectamente! No se requiere ninguna acción.")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return

    print("\n⚠️ Se detectó una diferencia en las columnas. Iniciando alineación...")
    
    # 3. Determinar el set de columnas objetivo (el de Songs)
    target_headers = songs_headers
    
    # 4. Asegurar que Archived tenga suficiente tamaño
    current_cols = archived_ws.col_count
    needed_cols = len(target_headers)
    if current_cols < needed_cols:
        print(f"  Aumentando el número de columnas de Archived de {current_cols} a {needed_cols}...")
        archived_ws.resize(cols=needed_cols)
        
    # 5. Obtener todos los valores actuales de Archived para no perder nada
    all_archived_data = archived_ws.get_all_values()
    
    # Si la hoja está vacía o solo tiene la cabecera vieja
    if len(all_archived_data) <= 1:
        print("  La hoja Archived está casi vacía. Escribiendo nueva cabecera...")
        archived_ws.clear()
        archived_ws.update(range_name='A1', values=[target_headers])
        print("✅ Cabecera de Archived actualizada con éxito.")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return
        
    # Si tiene filas de datos, debemos mapearlas correctamente
    old_headers = all_archived_data[0]
    old_rows = all_archived_data[1:]
    
    print(f"  Mapeando {len(old_rows)} filas existentes de Archived a las nuevas columnas...")
    
    new_rows = [target_headers]
    for row in old_rows:
        new_row = []
        for header in target_headers:
            # Si la columna ya existía en la hoja anterior, conservar el valor
            if header in old_headers:
                idx = old_headers.index(header)
                val = row[idx] if idx < len(row) else ""
            else:
                # Si es una columna nueva (ej. Tonality, Progression, Chord), dejar vacía
                val = ""
            new_row.append(val)
        new_rows.append(new_row)
        
    # 6. Guardar cambios en Archived de forma atómica
    print("  Guardando cambios en Google Sheets...")
    archived_ws.clear()
    archived_ws.update(range_name='A1', values=new_rows)
    
    print("\n✅ ¡Alineación completada con éxito!")
    print(f"Ahora la pestaña Archived tiene exactamente las mismas {len(target_headers)} columnas que Songs.")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

if __name__ == "__main__":
    main()
