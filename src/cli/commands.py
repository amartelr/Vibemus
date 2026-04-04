"""Command handlers for Vibemus CLI subcommands.

Each ``handle_*`` function receives the parsed ``argparse.Namespace`` and an
initialised ``Manager`` instance, executes the corresponding business logic,
and returns an integer exit code (0 = success).
"""

import subprocess
import sys
from datetime import datetime

from ..config import Config


# ── Artist ────────────────────────────────────────────────────────────────────


def handle_artist(args, manager) -> int:
    """Dispatch artist sub-actions."""
    action = getattr(args, "action", None)

    if action == "add":
        return _artist_add(args, manager)
    elif action == "remove":
        return _artist_remove(args, manager)


    elif action == "cleanup-collabs":
        return _artist_cleanup_collabs(manager)
    elif action == "sync":
        return _artist_sync(args, manager)
    else:
        print("Usage: vibemus artist <add|remove|cleanup-collabs|sync>")
        print("Run 'vibemus artist --help' for details.")
        return 1


def _artist_add(args, manager) -> int:
    """Add or update an artist and run its search logic."""
    status, artist_data = manager.add_artist(
        args.name, 
        target_playlist=args.playlist, 
        api_choice=args.api
    )

    if status == "cancelled":
        print("  \033[91mOperation cancelled by user.\033[0m")
        return 0
    if not artist_data:
        return 1

    name = artist_data.get("Artist Name") or args.name
    
    if status == "added":
        print(f"✅ Successfully added '{name}' to tracking.")
    elif status == "exists":
        if args.playlist:
            print(f"ℹ️ Artist '{name}' already exists. Updating its target playlist to '{args.playlist}'...")
            manager.sheets.update_artist_playlist(name, args.playlist)
        else:
            print(f"ℹ️ Artist '{name}' is already being tracked.")

    # Always run discovery/sync when adding an artist (new or existing)
    added_count = manager.check_new_releases(
        Config.PLAYLIST_ID, 
        force=True, 
        target_artist_name=name, 
        target_artist_id=artist_data.get("Artist ID"),
        interactive=True
    )

    # ACCIONES FINALES: Actualizamos el registro del artista en el Excel tras sincronizar
    # (Haya o no nuevas canciones, ya lo hemos "estudiado")
    if added_count != -1: # Sync was not cancelled by user
        now_str = datetime.now().strftime("%d/%m/%Y")
        
        # 1. Marcar como Done y poner fecha
        manager.sheets.update_artist_last_checked(name, now_str)
        if artist_data.get("Status", "") != "Archived":
            manager.sheets.update_artist_status(name, "Done")
        
        # 2. Recalcular el Song Count total para este artista (en toda la hoja de canciones)
        all_songs = manager.sheets.get_songs_records()
        norm_name = manager._normalize(name)
        # REGLA: No contar canciones en el Inbox (#) para el Song Count acumulado
        artist_total = len([s for s in all_songs if manager._normalize(s.get('Artist', '')) == norm_name and s.get('Playlist') != '#'])
        
        # Actualizamos la fila del artista con el nuevo conteo de canciones
        artists_data = manager.sheets.get_artists()
        for a in artists_data:
            if a.get('Artist Name') == name or (not a.get('Artist Name') and a.get('Artist ID') == artist_data.get('Artist ID')):
                a['Song Count'] = artist_total
                break
        manager.sheets.save_artists(artists_data)

        if status == "exists":
            print(f"✅ Artist '{name}' metadata and status updated in tracking list.")
        
    return 0


def _artist_remove(args, manager) -> int:
    manager.remove_artist(args.name)
    return 0








def _artist_cleanup_collabs(manager) -> int:
    manager.cleanup_collab_artists()
    return 0


def _artist_sync(args, manager) -> int:
    manager.sync_artists_from_songs()
    return 0


# ── Sync ──────────────────────────────────────────────────────────────────────


def handle_sync(args, manager) -> int:
    """Dispatch sync sub-actions."""
    action = getattr(args, "action", None)

    if action == "deep":
        return _sync_deep(args, manager)
    elif action == "playlist":
        return _sync_playlist(args, manager)
    elif action == "releases":
        return _sync_releases(args, manager)
    elif action == "new-releases":
        return _sync_new_releases(args, manager)
    elif action == "genre":
        return _sync_genre(args, manager)
    else:
        print("Usage: vibemus sync <deep|playlist|releases|new-releases|genre>")
        print("Run 'vibemus sync --help' for details.")
        return 1


def _sync_deep(args, manager) -> int:
    manager.deep_sync_all_artists(interactive=not args.auto)
    return 0


def _sync_playlist(args, manager) -> int:
    print("Starting playlist sync...")
    manager.sync_playlist(
        playlist_name=getattr(args, "name", None),
        skip_lastfm=args.skip_lastfm,
    )
    return 0





def _sync_genre(args, manager) -> int:
    manager.sync_genre_summary()
    return 0


def _sync_releases(args, manager) -> int:
    """Sync all artists for new releases (ignores 30-day window if forced)."""
    manager.sync_all_artist_releases(
        force=getattr(args, "force", False),
        interactive=not getattr(args, "auto", False)
    )
    return 0


def _sync_new_releases(args, manager) -> int:
    """Sync global new releases shelf and check if any tracked artists have updates."""
    manager.sync_global_new_releases(interactive=not getattr(args, "auto", False))
    return 0





# ── Playlist ──────────────────────────────────────────────────────────────────


def handle_playlist(args, manager) -> int:
    """Dispatch playlist sub-actions."""
    action = getattr(args, "action", None)

    if action == "cleanup-inbox":
        return _playlist_cleanup_inbox(manager)
    elif action == "cleanup-likes":
        return _playlist_cleanup_likes(args, manager)
    elif action == "apply-moves":
        return _playlist_apply_moves(args, manager)
    elif action == "split":
        return _playlist_split(args, manager)
    elif action == "cleanup-library":
        return _playlist_cleanup_library(manager)
    elif action == "list":
        return _playlist_list(manager)
    else:
        print(
            "Usage: vibemus playlist "
            "<cleanup-inbox|cleanup-likes|apply-moves|split|list>"
        )
        print("Run 'vibemus playlist --help' for details.")
        return 1





def _playlist_cleanup_inbox(manager) -> int:
    manager.cleanup_inbox_duplicates()
    return 0

def _playlist_cleanup_likes(args, manager) -> int:
    manager.cleanup_likes()
    return 0
def _playlist_apply_moves(args, manager) -> int:
    manager.apply_manual_moves(
        refresh_cache=args.refresh_cache,
        target_artist_name=args.artist,
        target_playlist_name=args.playlist,
        api_choice=args.api
    )
    return 0







def _playlist_split(args, manager) -> int:
    import re
    pl_name = args.name
    
    # 0. Validación de seguridad: Nunca permitir split en la Inbox (#)
    if pl_name == "#":
        print("❌ Error: No se puede dividir la playlist de Inbox '#'. Solo se pueden dividir playlists principales (ej. 'Rock').")
        return 1

    # 1. Obtener todas las playlists relacionadas (principal + archivos configurados)
    related_playlists = [pl_name]
    intervals = manager._archiving_config.get(pl_name, [])
    for start, end in intervals:
        related_playlists.append(f"{pl_name} ({start}-{end})")
    
    # 2. Recopilar canciones de la principal y de CUALQUIER archivo que siga el patrón (Nombre (...))
    all_songs = manager.sheets.get_songs_records()
    prefix = f"{pl_name} ("
    pl_songs = [
        s for s in all_songs 
        if s.get('Playlist') == pl_name or (s.get('Playlist', '').startswith(prefix) and s.get('Playlist', '').endswith(")"))
    ]
    
    if not pl_songs:
        print(f"❌ No se han encontrado canciones para '{pl_name}' (ni en sus archivos) en el Sheet.")
        return 1
    
    years = []
    missing_years = []
    for s in pl_songs:
        found_y = None
        y_str = str(s.get('Year', '')).strip()
        if y_str:
            match = re.search(r'(\d{4})', y_str)
            if match:
                found_y = int(match.group(1))
                years.append(found_y)
        
        if found_y is None:
            missing_years.append(s)
    
    # 3. Informar y Bloquear si faltan años
    if missing_years:
        print(f"\n⚠️  ALERTA DE SEGURIDAD: Se han detectado {len(missing_years)} canciones sin el metadato 'Year' en '{pl_name}':")
        for s in missing_years[:10]:
            artist = s.get('Artist', 'Unknown Artist')
            title = s.get('Title', 'Unknown Title')
            print(f"   - 🚫 {artist} - {title}")
        
        if len(missing_years) > 10:
            print(f"   ... y otras {len(missing_years) - 10} canciones más.")
            
        print(f"\n❌ Error: No se puede proceder con el 'split' porque hay canciones sin año.")
        print(f"💡 Por favor, completa la columna 'Year' en el Google Sheet para estas canciones y vuelve a intentarlo.")
        return 1

    min_y = min(years) if years else 0
    max_y = max(years) if years else 0
    
    print(f"\n📊 Análisis de colección global para '{pl_name}':")
    print(f"   - Canciones totales (Principal + {len(related_playlists)-1} Archivos): {len(pl_songs)}")
    print(f"   - Rango detectado: {min_y} - {max_y}")
    
    # 3. Datos de la división (Automática por partes o Manual por flags)
    if args.parts and args.parts > 1:
        suggested_buckets = _calculate_year_buckets(years, args.parts)
        print(f"\n📋 Sugerencia de división en {args.parts} partes:")
        for i, (s, e, count) in enumerate(suggested_buckets, 1):
            print(f"   {i}. [{s} - {e}]: {count} canciones")
        
        confirm = input(f"\n👉 ¿Estás de acuerdo con esta división? (s/n): ").strip().lower()
        if confirm in ['s', 'si', 'y', 'yes']:
            print(f"\n🚀 Iniciando división automática en {args.parts} bloques...")
            # Aplicamos todos los rangos excepto el último (que queda en la playlist principal)
            for s_year, e_year, _ in suggested_buckets[:-1]:
                manager.split_playlist_by_year(pl_name, s_year, e_year)
            
            # Rebalanceo final automático
            print("\n🕵️  Verificando consistencia de años en las nuevas playlists...")
            manager.rebalance_playlist_archives(pl_name)
            
            print(f"\n✅ Proceso de división automática finalizado.")
            return 0
        else:
            print("🛑 Operación cancelada.")
            return 0
    else:
        # Si llegamos aquí sin --parts es porque el parser falló o algo raro pasó,
        # pero como ya es required en el parser, esto es solo por seguridad.
        print("❌ Error: El parámetro --parts es obligatorio para el comando split.")
        return 1

def _playlist_cleanup_library(manager) -> int:
    print("\n" + "━"*60)
    print("🧹 VIBEMUS LIBRARY CLEANUP (Songs NOT in Playlists)")
    print("━"*60)

    # 1. Get Authorized set from Google Sheet
    print("\n1. Scanning Google Sheet (Songs)...")
    all_songs_in_sheet = manager.sheets.get_songs_records()
    
    sheet_vids = set()
    for s in all_songs_in_sheet:
        vid = s.get('Video ID')
        pl = s.get('Playlist')
        if vid and pl != '#':
            sheet_vids.add(vid)
    
    print(f"   Collected {len(sheet_vids)} unique songs from the 'Songs' sheet (excluding '#').")

    # 2. Get total library scan
    print("\n2. Scanning YouTube Music Library (Songs section)...")
    library_songs = manager.yt.get_library_songs(limit=None)
    print(f"   Found {len(library_songs)} songs in the Library.")

    # 3. Identify candidates for removal
    print("\n3. Identifying items to remove...")
    to_remove = []
    liked_to_keep = 0
    for s in library_songs:
        vid = s.get('videoId')
        if not vid: continue
        
        # Rule: Not in our Sheets AND not Liked
        in_sheet = vid in sheet_vids
        is_liked = s.get('likeStatus') == 'LIKE'
        
        if not in_sheet:
            if is_liked:
                liked_to_keep += 1
            else:
                to_remove.append(s)

    print(f"   Songs in Library NOT found in Sheet: {len(to_remove) + liked_to_keep}")
    print(f"   - To keep (Liked): {liked_to_keep}")
    print(f"   - To remove:      {len(to_remove)}")

    if not to_remove:
        print("\n✨ Library is already clean! No songs to remove.")
        return 0

    # 4. Show Preview (Top 20)
    print("\n4. Preview of removal list:")
    for s in to_remove[:20]:
        artist = s.get('artists', [{}])[0].get('name', 'Unknown')
        title = s.get('title', 'Unknown')
        print(f"   - {artist} - {title}")
    
    if len(to_remove) > 20:
        print(f"   ... and {len(to_remove) - 20} more.")

    # 5. Final Confirmation
    confirm = input(f"\n👉 Do you want to REMOVE {len(to_remove)} songs from your library? (s/n): ").strip().lower()
    if confirm not in ['s', 'si', 'y', 'yes', '']:
        print("🛑 Cleanup cancelled.")
        return 0

    # 6. Execute removal in batches
    print(f"\n5. Executing removal of {len(to_remove)} songs...")
    batch_size = 25
    
    for i in range(0, len(to_remove), batch_size):
        batch_items = to_remove[i:i+batch_size]
        batch_tokens = [it.get('feedbackTokens', {}).get('remove') for it in batch_items if it.get('feedbackTokens', {}).get('remove')]
        batch_vids = [it['videoId'] for it in batch_items if not it.get('feedbackTokens', {}).get('remove')]
        
        try:
            print(f"   Removing batch {i//batch_size + 1}/{(len(to_remove)-1)//batch_size + 1}...")
            if batch_tokens:
                manager.yt.edit_song_library_status(feedback_tokens=batch_tokens)
            if batch_vids:
                # Fallback for any itesm missing remove tokens
                manager.yt.edit_song_library_status(video_ids=batch_vids)
        except Exception as e:
            print(f"   ❌ Error removing batch starting at {i}: {e}")

    print("\n" + "━"*60)
    print(f"✅ CLEANUP COMPLETED: {len(vids_to_remove)} songs removed.")
    print("━"*60 + "\n")
    return 0

def _playlist_list(manager) -> int:
    manager.list_playlists_counts()
    return 0

def _calculate_year_buckets(years, num_parts):
    """Calculates approximately equal year buckets from a list of years.
    
    Ensures that a whole year belongs to exactly one bucket.
    """
    if not years or num_parts < 1:
        return []
    
    years.sort()
    total = len(years)
    part_size = total / num_parts
    
    buckets = []
    current_start_idx = 0
    
    for i in range(num_parts):
        if current_start_idx >= total:
            break
            
        target_end_idx = min(int((i + 1) * part_size), total - 1)
        
        # El año de fin de este bucket
        end_year = years[target_end_idx]
        
        # Ajustar para incluir TODAS las canciones del mismo año en este bucket
        # (Si no es el último bucket)
        if i < num_parts - 1:
            while target_end_idx + 1 < total and years[target_end_idx + 1] == end_year:
                target_end_idx += 1
        else:
            target_end_idx = total - 1
            end_year = years[-1]

        start_year = years[current_start_idx]
        count = target_end_idx - current_start_idx + 1
        buckets.append((start_year, end_year, count))
        
        current_start_idx = target_end_idx + 1
        
    return buckets





# ── System ────────────────────────────────────────────────────────────────────


def handle_system(args, manager) -> int:
    """Dispatch system sub-actions."""
    action = getattr(args, "action", None)

    if action == "refresh-cache":
        return _system_refresh_cache(manager)
    elif action == "auth":
        return _system_auth()
    else:
        print("Usage: vibemus system <refresh-cache|auth>")
        print("Run 'vibemus system --help' for details.")
        return 1





def _system_refresh_cache(manager) -> int:
    manager.refresh_source_cache_only()
    return 0


def _system_auth() -> int:
    """Run the grab_cookies.js authentication helper."""
    import os

    script_path = os.path.join(Config.BASE_DIR, "grab_cookies.js")
    if not os.path.exists(script_path):
        print(f"Error: Authentication script not found at {script_path}")
        return 1

    print("Launching authentication helper...")
    try:
        subprocess.run(["node", script_path], check=True)
    except FileNotFoundError:
        print("Error: Node.js is required. Install it via 'brew install node'.")
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Authentication failed with exit code {exc.returncode}.")
        return exc.returncode

    return 0
