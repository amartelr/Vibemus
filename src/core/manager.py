import os
import json
import time
import re
from datetime import datetime, timedelta
from src.config import Config

class Manager:
    def __init__(self, yt_service, sheets_service, lastfm_service, musicbrainz_service):
        self.yt = yt_service
        self.sheets = sheets_service
        self.lastfm = lastfm_service
        self.musicbrainz = musicbrainz_service

    def _resolve_playlist_id(self, pl_name):
        if not pl_name: return None
        if pl_name == '#': return Config.PLAYLIST_ID
        try:
            res = self.yt.yt.search(pl_name, filter='playlists', scope='library')
            for r in res:
                if r.get('title', '').lower().strip() == pl_name.lower().strip():
                    return r.get('playlistId') or r.get('browseId', '').replace('VL', '')
        except:
            pass
        return None

    def _normalize(self, text):
        if not text: return ""
        return str(text).lower().strip()

    def _get_archive_threshold(self, archive_playlist_name):
        """Get the year threshold from an archive '$' playlist's description.
        
        Reads the YouTube Music playlist description (e.g. 'Archivo: canciones ≤ 2021')
        and extracts the year. Results are cached per session.
        """
        if not hasattr(self, '_archive_thresholds'):
            self._archive_thresholds = {}
        
        if archive_playlist_name in self._archive_thresholds:
            return self._archive_thresholds[archive_playlist_name]
        
        threshold = None
        try:
            # Find the playlist in the library
            res = self.yt.yt.search(archive_playlist_name, filter='playlists', scope='library')
            for r in res:
                if r.get('title', '').lower().strip() == archive_playlist_name.lower().strip():
                    pl_id = r.get('playlistId') or r.get('browseId', '').replace('VL', '')
                    if pl_id:
                        # Get full playlist details to read description
                        pl_data = self.yt.yt.get_playlist(pl_id, limit=0)
                        desc = pl_data.get('description', '')
                        if desc:
                            match = re.search(r'(\d{4})', desc)
                            if match:
                                threshold = int(match.group(1))
                    break
        except Exception as e:
            print(f"    \033[90m⚠ No se pudo leer la descripción de '{archive_playlist_name}': {e}\033[0m")
        
        self._archive_thresholds[archive_playlist_name] = threshold
        return threshold

    def _fetch_song_year(self, vid, title, artist):
        """Try to fetch a song's release year from YouTube Music API. 
        Prioritizes album metadata over video upload dates for accuracy.
        """
        fetched_year = ''
        norm_title = self._normalize(title)
        norm_artist = self._normalize(artist)

        # Strategy 1: Search by title+artist and match metadata
        try:
            query = f"{artist} {title}".strip()
            results = self.yt.yt.search(query, filter='songs')
            for r in results:
                # Check if this result matches our song
                is_match = r.get('videoId') == vid or (
                    self._normalize(r.get('title', '')) == norm_title
                    and any(self._normalize(a.get('name', '')) == norm_artist for a in r.get('artists', []))
                )

                if is_match:
                    # 1a. Try to get album year (MOST ACCURATE)
                    alb_id = r.get('album', {}).get('id')
                    if alb_id:
                        try:
                            # Use direct album check
                            from ytmusicapi import YTMusic
                            alb_data = self.yt.yt.get_album(alb_id)
                            alb_yr = alb_data.get('year')
                            # Safety check: allow 2026 but be wary of future upload artifacts
                            if alb_yr and str(alb_yr).isdigit() and int(alb_yr) <= 2026:
                                return str(alb_yr)
                        except: pass
                    
                    # 1b. Fallback to year from search result
                    yr = r.get('year')
                    if yr and str(yr).isdigit() and int(yr) <= 2026:
                        return str(yr)
                    
                    break # Match found, if no year yet, try next strategy
        except Exception:
            pass

        # Strategy 2: Direct lookup via get_song (different endpoint)
        try:
            song_data = self.yt.yt.get_song(vid)
            # Try getting album from here too
            alb_id = song_data.get('album', {}).get('id') or song_data.get('videoDetails', {}).get('albumId')
            if alb_id:
                try:
                    alb_data = self.yt.yt.get_album(alb_id)
                    alb_yr = alb_data.get('year')
                    if alb_yr and str(alb_yr).isdigit() and int(alb_yr) <= 2026:
                        return str(alb_yr)
                except: pass
            
            # Strategy 3: Absolute last resort: Upload Date (only if reasonable)
            mf = song_data.get('microformat', {}).get('microformatDataRenderer', {})
            up_date = mf.get('uploadDate', '') or mf.get('datePublished', '')
            if up_date:
                m = re.search(r'(\d{4})', up_date)
                if m:
                    y = int(m.group(1))
                    if 1900 < y <= 2026: 
                        return str(y)
        except Exception:
            pass

        return fetched_year

    def _load_source_cache(self):
        try:
            if os.path.exists(Config.SOURCE_CACHE_FILE):
                with open(Config.SOURCE_CACHE_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _save_source_cache(self, cache):
        try:
            os.makedirs(os.path.dirname(Config.SOURCE_CACHE_FILE), exist_ok=True)
            with open(Config.SOURCE_CACHE_FILE, 'w') as f:
                json.dump(cache, f, indent=4)
        except Exception as e:
            print(f"Error saving source cache: {e}")

    def refresh_source_cache_only(self):
        print("\n\033[96m" + "━"*50 + "\033[0m")
        print("\033[1;96m🔄 REFRESHING SOURCE PLAYLIST CACHE\033[0m")
        print("\033[96m" + "━"*50 + "\033[0m")
        print("\033[90mFetching library playlists...\033[0m")
        
        source_cache = {}
        for pl_name in Config.SOURCE_PLAYLISTS:
            print(f"  Fetching '{pl_name}'...")
            playlist_id = None
            if pl_name == '#':
                playlist_id = Config.PLAYLIST_ID
            else:
                try:
                    search_res = self.yt.yt.search(pl_name, filter='playlists', scope='library')
                    for r in search_res:
                        if r.get('title', '').lower().strip() == pl_name.lower().strip():
                            playlist_id = r.get('playlistId') or r.get('browseId', '').replace('VL', '')
                            break
                except:
                    pass
            
            if playlist_id:
                items = self.yt.get_playlist_items_with_status(playlist_id)
                if items:
                    source_cache[pl_name] = items
                    print(f"    → {len(items)} songs")
            else:
                print(f"    ⚠ Could not resolve playlist ID for '{pl_name}'")

        self._save_source_cache(source_cache)
        total = sum(len(v) for v in source_cache.values())
        print(f"\n\033[92m✅ Cache refreshed:\033[0m \033[1m{len(source_cache)} playlists, {total} total songs.\033[0m\n")

    def apply_manual_moves(self, refresh_cache=False, target_artist_name=None, api_choice="lastfm"):
        print("\n\033[96m" + "━"*50 + "\033[0m")
        print(f"\033[1;96m🎤 VIBEMUS CLASSIFICATION ASSISTANT (apply-moves - {api_choice})\033[0m")
        
        # Select the metadata service
        meta_service = self.musicbrainz if api_choice == "musicbrainz" else self.lastfm
        
        artist_genres = '(Desconocido)'
        any_change_session = False
        if target_artist_name:
            print(f"\033[93m🎯 Filtro Artista: {target_artist_name}\033[0m")
            artist_info = meta_service.get_artist_info(target_artist_name, cache_ttl_days=-1)
            artist_genres = artist_info.get('genre', '(Desconocido)') if artist_info else '(Desconocido)'
            print(f"\033[95m   👤 Género del Artista: {artist_genres}\033[0m")
            
            # Check if artist genre has changed to queue an update at the end
            artists_records = self.sheets.get_artists()
            norm_target = self._normalize(target_artist_name)
            for arec in artists_records:
                if self._normalize(arec.get('Artist Name', '')) == norm_target:
                    old_ag = arec.get('Genre', '')
                    if artist_info and artist_genres != '(Desconocido)' and old_ag != artist_genres:
                        any_change_session = True
                    break
        print("\033[96m" + "━"*50 + "\033[0m")

        if refresh_cache:
            self.refresh_source_cache_only()

        all_songs = self.sheets.get_songs_records()
        source_cache = self._load_source_cache()
        if not source_cache:
            print("Source cache is empty! Run system refresh-cache first.")
            return

        songs_to_process = all_songs
        if target_artist_name:
            norm_target = self._normalize(target_artist_name)
            songs_to_process = [s for s in all_songs if norm_target in self._normalize(s.get('Artist', ''))]
            if not songs_to_process:
                print(f"No se encontraron canciones para: {target_artist_name}")
                return
            print(f"Revisando {len(songs_to_process)} canciones...")

        cache_vids = {}
        vid_to_cache_entries = {}
        for cache_key, items in source_cache.items():
            pl_lower = cache_key.lower()
            if pl_lower not in cache_vids: cache_vids[pl_lower] = set()
            for item in items:
                vid = item.get('videoId')
                if not vid: continue
                cache_vids[pl_lower].add(vid)
                if vid not in vid_to_cache_entries: vid_to_cache_entries[vid] = []
                vid_to_cache_entries[vid].append((cache_key, item))

        print("  Cargando IDs de playlists...")
        moves_applied = 0
        sheet_changed = False
        errors = 0
        playlist_counts = {}
        resolved_playlist_ids = {} # Cache local de IDs de destino

        def _finalize_song_iteration(current_pl):
            nonlocal sheet_changed, any_change_session
            if current_pl and current_pl != '#':
                playlist_counts[current_pl] = playlist_counts.get(current_pl, 0) + 1
            if sheet_changed:
                print(f"      💾 Resguardando progreso en Songs...")
                self.sheets.overwrite_songs(all_songs)
                sheet_changed = False
                any_change_session = True

        for song in songs_to_process:
            vid = song.get('Video ID')
            if not vid: continue

            # 1. Filtro Inbox: si solo está en '#', ignoramos por diseño
            other_entries_catalog = [(ck, item) for ck, item in vid_to_cache_entries.get(vid, []) if ck.lower() != '#']
            if not other_entries_catalog:
                continue

            # 2. Obtener Info del servicio seleccionado
            artist = song.get('Artist', '')
            song_title = song.get('Title', vid)
            
            # Forzamos la consulta ignorando la caché para mostrar los datos más frescos disponibles
            info = meta_service.get_track_info(artist, song_title, force_scrobbles=True, cache_ttl_days=-1)
            genres = info.get('genre', '(Desconocido)') if info else '(Desconocido)'
            scrobble = int(info.get('scrobble', 0)) if info else 0
            lastfm_scrobble = int(info.get('lastfm_listeners', 0)) or int(info.get('lastfm_scrobble', 0)) if info else 0
            
            # Update the track data to save to sheets
            if info:
                old_genre = song.get('Genre', '')
                if old_genre != genres:
                    song['Genre'] = genres
                    sheet_changed = True
                
                # Update scrobbles
                old_scrobble = song.get('Scrobble', 0)
                old_lastfm = song.get('LastfmScrobble', 0)
                
                # Check if scrobble values changed
                if str(old_scrobble) != str(scrobble) or str(old_lastfm) != str(lastfm_scrobble):
                    song['Scrobble'] = scrobble
                    song['LastfmScrobble'] = lastfm_scrobble
                    sheet_changed = True

            # 3. Mostrar Info y Preguntar
            target_pl = str(song.get('Playlist', '')).strip()
            target_pl_lower = target_pl.lower()
            current_pls = [ck for ck, _ in other_entries_catalog]
            
            song_year = str(song.get('Year', '')).strip()
            if not song_year:
                song_year = self._fetch_song_year(vid, song_title, artist)
                if song_year:
                    song['Year'] = song_year
                    sheet_changed = True
            year_str = f" \033[93m({song_year})\033[1;92m" if song_year else ""

            # Cálculo de estado de sincronización previo al prompt
            already_in_target = vid in cache_vids.get(target_pl_lower, set())
            # Está en sync si está en la de destino y NO está en ninguna otra del catálogo
            is_synced = already_in_target and not any(ck.lower() != target_pl_lower for ck, _ in other_entries_catalog)
            
            print(f"\n  \033[1;92m{artist} - {song_title}{year_str}\033[0m")
            if is_synced:
                print(f"    \033[92m✔ En sync con '{target_pl}'\033[0m")
            else:
                from_str = ", ".join(current_pls) if current_pls else "(Ninguna)"
                print(f"    \033[93m⚠ Diferencia detectada: \033[90m{from_str}\033[0m -> \033[1;94m{target_pl or '?'}\033[0m")
            
            print(f"    🎵  Género de la canción: \033[96m{genres}\033[0m")
            
            prompt = f"    📍 Destino (Enter=OK/Saltar, 'q'=salir, NuevaPL): "
            user_input = input(prompt).strip()

            if user_input.lower() == 'q':
                print("    Abortando y guardando cambios...")
                _finalize_song_iteration(None)
                break
                
            if user_input == '':
                if is_synced:
                    print("    ⏭  Mantenida sin cambios.")
                    _finalize_song_iteration(target_pl)
                    continue
                else:
                    pass  # Continuar con el movimiento (proceder a resolver ID de destino)
            elif user_input.lower() != target_pl.lower():
                # Si el usuario escribe una playlist distinta, actualizamos la hoja
                if user_input == '#':
                    print("    ⚠ El Inbox '#' no se permite como destino manual. Saltando.")
                    _finalize_song_iteration(target_pl)
                    continue
                
                song['Playlist'] = user_input
                target_pl = user_input
                target_pl_lower = target_pl.lower()
                sheet_changed = True
                print(f"      📝 Sheet: playlist actualizada a \033[92m'{target_pl}'\033[0m")

            if not target_pl or target_pl == '#':
                _finalize_song_iteration(target_pl)
                continue

            # 4. Resolver ID de destino
            target_pid = resolved_playlist_ids.get(target_pl_lower)
            if not target_pid:
                target_pid = self._resolve_playlist_id(target_pl)
                if target_pid:
                    resolved_playlist_ids[target_pl_lower] = target_pid
                else:
                    print(f"      ✗ Error: No se encontró la playlist '{target_pl}' en YouTube.")
                    errors += 1
                    _finalize_song_iteration(target_pl)
                    continue

            # 5. Ejecutar Movimientos en YouTube
            # Recalculamos tras posible cambio de user_input
            already_in_target = vid in cache_vids.get(target_pl_lower, set())
            old_pls_to_remove = [(ck, item) for ck, item in other_entries_catalog if ck.lower() != target_pl_lower]

            if not already_in_target:
                try:
                    self.yt.add_playlist_items(target_pid, [vid])
                    print(f"      ✅ YT: Añadida a '{target_pl}'")
                    moves_applied += 1
                    target_cache_key = next((k for k in Config.SOURCE_PLAYLISTS if k.lower() == target_pl_lower), target_pl)
                    if target_cache_key not in source_cache: source_cache[target_cache_key] = []
                    new_item = other_entries_catalog[0][1]
                    source_cache[target_cache_key].append(new_item)
                    cache_vids.setdefault(target_pl_lower, set()).add(vid)
                except Exception as e:
                    print(f"      ✗ error YT (Add): {e}")
                    errors += 1
                    _finalize_song_iteration(target_pl)
                    continue

            if old_pls_to_remove:
                for ck, item in old_pls_to_remove:
                    old_pid = resolved_playlist_ids.get(ck.lower())
                    if not old_pid:
                        old_pid = self._resolve_playlist_id(ck)
                        if old_pid: resolved_playlist_ids[ck.lower()] = old_pid
                    
                    if old_pid:
                        try:
                            self.yt.remove_playlist_items(old_pid, [item])
                            print(f"      ✅ YT: Quitada de '{ck}'")
                            source_cache[ck] = [i for i in source_cache[ck] if i.get('videoId') != vid]
                            if vid in cache_vids.get(ck.lower()): cache_vids[ck.lower()].remove(vid)
                            moves_applied += 1
                        except Exception as e:
                            if "400" in str(e) or "Precondition" in str(e):
                                print(f"      ↻ Refrescando caché de '{ck}' para reintentar eliminar...")
                                live_tracks = self.yt.get_playlist_items(old_pid)
                                live_item = next((t for t in live_tracks if t.get('videoId') == vid), None)
                                if live_item and live_item.get('setVideoId'):
                                    try:
                                        self.yt.remove_playlist_items(old_pid, [live_item])
                                        print(f"      ✅ YT: Quitada de '{ck}' (tras refresco)")
                                        source_cache[ck] = [i for i in source_cache[ck] if i.get('videoId') != vid]
                                        if ck.lower() in cache_vids and vid in cache_vids[ck.lower()]: cache_vids[ck.lower()].remove(vid)
                                        moves_applied += 1
                                    except Exception as retry_err:
                                        print(f"      ✗ error YT (Remove Retried): {retry_err}")
                                        errors += 1
                                else:
                                    print(f"      ⚠ La canción ya no estaba en '{ck}'. Saneando caché.")
                                    source_cache[ck] = [i for i in source_cache[ck] if i.get('videoId') != vid]
                                    if ck.lower() in cache_vids and vid in cache_vids[ck.lower()]: cache_vids[ck.lower()].remove(vid)
                                    moves_applied += 1
                            else:
                                print(f"      ✗ error YT (Remove): {e}")
                                errors += 1

            _finalize_song_iteration(target_pl)

        # 6. Persistencia Final
        if moves_applied > 0: 
            self._save_source_cache(source_cache)
        
        if target_artist_name:
            # We already saved per-song increments, but inform the user we're done with the iteration.
            print("\n✅ Sesión de canciones finalizada.")

            final_pl_for_artist = None
            
            # If we processed songs, we can suggest a playlist default
            if playlist_counts:
                most_common_pl = max(playlist_counts, key=playlist_counts.get)
                # Strip any trailing ' $' or ' #' from user preferences
                suggestion = most_common_pl.rstrip(' #$').strip()
                
                print(f"\n📢 Recomendación para Artista '{target_artist_name}':")
                print(f"   La playlist más usada para sus canciones fue '{most_common_pl}'.")
                confirm_prompt = f"   ¿Actualizar su playlist por defecto a \033[92m'{suggestion}'\033[0m? (Enter=Confirmar, escribe otra, 'n'=No): "
                user_choice = input(confirm_prompt).strip()
                
                if user_choice == '':
                    final_pl_for_artist = suggestion
                elif user_choice.lower() != 'n':
                    final_pl_for_artist = user_choice

            artists_records = self.sheets.get_artists()
            norm_target = self._normalize(target_artist_name)
            artist_updated = False
            
            for arec in artists_records:
                if self._normalize(arec.get('Artist Name', '')) == norm_target:
                    changed = False
                    
                    # Apply new playlist if user chose one
                    if final_pl_for_artist and arec.get('Playlist') != final_pl_for_artist:
                        arec['Playlist'] = final_pl_for_artist
                        changed = True
                        
                    # Apply artist genre
                    if artist_genres and artist_genres != '(Desconocido)' and arec.get('Genre') != artist_genres:
                        arec['Genre'] = artist_genres
                        changed = True
                        
                    if changed:
                        artist_updated = True
                        
                    break

            if artist_updated:
                self.sheets.save_artists(artists_records)
                pl_msg = f"playlist '{final_pl_for_artist}'" if final_pl_for_artist else "playlist sin cambios"
                print(f"✅ Sheet Artists: actualizada ({pl_msg}, género '{artist_genres}').")
            else:
                print("ℹ  La configuración del artista se mantiene igual (mismo género y playlist).")

        print("\n✅ ASISTENTE COMPLETADO\n" if not errors else f"\n⚠ COMPLETADO CON {errors} ERRORES\n")

    def _reorder_playlist_by_latest_added(self, playlist_name, playlist_id, all_songs):
        """Moves the 4 most recently added songs (last in the Songs sheet) to the top.
        This triggers YouTube Music to update the playlist collage cover.
        """
        if not playlist_id: return
        print(f"  \033[95m🖼 Generando portada dinámica (collage) para '{playlist_name}'...\033[0m")
        
        # 1. Get songs from sheet for this playlist (they are stored in insertion order)
        pl_songs = [s for s in all_songs if s.get('Playlist', '').lower() == playlist_name.lower()]
        
        if len(pl_songs) < 4:
            return

        # 2. Get last 4 (most recently added)
        latest_songs = pl_songs[-4:]
        latest_vids = [s.get('Video ID') for s in latest_songs if s.get('Video ID')]
        
        if not latest_vids:
            return

        # 3. Get current playlist tracks to find setVideoIds
        try:
            # We fetch up to 100 to find where our songs are
            playlist_data = self.yt.yt.get_playlist(playlist_id, limit=100)
            tracks = playlist_data.get('tracks', [])
            if not tracks: return
                
            vid_to_setvid = {t['videoId']: t['setVideoId'] for t in tracks if 'videoId' in t and 'setVideoId' in t}
            
            # Identify setVideoIds of our target songs
            target_set_vids = []
            for vid in latest_vids:
                if vid in vid_to_setvid:
                    target_set_vids.append(vid_to_setvid[vid])
            
            if not target_set_vids:
                return

            # 4. Perform moves sequentially to ensure they end up at 0, 1, 2, 3
            # We iterate in reverse order and move each to the top
            moves_made = 0
            for set_vid in reversed(target_set_vids):
                # Get current first item's setVideoId
                current_top = self.yt.yt.get_playlist(playlist_id, limit=1)['tracks']
                if not current_top: break
                
                top_set_vid = current_top[0]['setVideoId']
                
                if set_vid != top_set_vid:
                    self.yt.edit_playlist(playlist_id, moveItem=(set_vid, top_set_vid))
                    moves_made += 1
            
            if moves_made > 0:
                print(f"    \033[92m✓ Portada actualizada (usando últimas 4 canciones).\033[0m")
            else:
                print(f"    \033[90m(Portada ya optimizada).\033[0m")
                
        except Exception as e:
            print(f"    \033[91m✗ Error reordenando playlist: {e}\033[0m")

    def sync_playlist(self, playlist_name=None, skip_lastfm=False):
        print("\n\033[96m" + "━"*50 + "\033[0m")
        print(f"\033[1;96m🔄 SYNCING PLAYLIST: {playlist_name or 'ALL'}\033[0m")
        print("\033[96m" + "━"*50 + "\033[0m")
        
        if playlist_name:
            playlists_to_sync = [playlist_name]
        else:
            # By default sync all EXCEPT '#' (Inbox) - based on user preference to handle Inbox manually
            playlists_to_sync = [p for p in Config.SOURCE_PLAYLISTS if p != '#']
        
        source_cache = self._load_source_cache()
        all_songs = self.sheets.get_songs_records()
        artists_records = self.sheets.get_artists()
        disliked_vids_global = set()

        processed_playlist_ids = {} # To keep track for reordering later

        for idx, pl_name in enumerate(playlists_to_sync, 1):
            print(f"\n\033[1;94m[{idx}/{len(playlists_to_sync)}] 📂 Processing '{pl_name}'...\033[0m")
            is_hash = (pl_name == '#')
            
            # Resolve ID
            pid = Config.PLAYLIST_ID if is_hash else None
            
            if not is_hash:
                try:
                    res = self.yt.yt.search(pl_name, filter='playlists', scope='library')
                    for r in res:
                        if r.get('title', '').lower().strip() == pl_name.lower().strip():
                            pid = r.get('playlistId') or r.get('browseId', '').replace('VL', '')
                            break
                except: pass
            
            if not pid:
                print(f"  ⚠ Could not find playlist ID for '{pl_name}'")
                continue

            processed_playlist_ids[pl_name] = pid

            # Refresh
            fresh_items = self.yt.get_playlist_items_with_status(pid)
            if not fresh_items:
                print(f"  ⚠ No items found for '{pl_name}'")
                continue
            
            cache_key = next((k for k in source_cache if k.lower() == pl_name.lower()), pl_name)
            source_cache[cache_key] = fresh_items
            self._save_source_cache(source_cache)

            # Check for duplicates on YouTube and remove them
            seen_vids = set()
            duplicates_to_remove = []
            final_items = []
            
            for it in fresh_items:
                vid = it.get('videoId')
                if not vid: continue
                if vid in seen_vids:
                    duplicates_to_remove.append(it)
                else:
                    seen_vids.add(vid)
                    final_items.append(it)
            
            dup_count = len(duplicates_to_remove)
            if duplicates_to_remove:
                print(f"  \033[91m⚠ Detected {len(duplicates_to_remove)} duplicate(s) in YouTube Music playlist.\033[0m")
                print(f"  🗑  Removing duplicates to match the 'Songs' sheet...")
                try:
                    self.yt.remove_playlist_items(pid, duplicates_to_remove)
                    print(f"  ✅ Successfully removed duplicates from YT.")
                except Exception as e:
                    print(f"  ✗ Error removing duplicates: {e}")
            
            yt_vid_map = {it['videoId']: it for it in final_items}
            existing_sheet = [s for s in all_songs if s.get('Playlist', '').lower() == pl_name.lower()]
            existing_vids = {s['Video ID']: s for s in existing_sheet if s.get('Video ID')}
            
            disliked_for_archive = []
            moved_for_sheet = []
            
            # ── 2b. PRE-FLIGHT: Enrich missing years in '#' (Inbox) ──
            if is_hash:
                songs_without_year = [
                    s for s in all_songs
                    if s.get('Playlist') == '#'
                    and not str(s.get('Year', '')).strip()
                    and s.get('Video ID')
                ]
                if songs_without_year:
                    print(f"  \033[93m⚠ {len(songs_without_year)} songs in Inbox '#' missing Year — enriching...\033[0m")
                    enriched_count = 0
                    for s in songs_without_year:
                        vid = s.get('Video ID')
                        y = self._fetch_song_year(vid, s.get('Title', ''), s.get('Artist', ''))
                        if y:
                            s['Year'] = y
                            # Also update the local map for the loop below
                            if vid in yt_vid_map:
                                yt_vid_map[vid]['year'] = y
                            if vid in existing_vids:
                                existing_vids[vid]['Year'] = y
                            print(f"    \033[92m✓\033[0m {s.get('Artist')} - {s.get('Title')} → {y}")
                            enriched_count += 1
                    if enriched_count > 0:
                        print(f"  ✓ Enriched {enriched_count} songs with years.")
            
            # Identify liked vids if hash
            liked_vids = set()
            if is_hash:
                try:
                    liked = self.yt.yt.get_liked_songs(limit=100)
                    liked_vids = {t['videoId'] for t in liked.get('tracks', []) if t.get('videoId')}
                except: pass

            # ── 2c. Last.fm Enrichment ──
            if not skip_lastfm:
                print(f"  \033[93m⌛ Fetching scrobbles from Last.fm for {len(fresh_items)} songs...\033[0m")
                # Add Artist/Title for enrich_songs compatibility
                for item in fresh_items:
                    art_list = item.get('artists', [])
                    item['Artist'] = art_list[0]['name'] if art_list else 'Unknown'
                    item['Title'] = item.get('title', 'Unknown')
                
                self.lastfm.enrich_songs(fresh_items, force_scrobbles=False)

            print(f"  Checking {len(fresh_items)} songs for likes/dislikes...")
            
            # Important: iterate over a copy or tracking list to handle removals
            for item in list(fresh_items):
                vid = item['videoId']
                status = item.get('likeStatus', 'INDIFFERENT')
                if is_hash and vid in liked_vids: status = 'LIKE'
                
                # Get current scrobbles for logic
                scrobbles = item.get('Scrobble', 0)
                if not scrobbles and vid in existing_vids:
                    try: scrobbles = int(existing_vids[vid].get('Scrobble', 0))
                    except: pass
                
                high_scrobbles = is_hash and scrobbles > Config.SCROBBLE_THRESHOLD
                
                if status == 'DISLIKE' or high_scrobbles:
                    reason = "Disliked" if status == 'DISLIKE' else "High scrobbles"
                    artists_str = ", ".join([a.get('name', '') for a in item.get('artists', [])])
                    print(f"    \033[91m✗ {reason} → Archiving:\033[0m \033[92m{artists_str} - {item.get('title')}\033[0m")
                    try:
                        self.yt.remove_playlist_items(pid, [item])
                        if status == 'DISLIKE': self.yt.rate_song(vid, 'INDIFFERENT')
                    except: pass
                    
                    # Use scrobbles from Last.fm if available, fallback to sheet
                    scrobble_val = item.get('Scrobble', 0)
                    lastfm_val = item.get('LastfmScrobble', 0)
                    genre_val = item.get('Genre', '')
                    if not scrobble_val and vid in existing_vids:
                        scrobble_val = existing_vids[vid].get('Scrobble', 0)
                    
                    row = dict(existing_vids.get(vid) or {
                        'Playlist': pl_name, 'Artist': item.get('Artist', ''),
                        'Title': item.get('title'), 'Album': item.get('album', {}).get('name', ''),
                        'Year': str(item.get('year', '')), 'Video ID': vid, 
                        'Scrobble': scrobble_val, 'LastfmScrobble': lastfm_val, 'Genre': genre_val
                    })
                    row['Scrobble'] = scrobble_val
                    row['LastfmScrobble'] = lastfm_val
                    if genre_val: row['Genre'] = genre_val
                    disliked_for_archive.append(row)
                    disliked_vids_global.add(vid)
                    if vid in yt_vid_map: del yt_vid_map[vid]
                    continue

            if is_hash and status == 'LIKE':
                artists_list = item.get('artists', [])
                main_artist = artists_list[0]['name'] if artists_list else 'Unknown'
                song_title = item.get('title', 'Unknown')
                
                # Look up target playlist in sheet
                artist_row = next((a for a in artists_records if self._normalize(a.get('Artist Name')) == self._normalize(main_artist)), None)
                target_pl = (artist_row.get('Playlist') or '').strip() if artist_row else ''
                
                actual_target_pl = ""
                
                if not target_pl:
                    print(f"    \033[93m❓ Artista '{main_artist}' sin playlist asignada.\033[0m")
                    print(f"      Canción: \033[92m{song_title}\033[0m")
                    res_pl = input(f"      ¿A qué playlist enviamos a \033[1m'{main_artist}'\033[0m? ").strip()
                    if res_pl:
                        actual_target_pl = res_pl
                        print(f"      ✅ Asignando '{res_pl}' como playlist por defecto para '{main_artist}'.")
                        self.sheets.update_artist_playlist(main_artist, res_pl)
                        if not artist_row:
                            artists_records.append({'Artist Name': main_artist, 'Playlist': res_pl})
                        else:
                            artist_row['Playlist'] = res_pl
                else:
                    print(f"    ♥ Liked → \033[92m{main_artist} - {song_title}\033[0m")
                    print(f"      Playlist actual del artista: \033[1;94m[{target_pl}]\033[0m")
                    
                    user_ans = input(f"      Enter para aceptar '{target_pl}' o escribe otra playlist: ").strip()
                    if user_ans:
                        actual_target_pl = user_ans
                        # Preguntamos si quiere cambiar el default permanentemente
                        change_def = input(f"      ¿Cambiar el destino POR DEFECTO de '{main_artist}' a '{user_ans}' para el futuro? (y/N): ").lower().strip()
                        if change_def == 'y':
                            self.sheets.update_artist_playlist(main_artist, user_ans)
                            if artist_row: artist_row['Playlist'] = user_ans
                            print(f"      ✅ Filtro de artista actualizado.")
                    else:
                        actual_target_pl = target_pl
                
                if actual_target_pl:
                    # ── Year check ───────────────────────
                    song_year = 0
                    y_str = (existing_vids.get(vid) or {}).get('Year') or item.get('year')
                    
                    if y_str:
                        match = re.search(r'(\d{4})', str(y_str))
                        if match: song_year = int(match.group(1))

                    # ── Archive routing check ──
                    final_target_pl = actual_target_pl
                    if actual_target_pl in Config.ARCHIVABLE_PLAYLISTS and song_year:
                        archive_name = f"{actual_target_pl} $"
                        archive_threshold = self._get_archive_threshold(archive_name)
                        if archive_threshold and song_year <= archive_threshold:
                            final_target_pl = archive_name
                            print(f"    \033[93m📦 Año {song_year} ≤ {archive_threshold} → redirigiendo a '{archive_name}'\033[0m")

                    # ── Final Unliking Logic ──
                    if final_target_pl.endswith('$'):
                        print(f"    \033[93m⚠ Archivo catalogado → Quitando Like:\033[0m \033[92m{main_artist} - {song_title}\033[0m")
                        try:
                            self.yt.rate_song(vid, 'INDIFFERENT')
                        except: pass

                    print(f"    🚀 Moviendo a \033[1;94m[{final_target_pl}]\033[0m")
                    target_pid = self._resolve_playlist_id(final_target_pl)
                    if target_pid:
                        try:
                            self.yt.add_playlist_items(target_pid, [vid])
                            self.yt.remove_playlist_items(pid, [item])
                            
                            # Use Last.fm values for record
                            sc_val = item.get('Scrobble', 0)
                            lsc_val = item.get('LastfmScrobble', 0)
                            gen_val = item.get('Genre', '')
                            if not sc_val and vid in existing_vids:
                                sc_val = existing_vids[vid].get('Scrobble', 0)

                            new_record = dict(existing_vids.get(vid) or {
                                'Playlist': final_target_pl, 'Artist': main_artist,
                                'Title': item.get('title'), 'Album': item.get('album', {}).get('name', ''),
                                'Year': str(y_str or ''), 'Video ID': vid, 'Scrobble': sc_val,
                                'LastfmScrobble': lsc_val, 'Genre': gen_val
                            })
                            new_record['Year'] = str(y_str or '')
                            new_record['Playlist'] = final_target_pl
                            new_record['Scrobble'] = sc_val
                            new_record['LastfmScrobble'] = lsc_val
                            if gen_val: new_record['Genre'] = gen_val
                            moved_for_sheet.append(new_record)

                            if vid in yt_vid_map: del yt_vid_map[vid]
                            continue
                        except Exception as e:
                            print(f"      ✗ Error moviendo canción: {e}")
                    else:
                        print(f"      ⚠ No se pudo encontrar el ID de la playlist '{final_target_pl}'")
                continue

            # Reconciliation Authority: YOUTUBE IS ALWAYS THE AUTHORITY.
            yt_vids = set(yt_vid_map.keys())
            
            # 3a. Songs in YT but NOT in Sheet → add to Sheet
            new_vids = yt_vids - set(existing_vids.keys())
            new_songs = []
            if new_vids:
                print(f"  Found {len(new_vids)} new songs (on YT but missing from Sheet) to add...")
                for vid in new_vids:
                    item = yt_vid_map[vid]
                    artist_str = ", ".join([a.get('name', '') for a in item.get('artists', [])])
                    album_info = item.get('album')
                    album_name = album_info.get('name', '') if album_info else ''
                    # Use year from YT item; if missing, fetch via API
                    year = str(item.get('year') or '')
                    if not year:
                        year = self._fetch_song_year(vid, item.get('title', ''), artist_str)
                    new_songs.append({
                        'Playlist': pl_name,
                        'Artist': artist_str,
                        'Title': item.get('title', ''),
                        'Album': album_name,
                        'Year': year,
                        'Genre': item.get('Genre', ''),
                        'Scrobble': item.get('Scrobble', 0),
                        'LastfmScrobble': item.get('LastfmScrobble', 0),
                        'Video ID': vid
                    })

            # 3b. Songs in Sheet but NOT in YT → ARCHIVE (YouTube is the authority)
            # Exclude those already processed as disliked AND those moved to other playlists
            moved_vids = {s['Video ID'] for s in moved_for_sheet if s.get('Video ID')}
            to_archive_vids = set(existing_vids.keys()) - yt_vids - disliked_vids_global - moved_vids
            archived_songs = []
            if to_archive_vids:
                print(f"  Found {len(to_archive_vids)} songs to archive (missing from YouTube)...")
                for vid in to_archive_vids:
                    s = existing_vids[vid]
                    print(f"    \033[91m→ Archiving:\033[0m \033[90m{s.get('Artist')} - {s.get('Title')}\033[0m")
                    archived_songs.append(s)

            # Songs that stay: those in YT that were already in the Sheet
            kept_songs = []
            songs_needing_search_year = []
            for vid, s in existing_vids.items():
                if vid in yt_vid_map:
                    # Enrich the sheet record with data fetched in step 2c
                    yt_item = yt_vid_map[vid]
                    if 'Scrobble' in yt_item: s['Scrobble'] = yt_item['Scrobble']
                    if 'LastfmScrobble' in yt_item: s['LastfmScrobble'] = yt_item['LastfmScrobble']
                    if yt_item.get('Genre') and not s.get('Genre'): s['Genre'] = yt_item['Genre']
                    # Only fetch year from YT if it's missing in the sheet
                    if not str(s.get('Year', '')).strip():
                        alb_id = (yt_item.get('album') or {}).get('id')
                        if alb_id:
                            try:
                                alb_data = self.yt.yt.get_album(alb_id)
                                alb_yr = alb_data.get('year')
                                if alb_yr and str(alb_yr).isdigit() and int(alb_yr) <= 2026:
                                    s['Year'] = str(alb_yr)
                            except: pass
                        else:
                            # No album ID in playlist data → queue for full search
                            songs_needing_search_year.append((vid, s))
                    kept_songs.append(s)

            # For songs without album ID, fetch year via search (slower, only when needed)
            if songs_needing_search_year:
                print(f"  Fetching year for {len(songs_needing_search_year)} songs without album metadata...")
                for vid, s in songs_needing_search_year:
                    yr = self._fetch_song_year(vid, s.get('Title', ''), s.get('Artist', ''))
                    if yr:
                        s['Year'] = yr
                        print(f"    \033[90m📅 {s.get('Artist')} - {s.get('Title')} → {yr}\033[0m")

            # Final list for this playlist: kept + new additions from YT
            playlist_songs = kept_songs + new_songs

            # ── 5. Update global list ──
            # 1. Remove this playlist's current entries from the global master list
            all_songs = [s for s in all_songs if s.get('Playlist', '').lower() != pl_name.lower()]
            
            # 2. Prevent duplicates in other playlists only if they are from Inbox or this playlist
            # We avoid touching other catalog playlists to follow user's rule.
            vids_in_this_pl = {s['Video ID'] for s in playlist_songs if s.get('Video ID')}
            vids_moved = {s['Video ID'] for s in moved_for_sheet if s.get('Video ID')}
            vids_to_clean = vids_in_this_pl | vids_moved
            all_songs = [s for s in all_songs if s.get('Video ID') not in vids_to_clean or (s.get('Playlist') != '#' and s.get('Playlist').lower() != pl_name.lower())]

            # 3. Add the reconciled songs and moved songs
            all_songs.extend(playlist_songs)
            all_songs.extend(moved_for_sheet)

            # 4. Double-check: ensure NO disliked or about-to-be-archived vids remain in this playlist (or Inbox)
            vids_to_remove = disliked_vids_global | to_archive_vids
            all_songs = [s for s in all_songs if s.get('Video ID') not in vids_to_remove or (s.get('Playlist') != '#' and s.get('Playlist').lower() != pl_name.lower())]
            
            # ── 6. Batch archive to sheet ──
            final_archived_batch = disliked_for_archive + archived_songs
            if final_archived_batch:
                print(f"  Archiving {len(final_archived_batch)} songs to 'Archived' sheet...")
                self.sheets.add_to_archived_batch(final_archived_batch)

            # Summary counts for user verification
            # moved_away contains songs that were shifted to ANOTHER playlist (from Inbox)
            moved_away = len([m for m in moved_for_sheet if m.get('Video ID') and m.get('Playlist') != pl_name])
            yt_final_count = len(yt_vid_map) - len(disliked_for_archive) - moved_away
            sheet_final_count = len(playlist_songs)
            
            status_char = "✅" if yt_final_count == sheet_final_count else "⚠"
            dup_msg = f" (Dup YT: {dup_count})" if dup_count > 0 else ""
            print(f"  {status_char} Playlist '{pl_name}' synced. [YT: {yt_final_count} | Sheet: {sheet_final_count}]{dup_msg}")
            print(f"    (Kept: {len(kept_songs)}, Added: {len(new_songs)}, Archived: {len(disliked_for_archive) + len(archived_songs)})")

        # ── 7. Write back entire Songs sheet ──
        print("\nSaving Songs sheet...")
        self.sheets.overwrite_songs(all_songs)

        print("✅ Sync complete.")

    def add_artist(self, name, target_playlist=None, api_choice="lastfm"):
        print(f"\n\033[90m🔎 Searching for artist:\033[0m \033[1;93m'{name}'\033[0m...")
        results = self.yt.yt.search(name, filter='artists')
        if not results:
            print("\033[91m✗ Artist not found on YouTube Music.\033[0m")
            return "not_found", {}
        
        best = results[0]
        artist_name = best['artist']
        artist_id = best['browseId']
        
        artists = self.sheets.get_artists()
        for a in artists:
            if a.get('Artist ID') == artist_id:
                return "exists", a
        
        # Determine metadata service for genre fetching
        meta_service = self.musicbrainz if api_choice == "musicbrainz" else self.lastfm
        artist_info = meta_service.get_artist_info(artist_name, cache_ttl_days=-1)
        genre = artist_info.get('genre', "") if artist_info else ""
        
        new_row = {
            'Artist Name': artist_name,
            'Artist ID': artist_id,
            'Song Count': 0,
            'Last Checked': "",
            'Status': 'Pending',
            'Genre': genre,
            'Playlist': target_playlist or ""
        }
        
        self.sheets.add_artist(new_row)
        
        print(f"✅ Artist '{artist_name}' added to tracking list (Genre: {genre or '?'}).")
        print(f"🔍 Running initial song discovery for '{artist_name}'...")
        
        # Initial sync to populate the Inbox (#) right away
        self.check_new_releases(
            Config.PLAYLIST_ID, 
            force=True, 
            target_artist_name=artist_name, 
            target_artist_id=artist_id
        )
        
        return "added", new_row

    def remove_artist(self, name):
        norm = self._normalize(name)
        artists = self.sheets.get_artists()
        found = False
        for a in artists:
            if self._normalize(a.get('Artist Name')) == norm:
                a['Status'] = 'Archived'
                # Clear tracking data for archived artists
                a['Last Checked'] = ""
                a['Playlist'] = ""
                found = True
                break
        
        if found:
            self.sheets.save_artists(artists)
            print(f"✅ Artist \033[1m'{name}'\033[0m has been marked as \033[91mArchived\033[0m.")
            print("   (It will no longer be included in sync operations).")
        else:
            print(f"\033[91m✗ Artist '{name}' not found in tracking list.\033[0m")

    def list_artists(self):
        artists = self.sheets.get_artists()
        print("\n\033[96m" + "━"*50 + "\033[0m")
        print(f"\033[1;96m🎤 Tracked Artists ({len(artists)})\033[0m")
        print("\033[96m" + "━"*50 + "\033[0m")
        for a in artists:
            status = a.get('Status', 'Pending')
            color = "\033[92m" if status == 'Done' else "\033[93m"
            print(f" \033[90m•\033[0m \033[1m{a.get('Artist Name'):<30}\033[0m {color}[{status}]\033[0m")
        print("\033[96m" + "━"*50 + "\033[0m")

    def check_new_releases(self, playlist_id, force=False, target_artist_name=None, target_artist_id=None, clear_empty=False, interactive=False):
        """Revisa la discografía del artista en YouTube y añade las canciones limitadas a MAX_NEW_RELEASE_SONGS."""
        if not target_artist_name:
            print("Se requiere el nombre del artista.")
            return 0

        artist_id = target_artist_id
        if not artist_id:
            results = self.yt.yt.search(target_artist_name, filter='artists')
            if not results:
                print(f"  \033[91m✗ No se encontró a {target_artist_name} en YT.\033[0m")
                return 0
            
            # Intentamos buscar el Artist ID exacto si lo conocemos (pero aquí no lo tenemos si entramos aquí)
            artist_id = results[0]['browseId']
            
        try:
            artist_data = self.yt.yt.get_artist(artist_id)
        except Exception as e:
            print(f"  ✗ Error obteniendo datos del artista: {e}")
            return 0
            
        albums = artist_data.get('albums', {}).get('results', [])
        singles = artist_data.get('singles', {}).get('results', [])
        
        releases = albums + singles
        if not releases:
            print(f"  ✗ Sin lanzamientos para {target_artist_name}.")
            return 0
            
        existing_vids = self.sheets.get_all_video_ids()

        # OBTENEMOS TODAS LAS CANCIONES (Songs + Archived) PARA CONTROLAR DUPLICADOS DE TÍTULO+ARTISTA
        # Esto soluciona el problema de mayúsculas Ekkstacy == EKKSTACY y evita
        # añadir una canción si era disco y ahora single o si ya la descartamos antes.
        existing_keys = set()
        for r in self.sheets.get_songs_records() + self.sheets.get_archived_records():
            art = self._normalize(r.get('Artist', ''))
            tit = self._normalize(r.get('Title', ''))
            existing_keys.add(f"{art} - {tit}")

        # También añadimos los Video IDs de Archived a la lista de exclusión
        existing_vids.update(self.sheets.get_archived_vids())

        max_songs = Config.MAX_NEW_RELEASE_SONGS
        
        now = datetime.now()
        limit_year = now.year - Config.MAX_NEW_RELEASE_YEARS
        
        new_batch = []
        
        import re

        catalog_candidates = []
        for release in releases:
            title = release.get('title')
            browse_id = release.get('browseId')
            if not browse_id: continue
            
            try:
                album_info = self.yt.yt.get_album(browse_id)
            except Exception:
                continue
                
            album_year_str = str(album_info.get('year', ''))
            
            is_recent = False
            match = re.search(r'(\d{4})', album_year_str)
            if match:
                release_year = int(match.group(1))
                if release_year >= limit_year:
                    is_recent = True

            tracks = album_info.get('tracks', [])
            
            missing_tracks = []
            for track in tracks:
                vid = track.get('videoId')
                track_title = track.get('title', '')
                
                
                track_artists = [a.get('name', '') for a in track.get('artists', [])]
                
                # Para colaboraciones, si no está nuestro artista, saltamos
                if target_artist_name.lower() not in [a.lower() for a in track_artists]:
                    continue
                
                # REGLA DE PLATA: No queremos REMIXES de ningún tipo
                if 'remix' in track_title.lower():
                    continue
                
                # Normalizamos ambos nombres para hacer match insensible a mayúsculas
                norm_artist = self._normalize(target_artist_name)
                norm_title = self._normalize(track_title)
                track_key = f"{norm_artist} - {norm_title}"
                
                # Omitimos si ya tenemos el Video ID o el binomio Título-Artista exacto
                if vid and vid not in existing_vids and track_key not in existing_keys:
                    track['AlbumTitle'] = title
                    track['AlbumYear'] = album_year_str
                    missing_tracks.append(track)
            
            if not is_recent:
                # Si es un álbum antiguo, guardamos sus canciones posibles para un segundo pase de "catálogo"
                # Solo cogemos las primeras canciones (potenciales singles) para no saturar
                catalog_candidates.extend(missing_tracks[:2])
                continue

            if not missing_tracks:
                continue # Ya tenemos todas las canciones de este lanzamiento reciente
                
            # Limitamos a los MAX_NEW_RELEASE_SONGS (ej: los 3 primeros hits nuevos)
            top_missing_tracks = missing_tracks[:max_songs]

            # Registrar en existing_keys al momento para que si sale luego como single, no pregunte sea cual sea la decisión
            for t in top_missing_tracks:
                norm_title = self._normalize(t.get('title', ''))
                norm_artist = self._normalize(target_artist_name)
                existing_keys.add(f"{norm_artist} - {norm_title}")
                # Preparamos los campos que LastFMService espera leer
                t['Artist'] = target_artist_name
                t['Title'] = t.get('title', '')

            # Pre-enriquecemos los datos de Last.fm SOLO de estas canciones nuevas
            # para mostrar las reproducciones en el prompt
            print(f"    🔎 Buscando popularidad en Last.fm para {len(top_missing_tracks)} canciones...")
            self.lastfm.enrich_songs(top_missing_tracks, force_scrobbles=False)

            if interactive:
                # Ordenar por popularidad (oyentes en Last.fm) de mayor a menor
                top_missing_tracks = sorted(top_missing_tracks, key=lambda x: int(x.get('LastfmScrobble', 0)), reverse=True)
                
                print(f"    \033[95m📀 Lanzamiento reciente ({album_year_str}):\033[0m \033[1m'{title}'\033[0m")
                to_add_this_release = []
                for t in top_missing_tracks:
                    listeners = int(t.get('LastfmScrobble', 0))
                    listeners_fmt = f"{listeners:,}".replace(",", ".")
                    ans = input(f"      - \033[92m'{t.get('title')}'\033[0m \033[90m[{listeners_fmt}🎧]\033[0m. ¿Añadir? [S/n/q]: ").strip().lower()
                    if ans == 'q':
                        return -1
                    if ans != 'n':
                        to_add_this_release.append(t)
                
                if not to_add_this_release:
                    continue
                
                # Añadimos las confirmadas al lote general
                for track in to_add_this_release:
                    vid = track.get('videoId')
                    year_val = str(album_info.get('year') or '')
                    if not year_val and vid:
                        year_val = self._fetch_song_year(vid, track.get('title', ''), target_artist_name)
                    new_song = {
                        'Playlist': '#',
                        'Artist': target_artist_name,
                        'Title': track.get('title', ''),
                        'Album': title,
                        'Year': year_val,
                        'Genre': track.get('Genre', ''),
                        'Scrobble': track.get('Scrobble', 0),
                        'LastfmScrobble': track.get('LastfmScrobble', 0),
                        'Video ID': vid
                    }
                    new_batch.append(new_song)
                    existing_vids.add(vid)
            else:
                print(f"    \033[90m+ Analizando lanzamiento: '{title}' ({album_year_str}). Extraídas {len(top_missing_tracks)} pistas...\033[0m")
                for track in top_missing_tracks:
                    vid = track.get('videoId')
                    year_val = str(album_info.get('year') or '')
                    if not year_val and vid:
                        year_val = self._fetch_song_year(vid, track.get('title', ''), target_artist_name)
                    new_song = {
                        'Playlist': '#',
                        'Artist': target_artist_name,
                        'Title': track.get('title', ''),
                        'Album': title,
                        'Year': year_val,
                        'Genre': track.get('Genre', ''),
                        'Scrobble': track.get('Scrobble', 0),
                        'LastfmScrobble': track.get('LastfmScrobble', 0),
                        'Video ID': vid
                    }
                    new_batch.append(new_song)
                    existing_vids.add(vid)

        # SEGUNDO PASE: Sugerimos las mejores del catálogo histórico si estamos en modo interactivo
        if interactive and catalog_candidates:
            if not new_batch:
                prompt_msg = f"    ⚠ Sin novedades recientes. ¿Revisar las 3 más populares del catálogo antiguo? [s/N/q]: "
            else:
                prompt_msg = f"    ✨ ¿Revisar también las 3 más populares del catálogo antiguo? [s/N/q]: "

            ans = input(prompt_msg).strip().lower()
            if ans == 'q':
                return -1
            if ans == 's':
                # DEDUPLICADO: Evitar que la misma canción aparezca varias veces por estar en distintos álbumes/singles
                unique_catalog = {}
                for t in catalog_candidates:
                    t['Artist'] = target_artist_name
                    t['Title'] = t.get('title', '')
                    key = f"{self._normalize(target_artist_name)} - {self._normalize(t['Title'])}"
                    if key not in unique_catalog:
                        unique_catalog[key] = t
                
                deduped_candidates = list(unique_catalog.values())
                
                print(f"    🔎 Analizando popularidad del catálogo ({len(deduped_candidates)} candidatos)...")
                self.lastfm.enrich_songs(deduped_candidates, force_scrobbles=False)
                
                # Ordenar por oyentes y coger los 3 mejores
                top_catalog = sorted(deduped_candidates, key=lambda x: int(x.get('LastfmScrobble', 0)), reverse=True)[:3]
                
                print(f"    \033[95m📜 Joyas del catálogo antiguo:\033[0m")
                for t in top_catalog:
                    listeners = int(t.get('LastfmScrobble', 0))
                    listeners_fmt = f"{listeners:,}".replace(",", ".")
                    ans = input(f"      - \033[92m'{t.get('title')}'\033[0m ({t.get('AlbumYear')}) \033[90m[{listeners_fmt}🎧]\033[0m. ¿Añadir? [S/n/q]: ").strip().lower()
                    if ans == 'q':
                        return -1
                    if ans != 'n':
                        vid = t.get('videoId')
                        year_val = str(t.get('AlbumYear') or '')
                        if not year_val and vid:
                            year_val = self._fetch_song_year(vid, t.get('title', ''), target_artist_name)
                        new_song = {
                            'Playlist': '#',
                            'Artist': target_artist_name,
                            'Title': t.get('title', ''),
                            'Album': t.get('AlbumTitle', ''),
                            'Year': year_val,
                            'Genre': t.get('Genre', ''),
                            'Scrobble': t.get('Scrobble', 0),
                            'LastfmScrobble': listeners,
                            'Video ID': vid
                        }
                        new_batch.append(new_song)
                        existing_vids.add(vid)
                    
        if new_batch:
            # Quitamos el enrich_songs de aquí porque ya lo hemos hecho arriba canción por canción
            print(f"  Añadiendo {len(new_batch)} canciones a tu playlist Inbox '#' en YouTube Music...")
            try:
                self.yt.add_playlist_items(playlist_id, [s['Video ID'] for s in new_batch])
            except Exception as e:
                print(f"  ✗ Error añadiendo a la playlist: {e}")
                
            print(f"  Guardando {len(new_batch)} canciones en el Excel...")
            self.sheets.add_to_songs_batch(new_batch)
            return len(new_batch)
        else:
            print("  Ninguna canción destacada o nueva que añadir para este artista.")
            return 0



    def sync_new_releases(self, interactive=True):
        """Simula una sincronización general delegando en deep_sync."""
        self.deep_sync_all_artists(interactive=interactive)

    def _load_deep_sync_cache(self):
        try:
            if os.path.exists(Config.DEEP_SYNC_CACHE_FILE):
                with open(Config.DEEP_SYNC_CACHE_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _save_deep_sync_cache(self, cache):
        try:
            os.makedirs(os.path.dirname(Config.DEEP_SYNC_CACHE_FILE), exist_ok=True)
            with open(Config.DEEP_SYNC_CACHE_FILE, 'w') as f:
                json.dump(cache, f, indent=4)
        except Exception:
            pass

    def deep_sync_all_artists(self, interactive=True):
        print("\n" + "="*50)
        print("🚀 STARTING DEEP SYNC FOR PENDING ARTISTS")
        print("="*50)
        
        artists = self.sheets.get_artists()
        if not artists:
            print("No artists found in the sheet.")
            return

        songs = self.sheets.get_songs_records()
        cache = self._load_deep_sync_cache()
        now = datetime.now()

        to_sync = []
        for a in artists:
            name = a.get("Artist Name", "")
            status = a.get("Status", "")
            last_checked = str(a.get("Last Checked", "")).strip()
            norm_name = self._normalize(name)
            
            # Filtros de Sincronización PROFUNDA:
            # 1. Saltamos siempre los 'Archived' (archivados manualmente por el usuario)
            if status == "Archived":
                continue
            
            # 2. Decidimos si por el estado del Excel debe entrar en la lista
            should_sync = False
            if status == "Pending" or not last_checked:
                should_sync = True
            elif status == "Done":
                # Si está 'Done', miramos la fecha del último escaneo
                last_date = None
                try:
                    # Formato estándar DD/MM/YYYY
                    last_date = datetime.strptime(last_checked, "%d/%m/%Y")
                except ValueError:
                    try:
                        # Fallback: formato ISO (por si hay alguna fecha antigua mal guardada)
                        last_date = datetime.fromisoformat(last_checked)
                    except ValueError:
                        pass
                
                if last_date is None:
                    # Fecha ilegible → incluimos para no perder artistas
                    should_sync = True
                elif (now - last_date).days >= 30:
                    # Ha pasado más de un mes → re-escaneamos
                    should_sync = True
            
            if not should_sync:
                continue

            # 3. Filtro de Caché Local (protección contra ráfagas si has borrado/limpiado el Excel)
            cached_date = cache.get(norm_name)
            if cached_date:
                try:
                    d = datetime.fromisoformat(cached_date)
                    if (now - d).days < Config.DEEP_SYNC_CACHE_DAYS:
                        continue # Saltamos en silencio
                except:
                    pass
            
            to_sync.append(a)
                
        if not to_sync:
            # Fallback: Seek Archived artists if they haven't been checked in 30 days or empty
            archived_fallback = []
            for a in artists:
                if a.get("Status", "") == "Archived":
                    last_checked = str(a.get("Last Checked", "")).strip()
                    should_sync_archived = False
                    if not last_checked:
                        should_sync_archived = True
                    else:
                        last_date = None
                        try:
                            last_date = datetime.strptime(last_checked, "%d/%m/%Y")
                        except ValueError:
                            try: last_date = datetime.fromisoformat(last_checked)
                            except ValueError: pass
                        if last_date is None or (now - last_date).days >= 30:
                            should_sync_archived = True
                    
                    if should_sync_archived:
                        norm_name = self._normalize(a.get("Artist Name", ""))
                        cached_date = cache.get(norm_name)
                        if cached_date:
                            try:
                                d = datetime.fromisoformat(cached_date)
                                if (now - d).days < Config.DEEP_SYNC_CACHE_DAYS:
                                    should_sync_archived = False
                            except: pass
                        
                        if should_sync_archived:
                            archived_fallback.append(a)

            if archived_fallback:
                print("Todos los artistas pendientes y actualizados están al día.")
                print("🔄 Iniciando pasada de re-evaluación para Artistas Archivados...")
                to_sync = archived_fallback
            else:
                print("Todos los artistas (incluidos los archivados) están al día o en la caché de enfriamiento. ¡Nada que sincronizar!")
                return

            
        print(f"Encontrados {len(to_sync)} artistas pendientes de exploración profunda.")
        
        for idx, artist in enumerate(to_sync, start=1):
            res = self._process_deep_sync_artist_entry(artist, songs, cache, interactive, idx, len(to_sync))
            if res == "quit":
                print("\n🛑 Sincronización profunda interrumpida. Puedes continuar otro día.")
                break
            
            if not interactive and idx < len(to_sync):
                print(f"  Esperando {Config.SYNC_DELAY}s para la siguiente consulta de la API...")
                time.sleep(Config.SYNC_DELAY)

        print("\n✅ Deep Sync Completado.")

    def deep_sync_single_artist(self, artist_name):
        """Runs the deep sync interactive logic for a single artist name."""
        artists = self.sheets.get_artists()
        artist_row = next((a for a in artists if self._normalize(a.get('Artist Name')) == self._normalize(artist_name)), None)
        if not artist_row:
            print(f"\033[91m✗ Artist '{artist_name}' not found in tracking list.\033[0m")
            return
            
        songs = self.sheets.get_songs_records()
        cache = self._load_deep_sync_cache()
        
        self._process_deep_sync_artist_entry(artist_row, songs, cache, True, 1, 1)
        print("\n✅ Exploración de artista completada.")

    def _process_deep_sync_artist_entry(self, artist, songs, cache, interactive, idx, total):
        name = artist.get("Artist Name", "")
        norm_name = self._normalize(name)
        
        print(f"\n\033[96m" + "━"*50 + "\033[0m")
        print(f"\033[1m[{idx}/{total}] Revisando a:\033[0m \033[93m{name}\033[0m")
        
        if interactive:
            # Localizamos y mostramos las canciones actuales de este artista en la biblioteca
            tracked_artists = {self._normalize(a.get("Artist Name", "")) for a in self.sheets.get_artists()}
            
            def song_has_artist(song, target_norm_name):
                field = str(song.get("Artist", "")).strip()
                norm_field = self._normalize(field)
                if norm_field == target_norm_name:
                    return True
                if norm_field in tracked_artists:
                    # Entidad de otro artista distinto que seguimos (ej: 'hey, nothing' vs 'nothing')
                    return False
                # Fallback: separador oficial
                return target_norm_name in [self._normalize(part) for part in field.split(', ')]

            artist_songs = [s for s in songs if song_has_artist(s, norm_name)]
            if artist_songs:
                artist_songs_sorted = sorted(artist_songs, key=lambda x: int(x.get("LastfmScrobble") or 0), reverse=True)
                print(f"\n  \033[94m🎵 Biblioteca Actual ({len(artist_songs)}):\033[0m")
                for s in artist_songs_sorted:
                    s_title = s.get("Title", "")
                    s_scrobble = int(s.get("LastfmScrobble") or 0)
                    s_scrobble_fmt = f"{s_scrobble:,}".replace(",", ".")
                    s_pl = s.get("Playlist", "")
                    s_year = s.get("Year", "")
                    year_str = f" {s_year}" if s_year else ""
                    print(f"    - \033[92m{s_title}\033[0m\033[90m{year_str} [{s_scrobble_fmt}🎧]\033[0m \033[35m[{s_pl}]\033[0m")
                print()
            else:
                print(f"\n  \033[90m[✕ Biblioteca Actual: 0 canciones]\033[0m\n")
        
        artist_id = artist.get("Artist ID", "")
        added_songs = self.check_new_releases(Config.PLAYLIST_ID, force=True, target_artist_name=name, target_artist_id=artist_id, interactive=interactive)
        
        # Almacenamos en caché local DE INMEDIATO
        check_time = datetime.now()
        cache[norm_name] = check_time.isoformat()
        self._save_deep_sync_cache(cache)

        if added_songs == -1: # User Quit inside
            return "quit"

        # ── 3. Acciones Finales e Interacción ──
        
        # En modo no interactivo, actualizamos automáticamente según si hubo canciones o no
        if not interactive:
            self.sheets.update_artist_last_checked(name, check_time.strftime("%d/%m/%Y"))
            self.sheets.update_artist_status(name, "Done")
            return "completed"

        # Modo interactivo: informamos al usuario y actualizamos el Sheet ANTES de preguntar por 'quit'
        # para que los artistas queden marcados como procesados aunque se salga.
        # Actualizamos el Sheet SIEMPRE (haya o no canciones nuevas)
        is_archived = artist.get("Status", "") == "Archived"
        # Actualizamos el Sheet SIEMPRE (haya o no canciones nuevas)
        self.sheets.update_artist_last_checked(name, check_time.strftime("%d/%m/%Y"))
        
        if not is_archived:
            self.sheets.update_artist_status(name, "Done")
        else:
            # Si era un artista archivado, le preguntamos si quiere reactivarlo
            print(f"\n  \033[93m💡 Este artista estaba 'Archived'.\033[0m")
            reactivate = input(f"  ¿Quieres cambiar su estado a 'Done' para que salga en futuros syncs normales? [y/N]: ").strip().lower()
            if reactivate == 'y':
                print(f"  \033[92m✓ Artista reactivado como 'Done'.\033[0m")
                self.sheets.update_artist_status(name, "Done")
            else:
                print(f"  \033[90m• Se mantiene como 'Archived'.\033[0m")

        while True:
            ans = input(f"\n  \033[1;93m🎯 Artista completado. ¿Siguiente paso?\033[0m (\033[92m[C]ontinuar\033[0m | \033[91m[a]rchivar\033[0m | [q]uit): ").strip().lower()
            if not ans: ans = 'c'
            if ans in ['c', 'a', 'q']: break
            print("  Por favor responde con c, a, o q.")
        
        if ans == 'q':
            return "quit"
        elif ans == 'a':
            print(f"  \033[91mArchivando artista:\033[0m \033[1m{name}\033[0m")
            self.sheets.update_artist_status(name, "Archived")
            self.sheets.update_artist_last_checked(name, check_time.strftime("%d/%m/%Y"))
            return "archived"
        
        return "completed"

    def archive_playlist_by_year(self, playlist_name=None, year=None):
        """Archive songs from large playlists into '$' playlists based on year.
        
        Songs with Year <= year are moved from the original playlist to the 
        archive playlist (same name + ' $'). Creates the archive playlist in 
        YouTube Music if it doesn't exist.

        Pre-flight: any songs with no Year are enriched via YouTube Music API
        and saved to the Sheet before the archiving logic runs.
        """
        print("\n\033[96m" + "━"*50 + "\033[0m")
        print(f"\033[1;96m📦 ARCHIVING SONGS ≤ {year}\033[0m")
        print("\033[96m" + "━"*50 + "\033[0m")

        if playlist_name:
            if playlist_name not in Config.ARCHIVABLE_PLAYLISTS:
                print(f"\033[91m✗ '{playlist_name}' no es una playlist archivable.\033[0m")
                print(f"  Playlists válidas: {', '.join(Config.ARCHIVABLE_PLAYLISTS)}")
                return
            playlists_to_process = [playlist_name]
        else:
            playlists_to_process = Config.ARCHIVABLE_PLAYLISTS

        # 1. Read all songs from the Sheet
        all_songs = self.sheets.get_songs_records()

        # ── PRE-FLIGHT: Enrich missing years ────────────────────────────────
        target_pl_lower = {p.lower() for p in playlists_to_process}
        songs_without_year = [
            s for s in all_songs
            if s.get('Playlist', '').lower() in target_pl_lower
            and not str(s.get('Year', '')).strip()
            and s.get('Video ID')
        ]

        if songs_without_year:
            print(f"\n\033[93m⚠  {len(songs_without_year)} canciones sin año — buscando en YouTube Music...\033[0m")
            enriched = 0
            sheet_year_changed = False

            for s in songs_without_year:
                vid = s.get('Video ID')
                title = s.get('Title', vid)
                artist = s.get('Artist', '')
                
                fetched_year = self._fetch_song_year(vid, title, artist)

                if fetched_year:
                    s['Year'] = fetched_year
                    print(f"    \033[92m✓\033[0m \033[90m{artist} - {title}\033[0m → \033[1m{fetched_year}\033[0m")
                    enriched += 1
                    sheet_year_changed = True
                else:
                    print(f"    \033[91m✗\033[0m Sin año: \033[90m{artist} - {title}\033[0m (Video ID: {vid})")

            if sheet_year_changed:
                print(f"\n  📝 Guardando {enriched} años nuevos en el Sheet...")
                self.sheets.overwrite_songs(all_songs)
                print(f"  \033[92m✓ Sheet actualizado con años.\033[0m")
        else:
            print("\n  \033[92m✓ Todas las canciones tienen año.\033[0m")

        # 2. Resolve YouTube playlist IDs
        print("\n  Resolviendo IDs de playlists en YouTube Music...")
        resolved_ids = {}
        try:
            library_playlists = self.yt.yt.get_library_playlists(limit=100)
        except Exception as e:
            print(f"\033[91m✗ Error obteniendo playlists de la biblioteca: {e}\033[0m")
            return

        for lp in library_playlists:
            lp_title = lp.get('title', '')
            pid = lp.get('playlistId', '')
            if lp_title and pid:
                resolved_ids[lp_title.lower()] = pid

        total_moved = 0

        for pl_name in playlists_to_process:
            archive_name = f"{pl_name} $"
            pl_lower = pl_name.lower()
            archive_lower = archive_name.lower()

            original_pid = resolved_ids.get(pl_lower)
            if not original_pid:
                print(f"\n  \033[91m✗ No se encontró la playlist '{pl_name}' en YouTube Music.\033[0m")
                continue

            # Filter songs: same playlist + year <= threshold
            candidates = []
            skipped_no_year = []
            for s in all_songs:
                if s.get('Playlist', '').lower() != pl_lower:
                    continue
                song_year = str(s.get('Year', '')).strip()
                if not song_year:
                    skipped_no_year.append(s)
                    continue
                try:
                    if int(song_year) <= year:
                        candidates.append(s)
                except (ValueError, TypeError):
                    skipped_no_year.append(s)

            if skipped_no_year:
                print(f"\n  \033[93m⚠  {len(skipped_no_year)} canciones siguen sin año (ignoradas) en '{pl_name}':\033[0m")
                for s in skipped_no_year:
                    print(f"    \033[90m{s.get('Artist', '')} - {s.get('Title', '')}\033[0m")

            if not candidates:
                print(f"\n  \033[90m⏭ '{pl_name}': Sin canciones con año ≤ {year}.\033[0m")
                continue

            candidates.sort(key=lambda x: int(x.get('Year', 0)))

            print(f"\n\033[96m{'━'*50}\033[0m")
            print(f"  \033[1;95m📂 {pl_name}\033[0m → \033[1;93m{archive_name}\033[0m")
            print(f"  \033[90m{len(candidates)} canciones con año ≤ {year}:\033[0m")
            for s in candidates:
                print(f"    \033[92m{s.get('Artist', '')}\033[0m - {s.get('Title', '')} \033[90m({s.get('Year', '')})\033[0m")

            ans = input(f"\n  ¿Mover estas {len(candidates)} canciones a '{archive_name}'? [\033[92mS\033[0m/n]: ").strip().lower()
            if ans == 'n':
                print(f"  ⏭ Saltada.")
                continue

            # Find or create archive playlist
            archive_pid = resolved_ids.get(archive_lower)
            if not archive_pid:
                print(f"  📝 Creando playlist '{archive_name}' en YouTube Music...")
                try:
                    archive_pid = self.yt.create_playlist(archive_name, f"Archivo: canciones ≤ {year}")
                    resolved_ids[archive_lower] = archive_pid
                    print(f"  \033[92m✓ Playlist '{archive_name}' creada.\033[0m")
                except Exception as e:
                    print(f"  \033[91m✗ Error creando playlist: {e}\033[0m")
                    continue

            # Get full track objects from original playlist (needed for remove API)
            print(f"  📥 Obteniendo tracks de '{pl_name}' para mover...")
            original_tracks = self.yt.get_playlist_items(original_pid, limit=5000)
            vid_to_track = {t.get('videoId'): t for t in original_tracks if t.get('videoId')}

            candidate_vids = [s.get('Video ID') for s in candidates if s.get('Video ID')]

            if candidate_vids:
                print(f"  ➕ Añadiendo {len(candidate_vids)} canciones a '{archive_name}'...")
                try:
                    self.yt.add_playlist_items(archive_pid, candidate_vids)
                    print(f"  \033[92m✓ Añadidas.\033[0m")
                except Exception as e:
                    print(f"  \033[91m✗ Error añadiendo canciones: {e}\033[0m")
                    continue

                tracks_to_remove = [vid_to_track[vid] for vid in candidate_vids if vid in vid_to_track]
                if tracks_to_remove:
                    print(f"  ➖ Eliminando {len(tracks_to_remove)} canciones de '{pl_name}'...")
                    try:
                        self.yt.remove_playlist_items(original_pid, tracks_to_remove)
                        print(f"  \033[92m✓ Eliminadas.\033[0m")
                    except Exception as e:
                        print(f"  \033[91m✗ Error eliminando canciones: {e}\033[0m")

            # Update in-memory records
            candidate_vids_set = set(candidate_vids)
            for s in all_songs:
                if s.get('Playlist', '').lower() == pl_lower and s.get('Video ID') in candidate_vids_set:
                    s['Playlist'] = archive_name

            moved_count = len(candidate_vids)
            total_moved += moved_count
            print(f"  \033[92m✓ {moved_count} canciones movidas a '{archive_name}'.\033[0m")

        # Save Sheet (Playlist column + any Year changes not yet saved)
        if total_moved > 0:
            print(f"\n  📝 Actualizando {total_moved} registros en el Sheet...")
            self.sheets.overwrite_songs(all_songs)
            print(f"\033[92m✓ Sheet actualizado.\033[0m")

        print(f"\n\033[92m✅ Archivado completado. Total: {total_moved} canciones movidas.\033[0m")

    def cleanup_inbox_duplicates(self):
        pass







    def cleanup_collab_artists(self):
        print("\n\033[96m" + "━"*50 + "\033[0m")
        print("\033[1;96m🧹 CLEANUP COLLABORATIVE ARTISTS\033[0m")
        print("\033[96m" + "━"*50 + "\033[0m")
        
        artists = self.sheets.get_artists()
        songs = self.sheets.get_songs_records()
        collab_pattern = re.compile(r'\b(y|and|&|,)\b', re.IGNORECASE)
        
        collab_artists = []
        for a in artists:
            name = a.get("Artist Name", "")
            if collab_pattern.search(name) or "," in name:
                collab_artists.append(a)

        if not collab_artists:
            print("No se encontraron artistas que parezcan colaboraciones.")
            return

        print(f"\nSe han encontrado {len(collab_artists)} artistas que parecen colaboraciones.")

        artists_to_remove = []
        songs_to_archive = []

        resolved_playlist_ids = {}
        print("\nResolviendo IDs de playlists...")
        for pl_name in Config.SOURCE_PLAYLISTS:
            if pl_name == '#':
                resolved_playlist_ids['#'] = Config.PLAYLIST_ID
                continue
            try:
                search_res = self.yt.yt.search(pl_name, filter='playlists', scope='library')
                for r in search_res:
                    if r.get('title', '').lower().strip() == pl_name.lower().strip():
                        pid = r.get('playlistId') or r.get('browseId', '').replace('VL', '')
                        resolved_playlist_ids[pl_name] = pid
                        break
            except Exception:
                pass

        for a in collab_artists:
            artist_name = a.get("Artist Name", "")
            
            # Encontramos sus canciones
            artist_songs = [s for s in songs if s.get("Artist") == artist_name or artist_name in s.get("Artist", "").split(", ")]
            
            print(f"\n========================================")
            print(f"Artista: {artist_name}")
            if artist_songs:
                print(f"Canciones asociadas ({len(artist_songs)}):")
                for s in artist_songs:
                    print(f"  - {s.get('Title')} (Playlist: {s.get('Playlist')})")
            else:
                print("No tiene canciones registradas en la hoja 'Songs'.")
            
            ans = input(f"¿Eliminar este artista y todas las canciones listadas arriba? [S/n]: ").strip().lower()
            if ans == 'n':
                continue

            artists_to_remove.append(artist_name)

            if artist_songs:
                for s in artist_songs:
                    pl_name = s.get("Playlist", "")
                    vid = s.get("Video ID")
                    if pl_name and vid:
                        pid = resolved_playlist_ids.get(pl_name)
                        if pid:
                            try:
                                pl_items = self.yt.get_playlist_items_with_status(pid)
                                yt_items_to_remove = [item for item in pl_items if item.get('videoId') == vid]
                                if yt_items_to_remove:
                                    self.yt.remove_playlist_items(pid, yt_items_to_remove)
                                    print(f"    ✓ Eliminada de YouTube de la playlist '{pl_name}'")
                                else:
                                    print(f"    ⚠ No se encontró en la playlist de YT.")
                            except Exception as e:
                                print(f"    ✗ Error al borrar de YT: {e}")
                    
                    songs_to_archive.append(s)

        # Actualizar Sheets
        if artists_to_remove:
            print("\nActualizando Google Sheets...")
            new_artists = [a for a in artists if a.get("Artist Name") not in artists_to_remove]
            self.sheets.save_artists(new_artists)
            print(f"✓ {len(artists_to_remove)} artistas eliminados de la pestaña 'Artists'.")

            if songs_to_archive:
                vids_to_archive = {s.get('Video ID') for s in songs_to_archive}
                new_songs = [s for s in songs if s.get('Video ID') not in vids_to_archive]
                self.sheets.overwrite_songs(new_songs)
                self.sheets.add_to_archived_batch(songs_to_archive)
                print(f"✓ {len(songs_to_archive)} canciones movidas a 'Archived'.")

        print("\nLimpieza interactiva completada.")

    def cleanup_likes(self):
        print("\n" + "━"*50)
        print("🧹 CLEANING UP LIKED SONGS (BASED ON LAST.FM PLAY COUNT)")
        print("━"*50)

        # 1. Resolve "LM" playlist
        target_pl_name = "LM"
        playlist_id = self._resolve_playlist_id(target_pl_name)
        
        if not playlist_id:
            print(f"  Playlist '{target_pl_name}' not found. Searching for 'Liked Songs' collection...")
            try:
                liked_data = self.yt.yt.get_liked_songs(limit=500)
                liked_songs = liked_data.get('tracks', [])
            except Exception as e:
                print(f"  Error fetching liked songs: {e}")
                return
        else:
            print(f"  Playlist '{target_pl_name}' found ({playlist_id}). Fetching items...")
            liked_songs = self.yt.get_playlist_items_with_status(playlist_id)

        if not liked_songs:
            print("  No liked songs found.")
            return

        print(f"  Processing {len(liked_songs)} songs...")

        # 2. Preparation for Last.fm enrichment
        songs_to_enrich = []
        for s in liked_songs:
            vid = s.get('videoId')
            if not vid: continue
            
            artist = s.get('artists', [{}])[0].get('name', 'Unknown')
            title = s.get('title', 'Unknown')
            
            songs_to_enrich.append({
                'Artist': artist,
                'Title': title,
                'Video ID': vid
            })

        # 3. Last.fm Enrichment (Batch & Parallel)
        print(f"  Fetching play counts for {len(songs_to_enrich)} songs from Last.fm...")
        self.lastfm.enrich_songs(songs_to_enrich, force_scrobbles=True, cache_ttl_days=1)

        # 4. Sheet Sync & Update Preparation
        sheet_songs = self.sheets.get_songs_records()
        vid_to_sheet_idx = {s.get('Video ID'): i for i, s in enumerate(sheet_songs) if s.get('Video ID')}
        
        unliked_count = 0
        songs_updated_in_sheet = 0

        # 5. Iterative Cleanup
        for song in songs_to_enrich:
            scrobbles = int(song.get('Scrobble', 0))
            vid = song.get('Video ID')
            artist = song.get('Artist')
            title = song.get('Title')

            # Update Sheet record if it exists
            if vid in vid_to_sheet_idx:
                idx = vid_to_sheet_idx[vid]
                sheet_songs[idx]['Scrobble'] = scrobbles
                sheet_songs[idx]['LastfmScrobble'] = song.get('LastfmScrobble', 0)
                songs_updated_in_sheet += 1

            # Check threshold
            if scrobbles >= Config.UNLIKE_THRESHOLD:
                print(f"\n🎵 {artist} - {title}")
                print(f"   🎧 Plays: {scrobbles} (Threshold: {Config.UNLIKE_THRESHOLD})")
                
                choice = input("   ¿Quitar 'Me gusta' en YT Music? [y/N/q]: ").strip().lower()
                
                if choice == 'q':
                    print("🛑 Operation aborted by user.")
                    break
                elif choice == 'y':
                    try:
                        self.yt.rate_song(vid, 'INDIFFERENT')
                        unliked_count += 1
                        print("   ✅ Unmarked as Liked.")
                    except Exception as e:
                        print(f"   ❌ Error updating rating: {e}")
                else:
                    print("   ⏭ Song kept as Liked.")

        # 6. Final Sheet Save
        if songs_updated_in_sheet > 0:
            print(f"\n📝 Updating {songs_updated_in_sheet} records in Songs sheet with fresh scrobbles...")
            self.sheets.overwrite_songs(sheet_songs)

        print(f"\n✅ Cleanup complete. {unliked_count} songs unliked, {songs_updated_in_sheet} records updated in sheet.")
