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
        self._archiving_config = self._load_archiving_config()
        self.library_catalog = None

    def _get_library_catalog(self):
        """Fetches and caches a map of all video IDs to their items in the user's YouTube Library."""
        if self.library_catalog is None:
            print("  \033[93m⌛ Fetching YouTube Library index for safe removal...\033[0m")
            try:
                songs = self.yt.get_library_songs(limit=None)
                # Map videoId to the whole item so we can access feedbackTokens
                self.library_catalog = {s.get('videoId'): s for s in songs if s.get('videoId')}
                print(f"    \033[92m✓\033[0m Loaded {len(self.library_catalog)} library tracks.")
            except Exception as e:
                print(f"    \033[91m✗ Error fetching library: {e}\033[0m")
                self.library_catalog = {}
        return self.library_catalog

    def _load_archiving_config(self):
        """Loads the year interval configuration for archiving."""
        if os.path.exists(Config.ARCHIVING_CONFIG_FILE):
            with open(Config.ARCHIVING_CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}

    def _save_archiving_config(self):
        """Saves current archiving config to JSON."""
        with open(Config.ARCHIVING_CONFIG_FILE, 'w') as f:
            json.dump(self._archiving_config, f, indent=2)

    def get_target_playlist_by_year(self, base_playlist, year):
        """Resolves target playlist name based on base name and release year.
        
        Example: 'Pop' and 2019 -> 'Pop (0-2021)' if 2019 is in that range.
        If no range is found or year is 0, it defaults to the base_playlist.
        """
        if not base_playlist or not year:
            return base_playlist
            
        intervals = self._archiving_config.get(base_playlist)
        if not intervals:
            return base_playlist
            
        for start_y, end_y in intervals:
            if start_y <= year <= end_y:
                return f"{base_playlist} ({start_y}-{end_y})"
                
        return base_playlist

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
        import unicodedata
        if not text: return ""
        # Normalización NFC para que 'á' (compuesta) coincida con 'a' + '´' (descompuesta, típica en Mac)
        normalized = unicodedata.normalize('NFC', str(text))
        return normalized.lower().strip()

    def _print_artist_catalog_summary(self, artist_name):
        """Prints a summary of already tracked songs for the given artist."""
        norm_name = self._normalize(artist_name)
        active_songs = self.sheets.get_songs_records()
        archived_songs = self.sheets.get_archived_records()
        
        all_tracked_songs = []
        seen_vids = set()
        active_vids = set()
        
        for s in active_songs:
            vid = s.get("Video ID")
            if vid:
                if vid not in seen_vids:
                    seen_vids.add(vid)
                    active_vids.add(vid)
                    all_tracked_songs.append(s)
            else:
                all_tracked_songs.append(s)
                
        for s in archived_songs:
            vid = s.get("Video ID")
            if vid:
                if vid not in seen_vids:
                    seen_vids.add(vid)
                    all_tracked_songs.append(s)
            else:
                all_tracked_songs.append(s)
        
        all_artists = self.sheets.get_artists()
        tracked_artists = {self._normalize(a.get("Artist Name", "")) for a in all_artists}

        def song_has_artist(song, target_norm_name):
            field = str(song.get("Artist", "")).strip()
            norm_field = self._normalize(field)
            if norm_field == target_norm_name:
                return True
            
            # Si el campo exacto del artista de la canción es un artista que seguimos (pero no es este)
            # devolvemos False para evitar emparejamientos indeseados (ej: 'The National' vs 'National')
            if norm_field in tracked_artists:
                return False
                
            # Fallback: separadores comunes
            normalized_parts = [self._normalize(p) for p in re.split(r'[,&]', field)]
            return target_norm_name in normalized_parts

        artist_songs = [s for s in all_tracked_songs if song_has_artist(s, norm_name)]
        
        if artist_songs:
            artist_songs_sorted = sorted(artist_songs, key=lambda x: int(x.get("LastfmScrobble") or 0), reverse=True)
            print(f"\n  \033[94m🎵 Biblioteca Actual ({len(artist_songs)}):\033[0m")
            # Mostrar solo el top 15 si hay muchas para no saturar la pantalla
            limit = 15
            for s in artist_songs_sorted[:limit]:
                s_title = s.get("Title", "")
                s_scrobble = int(s.get("LastfmScrobble") or 0)
                s_scrobble_fmt = f"{s_scrobble:,}".replace(",", ".")
                s_pl = s.get("Playlist", "")
                s_year = s.get("Year", "")
                year_str = f" {s_year}" if s_year else ""
                
                # Tag si es archivada (solo si NO está en activas)
                is_archived = s.get("Video ID") not in active_vids
                arch_tag = " \033[33m[ARCH]\033[0m" if is_archived else ""
                
                print(f"    - \033[1;92m{s_title}\033[0m\033[90m{year_str} [{s_scrobble_fmt}🎧]\033[0m \033[35m[{s_pl}]{arch_tag}\033[0m")
            
            if len(artist_songs) > limit:
                print(f"    \033[90m... y {len(artist_songs) - limit} canciones más.\033[0m")
            print()
        else:
            print(f"\n  \033[90m[✕ Biblioteca Actual: 0 canciones conocidas para '{artist_name}']\033[0m\n")

    def _split_artist_names(self, raw_name, artist_map):
        """Intelligently splits an artist string into its individual artists, 
        respecting tracked names that might contain ampersands or commas.
        """
        if not raw_name: return []
        norm_raw = self._normalize(raw_name)
        
        # 1. If the exact combination is already tracked as a single entity, don't split
        if norm_raw in artist_map:
            return [artist_map[norm_raw].get('Artist Name') or raw_name]
        
        # 2. Split by comma first, then by ampersand
        parts = [p.strip() for p in re.split(r'[,]', raw_name) if p.strip()]
        final_parts = []
        for p in parts:
            if self._normalize(p) in artist_map:
                final_parts.append(p)
            else:
                # If the part is not a tracked artist, check for ampersands
                sub_parts = [sp.strip() for sp in re.split(r'[&]', p) if sp.strip()]
                final_parts.extend(sub_parts)
                
        return final_parts

    def _normalize_id(self, text):
        if not text: return ""
        # Remove any prefix like 'artist/' or similar if present (though usually not from YT API)
        s = str(text).strip()
        if '/' in s: s = s.split('/')[-1]
        return s

    def _find_artist_row(self, artists_records, name=None, artists_list=None):
        """Finds an artist in records using ID if available, otherwise by Name."""
        # 1. Match by ID (Highest priority)
        if artists_list:
            for art in artists_list:
                m_id = (art.get('id') or art.get('browseId'))
                m_id_norm = self._normalize_id(m_id)
                if m_id_norm:
                    for a in artists_records:
                        if self._normalize_id(a.get('Artist ID')) == m_id_norm:
                            return a
        elif name: # Single name case
            # This is less common now but kept for compatibility
            pass 
        
        # 2. Match by Name (Fallback)
        if artists_list:
            for art in artists_list:
                norm_name = self._normalize(art.get('name', ''))
                for a in artists_records:
                    if self._normalize(a.get('Artist Name', '')) == norm_name:
                        return a
        
        if name:
            norm_name = self._normalize(name)
            for a in artists_records:
                if self._normalize(a.get('Artist Name', '')) == norm_name:
                    return a
        
        return None

    def _ensure_artist_tracked(self, artists_records, main_artist, artists_list, pl_name, all_songs):
        """Ensures an artist is in the tracking list, prompts for onboarding if not."""
        artist_row = self._find_artist_row(artists_records, name=main_artist, artists_list=artists_list)
        
        if artist_row:
            # If name is different but ID matched, we could update it, but for now we trust the row
            return artist_row

        # If not found, start onboarding
        onboarding_artist = main_artist
        onboarding_id = (artists_list[0].get('id') or artists_list[0].get('browseId')) if artists_list else None

        # When multiple artists are present (collaboration), silently default to
        # the primary artist (index 0) — never prompt the user for compound artists.
        if artists_list and len(artists_list) > 1:
            collab_names = ", ".join([f"'{a['name']}'" for a in artists_list])
            print(f"    \033[90mℹ Collaboration [{collab_names}] → using primary: '{onboarding_artist}'\033[0m")
        
        import re
        default_pl = pl_name.replace(' $', '')
        # Remove any interval trailing string like " (2015-2021)" or " (2006-2022)"
        default_pl = re.sub(r'\s*\(\d{4}-\d{4}\)$', '', default_pl).strip()
        
        # Inbox '#' should never be an artist's permanent home.
        if default_pl == "#":
            default_pl = ""
            
        print(f"    \033[93m🆕 Tracking new artist: \033[1;96m'{onboarding_artist}'\033[0m")
        prompt = f"      Which playlist should receive their new releases? "
        if default_pl:
            prompt += f"[\033[92m{default_pl}\033[0m]: "
        else:
            prompt += "(e.g. Rock, Pop, Indie): "
            
        res_pl = input(prompt).strip()
        final_pl = res_pl if res_pl else default_pl
        
        if not final_pl:
            print(f"      ⏭  Artist '{onboarding_artist}' not registered (no default playlist).")
            return None

        print(f"      ✅ Registering '{onboarding_artist}' in Artists sheet with playlist '{final_pl}'.")
        
        # Get metadata for the chosen one
        m_id = onboarding_id
        
        # Genre lookup
        m_genre = None
        try:
            a_info = self.lastfm.get_artist_info(onboarding_artist)
            m_genre = a_info.get('genre', '')
        except: pass

        m_count = len([s for s in all_songs if self._normalize(s.get('Artist', '')) == self._normalize(onboarding_artist)])
        
        # Persist to sheet
        self.sheets.update_artist_playlist(onboarding_artist, final_pl, artist_id=m_id, genre=m_genre, song_count=m_count)
        
        # After update_artist_playlist, the local cache in self.sheets is updated.
        # Since artists_records is a reference to that list, it already contains the new artist.
        # We find and return that updated record to the caller.
        return self._find_artist_row(artists_records, name=onboarding_artist, artists_list=artists_list)

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
        all_to_fetch = list(Config.SOURCE_PLAYLISTS)
        for base_pl, intervals in self._archiving_config.items():
            for start_y, end_y in intervals:
                archive_name = f"{base_pl} ({start_y}-{end_y})"
                if archive_name not in all_to_fetch:
                    all_to_fetch.append(archive_name)

        for pl_name in all_to_fetch:
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

    def apply_manual_moves(self, refresh_cache=False, target_artist_name=None, target_playlist_name=None, api_choice="lastfm"):
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
        
        if target_playlist_name:
            print(f"\033[93m🎯 Filtro Playlist Destino: {target_playlist_name}\033[0m")
            
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
            songs_to_process = [s for s in songs_to_process if norm_target in self._normalize(s.get('Artist', ''))]
            
        if target_playlist_name:
            norm_pl_target = self._normalize(target_playlist_name)
            songs_to_process = [s for s in songs_to_process if self._normalize(s.get('Playlist', '')) == norm_pl_target]

        if not songs_to_process:
            if target_artist_name or target_playlist_name:
                print(f"No se encontraron canciones con los filtros aplicados.")
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
            year_str = f" \033[93m({song_year})\033[0m" if song_year else ""

            # Cálculo de estado de sincronización previo al prompt
            already_in_target = vid in cache_vids.get(target_pl_lower, set())
            # Está en sync si está en la de destino y NO está en ninguna otra del catálogo
            is_synced = already_in_target and not any(ck.lower() != target_pl_lower for ck, _ in other_entries_catalog)
            
            print(f"\n  \033[1;96m{artist}\033[0m \033[90m-\033[0m \033[1;92m{song_title}\033[0m{year_str}")
            if is_synced:
                print(f"    \033[92m✔ En sync con '{target_pl}'\033[0m")
            else:
                from_str = ", ".join(current_pls) if current_pls else "(Ninguna)"
                print(f"    \033[93m⚠ Diferencia detectada: \033[90m{from_str}\033[0m -> \033[1;94m{target_pl or '?'}\033[0m")
            
            print(f"    🎵  Género de la canción: \033[96m{genres}\033[0m")
            
            # Interactive Logic: Skip prompt if target_playlist_name or target_artist_name is set
            auto_mode = (target_playlist_name is not None)

            # ── Archive routing check ──
            original_target_pl = target_pl
            if target_pl in Config.ARCHIVABLE_PLAYLISTS and song_year:
                resolved_target = self.get_target_playlist_by_year(target_pl, int(song_year))
                if resolved_target != target_pl:
                    print(f"    \033[93m📦 Redirigiendo por año ({song_year}): '{target_pl}' → '{resolved_target}'\033[0m")
                    target_pl = resolved_target
                    target_pl_lower = target_pl.lower()
                    # Actualizamos la hoja de cálculo para que refleje el destino exacto (archivo)
                    song['Playlist'] = target_pl
                    sheet_changed = True
                    print(f"    \033[93m📝 Sheet: Actualizado a destino de archivo '{target_pl}'\033[0m")
            
            if auto_mode:
                user_input = "" # Treat as Enter
                if not is_synced or target_pl != original_target_pl:
                    print(f"    🚀 Automatic Reposition to '{target_pl}'...")
            else:
                prompt = f"    📍 Destino (Enter=OK/Saltar, 'q'=salir, NuevaPL): "
                user_input = input(prompt).strip()

            if user_input.lower() == 'q':
                print("    Abortando y guardando cambios...")
                _finalize_song_iteration(None)
                break
                
            if user_input == '':
                if is_synced:
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
                    # Aumentamos el límite para cubrir bibliotecas grandes
                    liked = self.yt.yt.get_liked_songs(limit=5000)
                    liked_tracks = liked.get('tracks', [])
                    liked_vids = {t['videoId'] for t in liked_tracks if t.get('videoId')}
                except Exception:
                    pass

            # ── 2c. Metadata Preparation & Last.fm Enrichment ──
            # Always ensure Artist/Title keys are set for archiving and internal logic, even if skipping Last.fm
            for item in fresh_items:
                art_list = item.get('artists', [])
                if art_list:
                    item['Artist'] = ", ".join([a.get('name', '') for a in art_list])
                else:
                    item['Artist'] = 'Unknown'
                item['Title'] = item.get('title', 'Unknown')

            if not skip_lastfm:
                print(f"  \033[93m⌛ Fetching scrobbles from Last.fm for {len(fresh_items)} songs...\033[0m")
                self.lastfm.enrich_songs(fresh_items, force_scrobbles=False)

            print(f"  Checking {len(fresh_items)} songs for likes/dislikes...")
            
            # Important: iterate over a copy or tracking list to handle removals
            for item in list(fresh_items):
                vid = item.get('videoId')
                song_title = item.get('title', 'Unknown')
                
                # ── Registro/Verificación de Artista (Lógica de Onboarding) ──
                artists_list = item.get('artists', [])
                main_artist = artists_list[0]['name'] if artists_list else 'Unknown'
                artist_row = self._ensure_artist_tracked(artists_records, main_artist, artists_list, pl_name, all_songs)
                if not artist_row:
                    continue # Skip processing this song if artist not tracked
                
                # Check status from 3 sources: YT Metadata, YT Liked List, or Google Sheet
                yt_status = item.get('likeStatus', 'INDIFFERENT')
                is_in_liked_list = vid in liked_vids
                sheet_status = existing_vids.get(vid, {}).get('status', '') if vid in existing_vids else ''
                
                status = 'INDIFFERENT'
                if yt_status == 'LIKE' or is_in_liked_list or sheet_status == 'Like':
                    status = 'LIKE'
                elif yt_status == 'DISLIKE':
                    status = 'DISLIKE'
                

                
                # Get current scrobbles for logic
                scrobbles = item.get('Scrobble', 0)
                if not scrobbles and vid in existing_vids:
                    try: scrobbles = int(existing_vids[vid].get('Scrobble', 0))
                    except: pass
                
                # ── 1. ARCHIVADO AUTOMÁTICO DESDE PLAYLISTS DE GÉNERO (No Inbox) ──
                # Si estamos sincronizando una playlist normal (ej: 'Español') y es archivable,
                # comprobamos si alguna canción debería ir ya a su versión de catálogo.
                if not is_hash and pl_name in Config.ARCHIVABLE_PLAYLISTS:
                    song_year = 0
                    y_str = (existing_vids.get(vid) or {}).get('Year') or item.get('year')
                    if not y_str:
                        y_str = self._fetch_song_year(vid, song_title, item.get('Artist', ''))
                    
                    if y_str:
                        match = re.search(r'(\d{4})', str(y_str))
                        if match: song_year = int(match.group(1))
                    
                    if song_year:
                        archive_name = self.get_target_playlist_by_year(pl_name, song_year)
                        if archive_name != pl_name:
                            print(f"    \033[93m📦 Propuesta de Archivo: Año {song_year} → '{archive_name}'\033[0m")
                            ans = input(f"      ¿Mover '{song_title} ({song_year})' de '{pl_name}' a '{archive_name}'? [S/n]: ").strip().lower()

                            if ans != 'n':
                                target_pid = self._resolve_playlist_id(archive_name)
                                if target_pid:
                                    try:
                                        self.yt.add_playlist_items(target_pid, [vid])
                                        self.yt.remove_playlist_items(pid, [item])
                                        self.yt.rate_song(vid, 'INDIFFERENT') # Quitar like al archivar
                                        
                                        # Construct robust record for the archive
                                        base_row = existing_vids.get(vid) or {}
                                        new_rec = {
                                            'Playlist': archive_name,
                                            'Artist': base_row.get('Artist') or item.get('Artist', 'Unknown'),
                                            'Title': base_row.get('Title') or song_title,
                                            'Album': base_row.get('Album') or (item.get('album') or {}).get('name', ''),
                                            'Year': base_row.get('Year') or str(y_str),
                                            'Video ID': vid
                                        }
                                        new_rec['Playlist'] = archive_name
                                        moved_for_sheet.append(new_rec)
                                        
                                        if vid in yt_vid_map: del yt_vid_map[vid]
                                        continue # Siguiente canción
                                    except Exception as e:
                                        print(f"      ✗ Error al auto-archivar: {e}")
                                else:
                                    print(f"      ⚠ No se pudo encontrar el ID de la playlist '{archive_name}'")
                            else:
                                print(f"      ⏭  Canción mantenida en '{pl_name}'.")

                
                high_scrobbles = is_hash and scrobbles > Config.SCROBBLE_THRESHOLD
                
                if status == 'DISLIKE' or high_scrobbles:
                    reason = "Disliked" if status == 'DISLIKE' else "High scrobbles"
                    artists_str = ", ".join([a.get('name', '') for a in item.get('artists', [])])
                    print(f"    \033[91m✗ {reason} → Archiving:\033[0m \033[92m{artists_str} - {item.get('title')}\033[0m")
                    try:
                        self.yt.remove_playlist_items(pid, [item])
                        if status == 'DISLIKE': 
                            self.yt.rate_song(vid, 'INDIFFERENT')
                    except Exception as e:
                        print(f"      ⚠ Error during YouTube archive/remove: {e}")
                    
                    # Use scrobbles from Last.fm if available, fallback to sheet
                    scrobble_val = item.get('Scrobble', 0)
                    lastfm_val = item.get('LastfmScrobble', 0)
                    genre_val = item.get('Genre', '')
                    if not scrobble_val and vid in existing_vids:
                        scrobble_val = existing_vids[vid].get('Scrobble', 0)
                    
                    # Construct robust record for the Archive sheet
                    base_row = existing_vids.get(vid) or {}
                    row = {
                        'Playlist': pl_name,
                        'Artist': base_row.get('Artist') or item.get('Artist', 'Unknown'),
                        'Title': base_row.get('Title') or item.get('Title', 'Unknown'),
                        'Album': base_row.get('Album') or (item.get('album', {}) or {}).get('name', ''),
                        'Year': base_row.get('Year') or str(item.get('year', '')),
                        'Video ID': vid, 
                        'Scrobble': scrobble_val,
                        'LastfmScrobble': lastfm_val,
                        'Genre': genre_val or base_row.get('Genre', '')
                    }
                    disliked_for_archive.append(row)
                    disliked_vids_global.add(vid)
                    if vid in yt_vid_map: del yt_vid_map[vid]
                    continue

                if is_hash and status == 'LIKE':
                    artists_list = item.get('artists', [])
                    main_artist = artists_list[0]['name'] if artists_list else 'Unknown'
                    song_title = item.get('title', 'Unknown')
                    
                    # Look up target playlist in sheet
                    artist_row = self._find_artist_row(artists_records, name=main_artist, artists_list=artists_list)
                    target_pl = (artist_row.get('Playlist') or '').strip() if artist_row else ''
                    
                    actual_target_pl = ""
                    
                    if not target_pl:
                        print(f"    \033[93m❓ Artista '{main_artist}' sin playlist asignada.\033[0m")
                        print(f"      Canción: \033[92m{song_title}\033[0m")
                        res_pl = input(f"      ¿A qué playlist enviamos a \033[1m'{main_artist}'\033[0m? ").strip()
                        if res_pl:
                            actual_target_pl = res_pl
                            print(f"      ✅ Asignando '{res_pl}' como playlist por defecto para '{main_artist}'.")
                            
                            # Recopilar datos adicionales
                            m_id = (artists_list[0].get('id') or artists_list[0].get('browseId')) if artists_list else None
                            
                            m_genre = item.get('Genre')
                            if not m_genre:
                                try:
                                    a_info = self.lastfm.get_artist_info(main_artist)
                                    m_genre = a_info.get('genre', '')
                                except: pass

                            m_count = len([s for s in all_songs if self._normalize(s.get('Artist', '')) == self._normalize(main_artist)])
                            
                            self.sheets.update_artist_playlist(main_artist, res_pl, artist_id=m_id, genre=m_genre, song_count=m_count)
                            # After update_artist_playlist, the cache in self.sheets is updated.
                            # We don't need to manually append to artists_records if it's a reference to the cache.
                            artist_row = self._find_artist_row(artists_records, name=main_artist, artists_list=artists_list)
                    else:
                        # AUTOMATISMO: Mover sin preguntar si ya tiene playlist
                        print(f"    ♥ Liked → \033[92m{main_artist} - {song_title}\033[0m")
                        print(f"      Destino automático: \033[1;94m[{target_pl}]\033[0m")
                        actual_target_pl = target_pl
                    
                    if actual_target_pl:
                        # ── Year check ───────────────────────
                        song_year = 0
                        y_str = (existing_vids.get(vid) or {}).get('Year') or item.get('year')
                        
                        if not y_str:
                            y_str = self._fetch_song_year(vid, song_title, main_artist)

                        if y_str:
                            match = re.search(r'(\d{4})', str(y_str))
                            if match: song_year = int(match.group(1))

                        # ── Archive routing check ──
                        final_target_pl = actual_target_pl
                        if actual_target_pl in Config.ARCHIVABLE_PLAYLISTS and song_year:
                            # Re-resolver destino según el año
                            final_target_pl = self.get_target_playlist_by_year(actual_target_pl, song_year)
                            if final_target_pl != actual_target_pl:
                                print(f"    \033[93m📦 Año {song_year} → redirigiendo a '{final_target_pl}'\033[0m")

                        # ── Final Unliking Logic ──
                        # Flag para saber si hay que quitar el Like después de mover
                        should_unlike = final_target_pl not in Config.SOURCE_PLAYLISTS
                        if should_unlike:
                            print(f"    \033[93m⚠ Archivo catalogado → Quitando Like tras mover:\033[0m \033[92m{main_artist} - {song_title}\033[0m")

                        print(f"    🚀 Moviendo a \033[1;94m[{final_target_pl}]\033[0m")
                        target_pid = self._resolve_playlist_id(final_target_pl)
                        if target_pid:
                            try:
                                self.yt.add_playlist_items(target_pid, [vid])
                                self.yt.remove_playlist_items(pid, [item])

                                # Quitamos el Like DESPUES de mover para evitar que YT lo re-aplique al guardar
                                if should_unlike:
                                    try:
                                        self.yt.rate_song(vid, 'INDIFFERENT')
                                    except Exception as e:
                                        print(f"      \033[91m✗ Error quitando Like:\033[0m {e}")
                                
                                # Use Last.fm values for record
                                sc_str = str(item.get('Scrobble', 0)).replace('.', '').replace(',', '').strip()
                                sc_val = int(sc_str) if sc_str.isdigit() else 0
                                if sc_val == 0 and vid in existing_vids:
                                    sc_str = str(existing_vids[vid].get('Scrobble', '0')).replace('.', '').replace(',', '').strip()
                                    sc_val = int(sc_str) if sc_str.isdigit() else 0
                                    
                                lsc_val = item.get('LastfmScrobble', 0)
                                gen_val = item.get('Genre', '')
                                
                                # ── ADD TO PENDIENTE LOGIC ──
                                if final_target_pl not in Config.SOURCE_PLAYLISTS and sc_val <= Config.PENDING_AUTO_ADD_THRESHOLD:
                                    print(f"      📌 Pocas reproducciones (<= {Config.PENDING_AUTO_ADD_THRESHOLD}) → Añadiendo también a 'Pendiente'")
                                    pendiente_pid = self._resolve_playlist_id("Pendiente")
                                    if not pendiente_pid:
                                        pendiente_pid = self.yt.create_playlist("Pendiente", "Canciones con pocas reproducciones para revisar")
                                    if pendiente_pid:
                                        try:
                                            self.yt.add_playlist_items(pendiente_pid, [vid])
                                        except Exception as e:
                                            print(f"        ⚠ Error en Pendiente: {e}")


                                new_record = dict(existing_vids.get(vid) or {
                                    'Playlist': final_target_pl, 'Artist': item.get('Artist', main_artist),
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
                    
                    # Identificar artista principal
                    artists_list = item.get('artists', [])
                    main_artist = artists_list[0]['name'] if artists_list else 'Unknown'
                    
                    # ── Registro de Artista Nuevo (Usando el helper consolidado) ──
                    artist_row = self._ensure_artist_tracked(artists_records, main_artist, artists_list, pl_name, all_songs)
                    if not artist_row:
                        continue # Skip song if artist not confirmed


                    artist_str = ", ".join([a.get('name', '') for a in artists_list])
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
                    # Always update metadata (Scrobbles and Genre) if they exist
                    if 'Scrobble' in yt_item: s['Scrobble'] = yt_item['Scrobble']
                    if 'LastfmScrobble' in yt_item: s['LastfmScrobble'] = yt_item['LastfmScrobble']
                    if yt_item.get('Genre'): 
                        s['Genre'] = yt_item['Genre']
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
        
        candidates = results[:5]
        best = candidates[0]
        
        # Si hay más de un resultado o el nombre no coincide exactamente, ofrecemos elegir
        if len(candidates) > 1:
            print(f"  \033[93mMultiple matches found for '{name}'. Please choose one:\033[0m")
            options = []
            for i, c in enumerate(candidates):
                artist_name = c['artist']
                artist_id = c['browseId']
                
                # Fetch top song to help disambiguation
                top_song_title = "Unknown"
                top_song_listeners = 0
                try:
                    # Buscamos la canción más popular para mostrarla
                    artist_data = self.yt.yt.get_artist(artist_id)
                    if 'songs' in artist_data and 'results' in artist_data['songs']:
                        top_song = artist_data['songs']['results'][0]
                        top_song_title = top_song.get('title', 'Unknown')
                        # Obtenemos oyentes globales de Last.fm
                        info = self.lastfm.get_track_info(artist_name, top_song_title)
                        top_song_listeners = int(info.get('lastfm_listeners', 0))
                except:
                    pass
                
                listeners_fmt = f"{top_song_listeners:,}".replace(",", ".")
                print(f"    [{i+1}] \033[1;92m{artist_name}\033[0m — Top Song: '{top_song_title}' \033[90m[{listeners_fmt}🎧]\033[0m")
                options.append(c)
                
            ans = input(f"  Choose artist (1-{len(options)}) or 'q' to cancel: ").strip().lower()
            if ans == 'q':
                return "cancelled", {}
            try:
                idx = int(ans) - 1
                if 0 <= idx < len(options):
                    best = options[idx]
                else:
                    print("  \033[91mInvalid index. Using first result.\033[0m")
            except ValueError:
                if ans != "":
                    print("  \033[91mInvalid input. Using first result.\033[0m")
        
        artist_name = best['artist']
        artist_id = best['browseId']
        
        artists = self.sheets.get_artists()
        for a in artists:
            if a.get('Artist ID') == artist_id:
                # Si el artista existe pero no tiene nombre (corrupción de datos), lo recuperamos
                if not a.get('Artist Name'):
                    a['Artist Name'] = artist_name
                    self.sheets.save_artists(artists)
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

    def deduplicate_artists(self):
        """Identifica y elimina artistas duplicados en la hoja de 'Artists'."""
        all_artists = self.sheets.get_artists()
        if not all_artists:
            return []

        # 1. Agrupar por Artist ID (para detectar nombres distintos pero misma entidad)
        # 2. Agrupar por Nombre Normalizado (para detectar el mismo nombre repetido)
        id_groups = {}
        name_groups = {}
        
        for i, a in enumerate(all_artists):
            aid = str(a.get('Artist ID', '')).strip()
            name = a.get('Artist Name', '').strip()
            if not name: continue
            norm = self._normalize(name)
            
            if aid:
                if aid not in id_groups: id_groups[aid] = []
                id_groups[aid].append((i, a))
            
            if norm not in name_groups: name_groups[norm] = []
            name_groups[norm].append((i, a))

        to_remove_indices = set()
        name_renames = {} # {old_normalized_name: new_actual_name}
        modified = False

        # Procesar primero por ID (es más fiable)
        handled_indices = set()
        for aid, entries in id_groups.items():
            if len(entries) > 1:
                print(f"\n\033[1;91m⚠ ENTIDAD DUPLICADA (Mismo Artist ID): {aid}\033[0m")
                for idx, (original_idx, a) in enumerate(entries):
                    print(f"  {idx+1}) NAME: {a.get('Artist Name'):<30} | Playlist: {a.get('Playlist'):<15} | Count: {a.get('Song Count')}")
                
                res = input(f"    ¿Cuál quieres MANTENER como nombre canónico? (1-{len(entries)} o Enter para omitir): ").strip()
                if res.isdigit():
                    keep_idx_in_entries = int(res) - 1
                    if 0 <= keep_idx_in_entries < len(entries):
                        keep_original_idx, keep_artist = entries[keep_idx_in_entries]
                        kept_name = keep_artist.get('Artist Name')
                        
                        for i, (orig_idx, other_a) in enumerate(entries):
                            if i != keep_idx_in_entries:
                                to_remove_indices.add(orig_idx)
                                name_renames[self._normalize(other_a.get('Artist Name'))] = kept_name
                            handled_indices.add(orig_idx)
                        handled_indices.add(keep_original_idx)
                        modified = True
                        print(f"    ✅ Manteniendo '{kept_name}'. Los demás se unificarán.")

        # Procesar por Nombre (para los que no tienen ID o no han sido procesados)
        for norm, entries in name_groups.items():
            # Filtrar los que ya procesamos por ID
            relevant_entries = [e for e in entries if e[0] not in handled_indices]
            if len(relevant_entries) > 1:
                print(f"\n\033[1;91m⚠ DUPLICADO POR NOMBRE: '{relevant_entries[0][1]['Artist Name']}'\033[0m")
                for idx, (original_idx, a) in enumerate(relevant_entries):
                    print(f"  {idx+1}) ID: {a.get('Artist ID') or '---':<15} | Playlist: {a.get('Playlist'):<15} | Count: {a.get('Song Count')}")
                
                res = input(f"    ¿Cuál quieres MANTENER? (1-{len(relevant_entries)} o Enter para omitir): ").strip()
                if res.isdigit():
                    keep_idx_in_entries = int(res) - 1
                    if 0 <= keep_idx_in_entries < len(relevant_entries):
                        keep_original_idx, _ = relevant_entries[keep_idx_in_entries]
                        for i, (orig_idx, _) in enumerate(relevant_entries):
                            if i != keep_idx_in_entries:
                                to_remove_indices.add(orig_idx)
                        modified = True
                        print(f"    ✅ Manteniendo mejor registro. Eliminando duplicados.")

        if modified:
            # 1. Limpiar hoja de Artistas
            final_list = [a for i, a in enumerate(all_artists) if i not in to_remove_indices]
            self.sheets.save_artists(final_list)
            
            # 2. Si hay renombres, actualizar la hoja de Songs
            if name_renames:
                print(f"\n🔄 Actualizando nombres de artista en la hoja 'Songs' para {len(name_renames)} entidades...")
                all_songs = self.sheets.get_songs_records()
                replaced_total = 0
                for s in all_songs:
                    art = (s.get('Artist') or '').strip()
                    if not art: continue
                    norm_art = self._normalize(art)
                    if norm_art in name_renames:
                        s['Artist'] = name_renames[norm_art]
                        replaced_total += 1
                
                if replaced_total > 0:
                    self.sheets.overwrite_songs_sheet(all_songs)
                    print(f"    ✅ Se han corregido {replaced_total} menciones en 'Songs'.")

            print(f"\n✅ Limpieza completada. {len(to_remove_indices)} duplicados eliminados.")
            return final_list
        else:
            print("  No se encontraron duplicados.")
            return all_artists


    def sync_artists_from_songs(self):
        """
        Scans all songs in the 'Songs' sheet and updates the 'Artists' sheet.
        Excludes inbox ('#') songs for artist discovery of new candidates.
        Updates 'Song Count' for all tracked artists based on the full catalog.
        Performs interactive onboarding for new artists.
        """
        print("\n\033[94m" + "━"*60 + "\033[0m")
        print("\033[1;94m🔄 SYNCING ARTISTS FROM CATALOG (SONGS SHEET)\033[0m")
        print("\033[94m" + "━"*60 + "\033[0m")
        
        # 0. Deduplicate and audit for "fused" artists (collaborations)
        all_artists = self.deduplicate_artists()
        # Audit for possible fusions (like "Mark Kozelek & Desertshore") already tracked
        print("\n\033[1m🔍 Auditando artistas en seguimiento por posibles fusiones...\033[0m")
        all_artists = self.audit_fused_artists(all_artists)
        
        artist_map = {self._normalize(a.get('Artist Name')): a for a in all_artists if a.get('Artist Name')}
        
        all_songs = self.sheets.get_songs_records()

        if not all_songs:
            print("  ⚠ No songs found in the 'Songs' sheet.")
            return

        # 1. Group all songs by artist for counting (including Inbox)
        artist_counts = {}
        inbox_counts = {}
        # Matrix to find the "majority" playlist: norm_artist -> { base_playlist -> count }
        artist_pl_matrix = {}
        
        for s in all_songs:
            raw_art = (s.get('Artist') or '').strip()
            if not raw_art: continue
            
            # Split using smart helper that respects tracked artists
            artist_names = self._split_artist_names(raw_art, artist_map)
            
            pl = (s.get('Playlist') or '').strip()
            
            for art in artist_names:
                if not art: continue
                norm_art = self._normalize(art)
                
                # REGLA: No contamos canciones en el Inbox (#) para el Song Count acumulado
                if pl != '#':
                    artist_counts[norm_art] = artist_counts.get(norm_art, 0) + 1
                else:
                    inbox_counts[norm_art] = inbox_counts.get(norm_art, 0) + 1
                
                if pl and pl != '#':
                    # Normalize playlist name: use base name even if it's an archive list (Ending in ' $')
                    base_pl = pl.replace(' $', '').strip()
                    
                    # REGLA: Si es una playlist de archivo tipo "Rock (1994-2010)", la reducimos a la principal "Rock"
                    # para que la sugerencia de nuevas incorporaciones sea siempre la playlist base.
                    for source in Config.SOURCE_PLAYLISTS:
                        if source == "#": continue
                        if base_pl.startswith(source + " ("):
                            base_pl = source
                            break
                            
                    if norm_art not in artist_pl_matrix:
                        artist_pl_matrix[norm_art] = {}
                    artist_pl_matrix[norm_art][base_pl] = artist_pl_matrix[norm_art].get(base_pl, 0) + 1
            
        # 2. Identify unique "raw" artist strings from non-inbox playlists for discovery
        raw_names_from_songs = set()
        for s in all_songs:
            if s.get('Playlist') != '#':
                raw_art = (s.get('Artist') or '').strip()
                if raw_art:
                    raw_names_from_songs.add(raw_art)
        
        # 3. Process each artist
        print(f"  Found {len(raw_names_from_songs)} unique artist entries in catalog (excluding Inbox).")
        print(f"  Total unique normalized artists tracked/counted: {len(artist_counts)}")
        
        new_artists_added = 0
        
        # First: Handle Onboarding
        for raw_name in sorted(raw_names_from_songs):
            # Skip if whole string is already tracked
            if self._normalize(raw_name) in artist_map:
                continue

            parts = self._split_artist_names(raw_name, artist_map)
            # Identify which parts are missing from tracking
            missing_parts = [p for p in parts if self._normalize(p) not in artist_map]
            
            if not missing_parts:
                continue
                
            targets = []
            if len(parts) > 1:
                # COLLABORATION / DUAL NAME
                any_tracked = any(self._normalize(p) in artist_map for p in parts)
                
                print(f"\n\033[1;93m⚠ Posible colaboración detectada: '{raw_name}'\033[0m")
                print(f"    Artistas individuales encontrados: {', '.join(parts)}")
                if any_tracked:
                    tracked_list = [p for p in parts if self._normalize(p) in artist_map]
                    print(f"    (Ya sigues a: {', '.join(tracked_list)})")
                
                print(f"    ¿Qué deseas hacer con esta entrada?")
                print(f"    - 's': Registrar como UN SOLO artista/banda (ej: 'Mumford & Sons').")
                print(f"    - 'n': Tratar como VARIOS artistas independientes (y registrar los que falten).")
                print(f"    - 'i': DESCARTAR COMBO para siempre (no volver a preguntar por esta unión).")
                print(f"    - 'c': Omitir por ahora.")
                
                choice = input(f"    Opción (s/n/i/c): ").strip().lower()
                
                if choice == 's':
                    targets = [raw_name]
                elif choice == 'i':
                    print(f"    Marcando combo '{raw_name}' como 'Multi' permanentemente...")
                    # Forzar Status: Archived para cumplir con los 3 estados permitidos por el usuario
                    self.sheets.add_artist({'Artist Name': raw_name, 'Status': 'Archived', 'Type': 'Multi'})
                    artist_map[self._normalize(raw_name)] = {'Artist Name': raw_name, 'Status': 'Archived', 'Type': 'Multi'}
                    continue
                elif choice == 'n':
                    print(f"    Registrando componentes faltantes: {', '.join(missing_parts)}")
                    targets = missing_parts
                    # Opcionalmente, para no volver a preguntar por este combo aunque no registremos todos sus componentes,
                    # podríamos marcar el combo como ignorado también. Pero el usuario ha sugerido registrar cada uno.
                else:
                    continue
            else:
                # SINGLE ARTIST
                targets = missing_parts

                
            for name in targets:
                # Check again in case it was added in a previous iteration of this loop
                norm_name = self._normalize(name)
                if norm_name in artist_map:
                    continue
                
                total_songs = artist_counts.get(norm_name, 0)
                print(f"\n\033[93m❓ New artist found: '{name}'\033[0m (Total songs: {total_songs})")
                
                # Auto-detect majority playlist
                best_pl = ""
                pl_data = artist_pl_matrix.get(norm_name, {})
                if pl_data:
                    best_pl = max(pl_data, key=pl_data.get)
                
                prompt = f"    ¿A qué playlist enviamos a \033[1m'{name}'\033[0m?"
                if best_pl:
                    prompt += f" [\033[1mPredeterminada: {best_pl}\033[0m] "
                else:
                    prompt += " "
                
                res_pl = input(prompt).strip()
                if not res_pl:
                    if best_pl:
                        res_pl = best_pl
                    else:
                        print(f"    ⏭ Omitiendo registro de '{name}'...")
                        continue
                
                # Fetch metadata
                print(f"    ⌛ Buscando metadatos para '{name}'...")
                m_id = None
                try:
                    res = self.yt.yt.search(name, filter='artists')
                    if res:
                        # Try to find an exact match
                        for r in res:
                            if self._normalize(r.get('artist')) == norm_name:
                                m_id = r.get('browseId')
                                break
                        if not m_id:
                            m_id = res[0].get('browseId')
                except: pass
                
                m_genre = ""
                try:
                    a_info = self.lastfm.get_artist_info(name)
                    m_genre = a_info.get('genre', '')
                except: pass
                
                new_row = {
                    'Artist Name': name,
                    'Artist ID': m_id or '',
                    'Song Count': total_songs,
                    'Last Checked': datetime.now().strftime("%d/%m/%Y"),
                    'Status': 'Done',
                    'Genre': m_genre,
                    'Playlist': res_pl
                }
                all_artists.append(new_row)
                artist_map[norm_name] = new_row
                new_artists_added += 1
                status_genre = f" ({m_genre})" if m_genre else ""
                print(f"    ✅ Registrado: '{name}' → {res_pl}{status_genre}")

        # 4. Final pass to update counts for ALL tracked artists and check staleness
        print("\n  Updating song counts and checking staleness for all tracked artists...")
        now = datetime.now()
        for row in all_artists:
            aname = row.get('Artist Name')
            if not aname: continue
            norm_name = self._normalize(aname)
            
            # Sync count
            total_songs = artist_counts.get(norm_name, 0)
            inbox_songs = inbox_counts.get(norm_name, 0)
            if str(row.get("Song Count")) != str(total_songs):
                row["Song Count"] = total_songs

            # Sync Playlist: Update to majority if it changed
            if total_songs > 0:
                pl_data = artist_pl_matrix.get(norm_name, {})
                if pl_data:
                    best_pl = max(pl_data, key=pl_data.get)
                    old_pl = row.get("Playlist", "").strip()
                    if best_pl and old_pl != best_pl and row.get("Status") != "Archived":
                        print(f"    🔄 Artist '{aname}': Playlist changed {old_pl} -> \033[1;94m{best_pl}\033[0m (Majority)")
                        row["Playlist"] = best_pl

            # ARCHIVE LOGIC: If no songs in catalog AND no songs in Inbox (#), archive artist
            if total_songs == 0 and inbox_songs == 0 and row.get("Status") != "Archived":
                print(f"    \033[91m⚠ Artist '{aname}' has 0 active songs (Catalog & Inbox).\033[0m")
                row["Status"] = "Archived"
                # Consistent with remove_artist: clear tracking data
                row["Last Checked"] = ""
                row["Playlist"] = ""
                print(f"    ✅ Status updated to 'Archived'.")
            
            # Check staleness (Last Checked > 1 year)
            lc_str = row.get('Last Checked')
            if lc_str:
                try:
                    lc_date = datetime.strptime(lc_str, "%d/%m/%Y")
                    # Using 365 days as 1 year
                    if (now - lc_date).days > 365 and row.get('Status') != 'Pending':
                        print(f"\n\033[1;95m⌛ Artista 'estancado': '{aname}'\033[0m")
                        print(f"    Última revisión: \033[1m{lc_str}\033[0m (Hace más de 1 año)")
                        print(f"    Estado actual: {row.get('Status')}")
                        ans = input(f"    ¿Quieres cambiar su estado a 'Pending'? (s/n): ").strip().lower()
                        if ans == 's':
                            row['Status'] = 'Pending'
                            print(f"    ✅ Estado actualizado a 'Pending'.")
                except ValueError:
                    # Ignore invalid date formats
                    pass


        # 5. Save back
        print(f"\n\033[1;92m✔ Saving {len(all_artists)} artists to Google Sheets...\033[0m")
        self.sheets.save_artists(all_artists)
        print(f"✅ Finished! Added {new_artists_added} new artists and updated counts for the rest.")

    def _add_tracks_to_inbox(self, playlist_id, tracks):
        """Helper to add a batch of tracks to the YouTube Music Inbox and local storage."""
        if not tracks:
            return 0
            
        try:
            # Deduplicate by Video ID to prevent whole batch failing if one is duplicate or suggested twice
            vids = list(dict.fromkeys([s['Video ID'] for s in tracks if s.get('Video ID')]))
            print(f"  Añadiendo {len(vids)} canciones únicas a tu playlist Inbox '#' en YouTube Music...")
            
            res = self.yt.add_playlist_items(playlist_id, vids)
            
            # Check status: some versions return a dict. If it failed, don't update Excel yet.
            if res and isinstance(res, dict) and res.get('status') == "STATUS_FAILED":
                print(f"  ✗ Error: YouTube rechazó la adición (posibl. duplicados o límite).")
                return 0
            
        except Exception as e:
            print(f"  ✗ Error añadiendo a la playlist de YouTube: {e}")
            return 0

        # 2. Add to Excel only if YouTube succeeded
        print(f"  Guardando {len(tracks)} canciones en el Excel...")
        self.sheets.add_to_songs_batch(tracks)
        return len(tracks)

    def check_new_releases(self, playlist_id, force=False, target_artist_name=None, target_artist_id=None, clear_empty=False, interactive=False, skip_summary=False):
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
            
        if interactive and not skip_summary:
            self._print_artist_catalog_summary(target_artist_name)
            
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
        total_added = 0
        
        import re
        catalog_candidates = []

        # 1. Incluimos las "Top Songs" directamente como candidatos de catálogo
        top_songs = artist_data.get('songs', {}).get('results', [])
        for track in top_songs:
            vid = track.get('videoId')
            track_title = track.get('title', '')
            norm_artist = self._normalize(target_artist_name)
            norm_title = self._normalize(track_title)
            track_key = f"{norm_artist} - {norm_title}"

            if vid and vid not in existing_vids and track_key not in existing_keys:
                track['Artist'] = target_artist_name
                track['Title'] = track_title
                track['AlbumTitle'] = (track.get('album') or {}).get('name', 'Top Song')
                catalog_candidates.append(track)

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
                # Cogemos hasta 5 para tener más variedad en el top final
                catalog_candidates.extend(missing_tracks[:5])
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
                    user_scrobbles = int(t.get('Scrobble', 0))
                    listeners_fmt = f"{listeners:,}".replace(",", ".")
                    ans = input(f"      - \033[1;96m{target_artist_name}\033[0m \033[90m-\033[0m \033[1;92m{t.get('title')}\033[0m \033[90m[{listeners_fmt}🎧 | {user_scrobbles}👤]\033[0m. ¿Añadir? [\033[92mS\033[0m/n/q]: ").strip().lower()
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


        # Añadimos las canciones de lanzamientos recientes antes de preguntar por el catálogo
        if interactive and new_batch:
            total_added += self._add_tracks_to_inbox(playlist_id, new_batch)
            new_batch = []

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
                
                # Ordenar por oyentes y coger los 5 mejores (antes 3)
                top_catalog = sorted(deduped_candidates, key=lambda x: int(x.get('LastfmScrobble', 0)), reverse=True)[:5]
                
                print(f"    \033[95m📜 Joyas del catálogo antiguo (Top Popular):\033[0m")
                for t in top_catalog:
                    listeners = int(t.get('LastfmScrobble', 0))
                    user_scrobbles = int(t.get('Scrobble', 0))
                    listeners_fmt = f"{listeners:,}".replace(",", ".")
                    ans = input(f"      - \033[1;96m{target_artist_name}\033[0m \033[90m-\033[0m \033[1;92m{t.get('title')}\033[0m \033[90m({t.get('AlbumYear')}) [{listeners_fmt}🎧 | {user_scrobbles}👤]\033[0m. ¿Añadir? [\033[92mS\033[0m/n/q]: ").strip().lower()
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
            total_added += self._add_tracks_to_inbox(playlist_id, new_batch)
            
        if total_added == 0:
            print("  Ninguna canción destacada o nueva que añadir para este artista.")
        
        return total_added


    def sync_pending_playlist(self, threshold=None):
        print("\n" + "━"*50)
        title_suffix = f" (<= {threshold} reproducciones)" if threshold is not None else " (Solo limpieza)"
        print(f"📋 REVISIÓN DE CANCIONES PENDIENTES{title_suffix}")
        print("━"*50)
        
        pl_name = "Pendiente"
        target_pid = self._resolve_playlist_id(pl_name)
        if not target_pid:
            print(f"  📝 Creando playlist '{pl_name}' en YouTube Music...")
            target_pid = self.yt.create_playlist(pl_name, "Canciones con pocas reproducciones para revisar")
            if not target_pid:
                print("  \033[91m✗ Error creando la playlist.\033[0m")
                return
                
        print(f"  Obteniendo canciones actuales de la playlist '{pl_name}'...")
        try:
            current_items = self.yt.get_playlist_items(target_pid, limit=None)
        except Exception:
            current_items = []
        current_vids = {it.get('videoId'): it for it in current_items if it.get('videoId')}
        
        all_songs = self.sheets.get_songs_records()
        to_remove_from_all_songs = set()
        archived_batch = []
        updated_any_songs = False
        
        # 1. Check for Dislikes in the current playlist
        if current_items:
            print("  Revisando dislikes de la playlist Pendiente...")
            for item in current_items:
                vid = item.get('videoId')
                if not vid: continue
                
                if item.get('likeStatus') == 'DISLIKE':
                    title = item.get('title', 'Unknown')
                    artist = ", ".join([a.get('name', '') for a in item.get('artists', [])])
                    print(f"    \033[91m✗ Dislike detectado:\033[0m \033[92m{artist} - {title}\033[0m")
                    try:
                        self.yt.remove_playlist_items(target_pid, [item])
                        self.yt.rate_song(vid, 'INDIFFERENT')
                    except Exception as e:
                        print(f"      ⚠ Error actualizando YouTube: {e}")
                    
                    # Check where this song is in the main sheet
                    sheet_matches = [s for s in all_songs if s.get('Video ID') == vid]
                    if sheet_matches:
                        for s in sheet_matches:
                            original_pl = s.get('Playlist')
                            
                            # Proactivamente intentamos eliminar de la original si podemos resolver su id
                            if original_pl and original_pl != '#':
                                orig_pid = self._resolve_playlist_id(original_pl)
                                if orig_pid:
                                    try:
                                        orig_items = self.yt.get_playlist_items(orig_pid, limit=1000)
                                        it_to_remove = [i for i in orig_items if i.get('videoId') == vid]
                                        if it_to_remove:
                                            self.yt.remove_playlist_items(orig_pid, it_to_remove)
                                    except: pass
                            
                            s_clone = s.copy()
                            # Preparar para archivo
                            archived_batch.append(s_clone)
                    else:
                        # Si no estaba en el sheet, creamos un record base
                        row = {
                            'Playlist': pl_name,
                            'Artist': item.get('Artist', artist),
                            'Title': item.get('Title', title),
                            'Album': (item.get('album', {}) or {}).get('name', ''),
                            'Year': str(item.get('year', '')),
                            'Video ID': vid, 
                            'Scrobble': 0,
                            'LastfmScrobble': 0,
                            'Genre': ''
                        }
                        archived_batch.append(row)
                    
                    to_remove_from_all_songs.add(vid)
                    if vid in current_vids:
                        del current_vids[vid]
                        
                elif item.get('likeStatus') == 'LIKE':
                    title = item.get('title', 'Unknown')
                    artist = ", ".join([a.get('name', '') for a in item.get('artists', [])])
                    print(f"    \033[94m♥ Like detectado:\033[0m \033[92m{artist} - {title}\033[0m")
                    try:
                        self.yt.remove_playlist_items(target_pid, [item])
                        # Se ha dado a Me Gusta, así que lo mantenemos en YouTube como 'LIKE' para tus recomendaciones.
                    except Exception as e:
                        print(f"      ⚠ Error removiendo de YouTube: {e}")
                        
                    sheet_matches = [s for s in all_songs if s.get('Video ID') == vid]
                    for s in sheet_matches:
                        scrobbles_raw = str(s.get('Scrobble', '0')).replace('.', '').replace(',', '').strip()
                        c_scrobbles = int(scrobbles_raw) if scrobbles_raw.isdigit() else 0
                        
                        if c_scrobbles < 4:
                            s['Scrobble'] = 4
                            updated_any_songs = True
                            print(f"      → Scrobbles subidos a 4 en tu hoja para que ya no vuelva a ser evaluada.")
                            
                    if vid in current_vids:
                        del current_vids[vid]

                else:
                    # ── AUTO GRADUATION: Pasó de reproducciones naturalmente ──
                    title = item.get('title', 'Unknown')
                    artist = ", ".join([a.get('name', '') for a in item.get('artists', [])])
                    sheet_matches = [s for s in all_songs if s.get('Video ID') == vid]
                    if sheet_matches:
                        s = sheet_matches[0]
                        scrobbles_raw = str(s.get('Scrobble', '0')).replace('.', '').replace(',', '').strip()
                        c_scrobbles = int(scrobbles_raw) if scrobbles_raw.isdigit() else 0
                        
                        if threshold is not None and c_scrobbles > threshold:
                            print(f"    \033[93m🏆 Graduada ({c_scrobbles} scrobbles):\033[0m \033[92m{artist} - {title}\033[0m")
                            print(f"      → Superó el límite (>{threshold}), eliminando de Pendiente.")
                            try:
                                self.yt.remove_playlist_items(target_pid, [item])
                            except Exception as e:
                                print(f"      ⚠ Error removiendo de YouTube: {e}")
                            
                            if vid in current_vids:
                                del current_vids[vid]
                        
        # 2. Add candidates to Pendiente
        if threshold is not None:
            print(f"  Escaneando catálogo global (<= {threshold} reproducciones)...")
            candidates_to_add = []
            
            for s in all_songs:
                if s.get('Video ID') in to_remove_from_all_songs:
                    continue
                    
                pl = s.get('Playlist', '')
                if pl == '#':
                    continue
                    
                if pl in Config.ARCHIVABLE_PLAYLISTS:
                    continue
                    
                # "solo deberá recorrer las que han sido archivadas y tienen puesto en el título intervalo de años"
                if not re.search(r'\d{4}\s*-\s*\d{4}', pl):
                    continue
                    
                vid = s.get('Video ID')
                if not vid: continue
                
                scrobbles_raw = str(s.get('Scrobble', '0')).replace('.', '').replace(',', '').strip()
                scrobbles = 0
                if scrobbles_raw.isdigit():
                    scrobbles = int(scrobbles_raw)
                    
                if scrobbles <= threshold:
                    if vid not in current_vids:
                        candidates_to_add.append(s)

            # Dedup candidates
            unique_candidates = {}
            for c in candidates_to_add:
                unique_candidates[c.get('Video ID')] = c
            candidates_to_add = list(unique_candidates.values())
            
            # 3. Detectar y limpiar "Likes" residuales en los candidatos nuevos
            if candidates_to_add:
                print("  Comprobando que los nuevos candidatos no tengan 'Me gusta' activo...")
                liked_data = self.yt.get_liked_songs(limit=None)
                liked_vids = {t.get('videoId') for t in liked_data.get('tracks', []) if t.get('videoId')}
                
                for c in candidates_to_add:
                    vid = c.get('Video ID')
                    if vid in liked_vids:
                        artist = c.get('Artist', '')
                        title = c.get('Title', '')
                        print(f"    \033[93m⚠ Quitando 'Me Gusta' (residual/erróneo):\033[0m \033[92m{artist} - {title}\033[0m")
                        try:
                            self.yt.rate_song(vid, 'INDIFFERENT')
                        except Exception as e:
                            print(f"      ✗ Error quitando like: {e}")

            if candidates_to_add:
                print(f"  \033[92m📥 Añadiendo {len(candidates_to_add)} canciones a 'Pendiente'...\033[0m")
                vids_to_add = [c.get('Video ID') for c in candidates_to_add]
                batch_size = 50
                for i in range(0, len(vids_to_add), batch_size):
                    batch = vids_to_add[i:i+batch_size]
                    try:
                        self.yt.add_playlist_items(target_pid, batch)
                    except Exception as e:
                        print(f"    ⚠ Error añadiendo batch: {e}")
                        
            else:
                print("  ✨ Tu playlist 'Pendiente' ya está al día.")
        else:
            print("\n  ⏭ Saltando búsqueda de nuevos candidatos (no se especificó un límite de reproducciones).")

        # Apply changes to sheet
        if to_remove_from_all_songs or updated_any_songs:
            if to_remove_from_all_songs:
                print(f"  Archivando {len(archived_batch)} canciones (Disliked)...")
            else:
                print(f"  Actualizando base de datos local (Likes ajustados a 4)...")
                
            updated_all_songs = [s for s in all_songs if s.get('Video ID') not in to_remove_from_all_songs]
            self.sheets.overwrite_songs(updated_all_songs)
            
            if archived_batch:
                self.sheets.add_to_archived_batch(archived_batch)
            
        print("\n✅ Proceso completado.")


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

    def _load_releases_sync_cache(self):
        try:
            if os.path.exists(Config.RELEASES_SYNC_CACHE_FILE):
                with open(Config.RELEASES_SYNC_CACHE_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _save_releases_sync_cache(self, cache):
        try:
            os.makedirs(os.path.dirname(Config.RELEASES_SYNC_CACHE_FILE), exist_ok=True)
            with open(Config.RELEASES_SYNC_CACHE_FILE, 'w') as f:
                json.dump(cache, f, indent=4)
        except Exception:
            pass

    def _prompt_for_default_playlist(self, name):
        """Asks the user to select a default playlist for an artist."""
        print(f"\n  \033[93m💡 El artista '{name}' no tiene una playlist por defecto asignada.\033[0m")
        print(f"  Selecciona una para futuros syncs automáticos:")
        
        # Opciones basadas en Config.SOURCE_PLAYLISTS (excluyendo Inbox '#')
        options = [p for p in Config.SOURCE_PLAYLISTS if p != '#']
        
        for i, opt in enumerate(options, 1):
            print(f"    {i}. {opt}")
        print(f"    0. Saltear (Dejar en blanco)")
        
        while True:
            ans = input(f"\n  Selecciona una opción [0-{len(options)}]: ").strip()
            if not ans:
                return None
            if ans == '0':
                return ""
            try:
                idx = int(ans)
                if 1 <= idx <= len(options):
                    return options[idx-1]
            except ValueError:
                pass
            print(f"  Entrada no válida. Por favor, introduce un número entre 0 y {len(options)}.")

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
            if status.strip().lower() == "archived":
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

        def _get_deep_sort_date(a):
            norm_n = self._normalize(a.get("Artist Name", ""))
            cached_date = cache.get(norm_n)
            last_checked = a.get("Last Checked")
            
            if cached_date:
                try:
                    return datetime.fromisoformat(cached_date)
                except:
                    pass
            if last_checked:
                try:
                    fmt = "%d/%m/%Y" if '/' in last_checked else "%Y-%m-%d"
                    return datetime.strptime(last_checked, fmt)
                except:
                    pass
            return datetime.min

        to_sync.sort(key=_get_deep_sort_date)
                
        if not to_sync:
            print("✨ Todos los artistas están al día. Nada que sincronizar.")
            print("\033[90m   (Los artistas 'Archived' no se revisan automáticamente. Cámbialos manualmente en el Sheet si quieres reactivarlos.)\033[0m")
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


    def sync_all_artist_releases(self, force=False, interactive=False):
        """Quickly scans all tracked artists for new releases without complex deep sync filters."""
        print(f"\n==================================================")
        print(f"🚀 SYNCING ALL ARTIST RELEASES (Force: {force})")
        print(f"==================================================\n")

        # Filtrar artistas por fecha (solo si NO es force)
        all_artists = self.sheets.get_artists()
        now = datetime.now()
        
        # Cargamos cache local de releases (7 días)
        releases_cache = self._load_releases_sync_cache()
        
        artists = []
        for a in all_artists:
            name = a.get("Artist Name")
            if a.get("Status", "").strip().lower() == "archived":
                continue
            last_checked = a.get("Last Checked")
            
            # Prioridad 1: Cache local (más fiable en reinicios rápidos)
            cached_date = releases_cache.get(name)
            if not force and cached_date:
                try:
                    d = datetime.strptime(cached_date, "%Y-%m-%d")
                    if (now - d).days < Config.RELEASES_SYNC_CACHE_DAYS:
                        continue
                except:
                    pass

            # Prioridad 2: Fecha en Sheets (para sincronización entre dispositivos/versiones antiguas)
            if not force and last_checked:
                try:
                    # Admite formato d/m/Y o Y-m-d por si acaso
                    fmt = "%d/%m/%Y" if '/' in last_checked else "%Y-%m-%d"
                    d = datetime.strptime(last_checked, fmt)
                    if (now - d).days < Config.RELEASES_SYNC_CACHE_DAYS:
                        continue
                except:
                    pass
            
            artists.append(a)

        # Ordenamos los artistas pendientes para procesar primero los MÁS ANTIGUOS
        # Esto asegura un ciclo continuo donde siempre retomas por el artista que llevas más tiempo sin revisar.
        def _get_sort_date(a):
            last_checked = a.get("Last Checked")
            cached_date = releases_cache.get(a.get("Artist Name"))
            
            if cached_date:
                try:
                    return datetime.strptime(cached_date, "%Y-%m-%d")
                except:
                    pass
            if last_checked:
                try:
                    fmt = "%d/%m/%Y" if '/' in last_checked else "%Y-%m-%d"
                    return datetime.strptime(last_checked, fmt)
                except:
                    pass
            return datetime.min
            
        if not force:
            artists.sort(key=_get_sort_date)

        if not artists:
            print("✨ Todos tus artistas están al día. Nada que sincronizar hoy.")
            return

        added_total = 0
        for idx, a in enumerate(artists, 1):
            name = a.get("Artist Name")
            
            last_checked = a.get("Last Checked", "Nunca")
            print(f"  ⌛ [{idx}/{len(artists)}] Checking \033[1m{name}\033[0m... (Última vez: {last_checked})")
            
            # --- NUEVO PROMPT PRE-SINCRONIZACIÓN ---
            if interactive:
                # Mostramos un breve resumen antes de preguntar
                self._print_artist_catalog_summary(name)
                
                while True:
                    ans = input(f"\n  \033[1;93m🔍 Artista: '{name}'. ¿Qué quieres hacer?\033[0m (\033[92m[S]incronizar\033[0m | \033[91m[a]rchivar\033[0m | [p]asar | [q]uit): ").strip().lower()
                    if not ans: ans = 's'
                    if ans in ['s', 'a', 'p', 'q']: break
                    print("  Por favor responde con s/a/p/q.")
                
                if ans == 'q':
                    print("\n🛑 Sincronización detenida por el usuario.")
                    break
                elif ans == 'p':
                    print(f"  ⏭ Saltando '{name}' por ahora (actualizando fecha).")
                    self.sheets.update_artist_last_checked(name, now.strftime("%d/%m/%Y"))
                    releases_cache[name] = now.strftime("%Y-%m-%d")
                    self._save_releases_sync_cache(releases_cache)
                    continue
                elif ans == 'a':
                    print(f"  \033[91m📦 Archivando artista:\033[0m \033[1m{name}\033[0m")
                    self.sheets.update_artist_status(name, "Archived")
                    # Marcamos como chequeado para que no estorbe si se desarchiva pronto
                    self.sheets.update_artist_last_checked(name, now.strftime("%d/%m/%Y"))
                    releases_cache[name] = now.strftime("%Y-%m-%d")
                    self._save_releases_sync_cache(releases_cache)
                    continue
                # Si es 's', continúa al check_new_releases

            count = self.check_new_releases(
                Config.PLAYLIST_ID, 
                force=force, 
                target_artist_name=name, 
                target_artist_id=a.get("Artist ID"),
                interactive=interactive,
                skip_summary=True
            )

            if count == -1:
                print("\n🛑 Sincronización interrumpida. Puedes continuar otro día.")
                break

            # Actualizamos metadatos de escaneo SIEMPRE que se haya completado el proceso
            self.sheets.update_artist_last_checked(name, now.strftime("%d/%m/%Y"))
            self.sheets.update_artist_status(name, "Done")
            
            # Actualizamos cache local inmediatamente para poder reanudar tras interrupción
            releases_cache[name] = now.strftime("%Y-%m-%d")
            self._save_releases_sync_cache(releases_cache)

            if count > 0:
                added_total += count

            # --- NUEVO PROMPT POST-SINCRONIZACIÓN ---
            if interactive:
                while True:
                    ans = input(f"\n  \033[1;93m🎯 Artista completado. ¿Siguiente paso?\033[0m (\033[92m[C]ontinuar\033[0m | \033[91m[a]rchivar\033[0m | [q]uit): ").strip().lower()
                    if not ans: ans = 'c'
                    if ans in ['c', 'a', 'q']: break
                    print("  Por favor responde con c, a, o q.")
                
                if ans == 'q':
                    print("\n🛑 Sincronización detenida por el usuario.")
                    break
                elif ans == 'a':
                    print(f"  \033[91m📦 Archivando artista:\033[0m \033[1m{name}\033[0m")
                    self.sheets.update_artist_status(name, "Archived")
                    print(f"  \033[90m  → '{name}' ya no aparecerá en los syncs automáticos.\033[0m")

        print(f"\n✅ Finished. Total new songs found across all artists: {added_total}")


    def sync_global_new_releases(self, interactive=False):
        """Scans the global YouTube Music 'New Releases' shelf for tracked artists."""
        print("\n" + "="*50)
        print("🌍 SCANNING GLOBAL NEW RELEASES (YouTube Music Explore)")
        print("="*50)

        artists = self.sheets.get_artists()
        tracked_ids = {a.get('Artist ID') for a in artists if a.get('Artist ID') and a.get('Status', '').strip().lower() != 'archived'}
        tracked_names = {self._normalize(a.get('Artist Name')) for a in artists if a.get('Status', '').strip().lower() != 'archived'}
        
        print(f"   Tracking {len(tracked_ids)} artists with IDs and {len(tracked_names)} names.")
        print("   Fetching new releases from YouTube Explore...")
        
        global_albums = self.yt.get_new_releases()
        if not global_albums:
            print("   ✗ Could not fetch global new releases shelf.")
            return

        print(f"   Found {len(global_albums)} albums in the global shelf.")
        matches = []
        for album in global_albums:
            album_artists = album.get('artists', [])
            matched_artist = None
            for art in album_artists:
                if art.get('id') in tracked_ids or self._normalize(art.get('name')) in tracked_names:
                    matched_artist = art.get('name')
                    break
            if matched_artist:
                matches.append((matched_artist, album))

        if not matches:
            print("   ✨ No new releases found from your tracked artists in the global shelf.")
            return

        print(f"\n   \033[1;92m🎯 Found {len(matches)} relevant new releases!\033[0m")
        added_total = 0
        existing_vids = self.sheets.get_all_video_ids()
        existing_vids.update(self.sheets.get_archived_vids())
        
        existing_keys = set()
        for r in self.sheets.get_songs_records() + self.sheets.get_archived_records():
            art = self._normalize(r.get('Artist', ''))
            tit = self._normalize(r.get('Title', ''))
            existing_keys.add(f"{art} - {tit}")

        # Track if we have already checked an artist to update their date efficiently at the end
        artists_checked_today = set()
        
        for art_name, album in matches:
            browse_id = album.get('browseId')
            if not browse_id: continue
            
            # Record that we process this artist match
            artists_checked_today.add(self._normalize(art_name))

            print(f"\n   💿 processing \033[1;96m{art_name}\033[0m - \033[1;94m{album.get('title')}\033[0m...")
            try:
                album_detail = self.yt.yt.get_album(browse_id)
            except Exception as e:
                print(f"      ✗ Error fetching album details: {e}")
                continue

            tracks = album_detail.get('tracks', [])
            album_title = album.get('title')
            album_year = str(album_detail.get('year', ''))
            
            candidate_tracks = []
            for t in tracks:
                vid = t.get('videoId')
                title = t.get('title')
                key = f"{self._normalize(art_name)} - {self._normalize(title)}"
                
                if vid and vid not in existing_vids and key not in existing_keys:
                    # ✅ NEW FILTER: Only pull songs from the LAST 7 DAYS
                    upload_date_str = self.yt.get_song_upload_date(vid)
                    if upload_date_str:
                        upload_date = datetime.fromisoformat(upload_date_str)
                        days_diff = (datetime.now() - upload_date).days
                        if days_diff > 7:
                            # Skip if older than 7 days
                            # print(f"      - Skipping '{title}' (released {days_diff} days ago)")
                            continue
                    
                    t['Artist'] = art_name
                    t['Title'] = title
                    candidate_tracks.append(t)
            
            if not candidate_tracks:
                # Still updated above with artists_checked_today to reflect we saw their listing
                continue

            # Enriquecemos con Last.fm siempre para tener los metadatos (Género, Scrobbles...)
            # aunque solo usemos los listeners para el prompt en interactivo
            print(f"    🔎 Buscando popularidad y género en Last.fm para {len(candidate_tracks)} pistas...")
            self.lastfm.enrich_songs(candidate_tracks, force_scrobbles=False)

            if interactive:
                # Ordenar por popularidad
                candidate_tracks = sorted(candidate_tracks, key=lambda x: int(x.get('LastfmScrobble', 0)), reverse=True)

                print(f"    \033[1;95m📀 {art_name} \033[0m» \033[1;94m'{album_title}'\033[0m \033[90m({album_year})\033[0m")
                to_add_this_album = []
                for t in candidate_tracks:
                    listeners = int(t.get('LastfmScrobble', 0))
                    user_scrobbles = int(t.get('Scrobble', 0))
                    listeners_fmt = f"{listeners:,}".replace(",", ".")
                    ans = input(f"      - \033[1;96m{art_name}\033[0m \033[90m-\033[0m \033[1;92m{t.get('Title')}\033[0m \033[90m[{listeners_fmt}🎧 | {user_scrobbles}👤]\033[0m. ¿Añadir? [\033[92mS\033[0m/n/q]: ").strip().lower()
                    if ans == 'q':
                        print("\n🛑 Sincronización cancelada por el usuario.")
                        return
                    if ans != 'n':
                        to_add_this_album.append(t)
                
                final_new_songs = []
                for t in to_add_this_album:
                    final_new_songs.append({
                        'Playlist': '#',
                        'Artist': art_name,
                        'Title': t.get('Title'),
                        'Album': album_title,
                        'Year': album_year,
                        'Genre': t.get('Genre', ''),
                        'Scrobble': t.get('Scrobble', 0),
                        'LastfmScrobble': t.get('LastfmScrobble', 0),
                        'Video ID': t.get('videoId')
                    })
            else:
                final_new_songs = []
                for t in candidate_tracks:
                    print(f"      + New track: {t.get('Title')}")
                    final_new_songs.append({
                        'Playlist': '#',
                        'Artist': art_name,
                        'Title': t.get('Title'),
                        'Album': album_title,
                        'Year': album_year,
                        'Genre': t.get('Genre', ''),
                        'Scrobble': t.get('Scrobble', 0),
                        'LastfmScrobble': t.get('LastfmScrobble', 0),
                        'Video ID': t.get('videoId')
                    })

            if final_new_songs:
                try:
                    self.yt.add_playlist_items(Config.PLAYLIST_ID, [s['Video ID'] for s in final_new_songs])
                    self.sheets.add_to_songs_batch(final_new_songs)
                    added_total += len(final_new_songs)
                    
                    # We update the artist objects in the local cache
                    # (Final save happens at the end of the global loop)
                    for s in final_new_songs:
                        existing_vids.add(s['Video ID'])
                except Exception as e:
                    print(f"      ✗ Error añadiendo canciones: {e}")

        # Final update of all artist metadata (Status + Last Checked)
        # We update Status to 'Done' and Last Checked to 'Today' for ANY artist matched on the shelf
        # regardless of whether we added songs or not (since we've processed their fresh metadata).
        all_artists = self.sheets.get_artists()
        updated_any = False
        today_str = datetime.now().strftime("%d/%m/%Y")

        for a in all_artists:
            norm_a = self._normalize(a.get("Artist Name", ""))
            if norm_a in artists_checked_today:
                a["Last Checked"] = today_str
                a["Status"] = "Done"
                updated_any = True
        
        if updated_any or added_total > 0:
            print(f"\n   \033[1;94m💾 Saving artist status and new songs to spreadsheet...\033[0m")
            self.sheets.save_artists(all_artists)


        print(f"\n\033[1;92m✅ Global scan complete. Added {added_total} new songs.\033[0m")

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
            # La biblioteca actual ahora se muestra dentro de check_new_releases para mayor consistencia
            pass
        
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
        
        should_check_playlist = False
        if not is_archived:
            self.sheets.update_artist_status(name, "Done")
            should_check_playlist = True
        else:
            # Si era un artista archivado, le preguntamos si quiere reactivarlo
            print(f"\n  \033[93m💡 Este artista estaba 'Archived'.\033[0m")
            reactivate = input(f"  ¿Quieres cambiar su estado a 'Done' para que salga en futuros syncs normales? [y/N]: ").strip().lower()
            if reactivate == 'y':
                print(f"  \033[92m✓ Artista reactivado como 'Done'.\033[0m")
                self.sheets.update_artist_status(name, "Done")
                should_check_playlist = True
            else:
                print(f"  \033[90m• Se mantiene como 'Archived'.\033[0m")

        # COMPROBACIÓN DE PLAYLIST POR DEFECTO
        # Si el artista no tiene playlist asignada y va a estar activo (Done), preguntamos.
        if should_check_playlist:
            # Buscamos el registro más actual en memoria a través de sheets service
            artists_in_memory = self.sheets.get_artists()
            # Intentamos encontrar el registro actualizado (que puede tener la playlist)
            current_row = next((a for a in artists_in_memory if a.get("Artist Name") == name), artist)
            
            if not current_row.get("Playlist", "").strip():
                new_pl = self._prompt_for_default_playlist(name)
                if new_pl is not None:
                    print(f"  \033[92m✓ Playlist '{new_pl}' asignada a {name}.\033[0m")
                    self.sheets.update_artist_playlist(name, new_pl)
                    # Actualizamos el objeto local por si se usa más adelante en esta función
                    artist["Playlist"] = new_pl

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

    def split_playlist_by_year(self, playlist_name, start_year, end_year):
        """Splits a playlist into a new year-based archive interval.
        
        1. Updates the archiving configuration.
        2. Moves songs from any related playlist (base or old archives) to the new interval playlist.
        3. Updates the Google Sheet records.
        """
        import re
        if playlist_name == "#":
            print("  \033[91m✗ Error: No se permite dividir la playlist de Inbox '#'.\033[0m")
            return

        print(f"\n\033[96m" + "━"*50 + "\033[0m")
        print(f"\033[1;96m✂ GLOBAL SPLITTING: {playlist_name} ({start_year}-{end_year})\033[0m")
        print("\033[96m" + "━"*50 + "\033[0m")

        # 1. Check for Overlaps and Update Config
        if playlist_name not in self._archiving_config:
            self._archiving_config[playlist_name] = []
        
        new_interval = [int(start_year), int(end_year)]
        
        # Check for overlaps
        for existing_s, existing_e in self._archiving_config[playlist_name]:
            if max(start_year, existing_s) <= min(end_year, existing_e):
                if [start_year, end_year] == [existing_s, existing_e]:
                    continue  # Es el mismo, está bien (reagrupación global)
                print(f"  \033[93m⚠️ Advertencia: El nuevo rango {start_year}-{end_year} solapa con el existente {existing_s}-{existing_e}.\033[0m")
        if new_interval not in self._archiving_config[playlist_name]:
            self._archiving_config[playlist_name].append(new_interval)
            self._archiving_config[playlist_name].sort(key=lambda x: x[0])
            self._save_archiving_config()
            print(f"  ✓ Configuración actualizada: {playlist_name} -> {self._archiving_config[playlist_name]}")
        else:
            print(f"  ℹ El intervalo {start_year}-{end_year} ya existe para '{playlist_name}'.")

        target_name = f"{playlist_name} ({start_year}-{end_year})"
        
        # 2. Identificar TODAS las playlists relacionadas en YouTube (Principal + Archivos existentes/huérfanos)
        related_playlists = [playlist_name]
        related_pids = {} # {nombre: pid}
        try:
            # Buscamos en la biblioteca todas las playlists que sigan el patrón Nombre (...)
            search_results = self.yt.yt.search(playlist_name, filter='playlists', scope='library')
            prefix = f"{playlist_name} ("
            for r in search_results:
                title = r.get('title', '')
                pid = r.get('playlistId') or r.get('browseId', '').replace('VL', '')
                if not pid: continue
                
                if title == playlist_name:
                    related_pids[title] = pid
                elif title.startswith(prefix) and title.endswith(")"):
                    related_pids[title] = pid
                    if title != target_name: 
                        related_playlists.append(title)
            
            # 3. Resolve/Create Target Playlist
            target_pid = related_pids.get(target_name) or self._resolve_playlist_id(target_name)
            if not target_pid:
                print(f"  📝 Creando playlist de destino '{target_name}'...")
                target_pid = self.yt.create_playlist(target_name, f"Archivo {playlist_name}: {start_year}-{end_year}")
                if not target_pid:
                    print(f"  \033[91m✗ Error creando playlist '{target_name}'.\033[0m")
                    return
            related_pids[target_name] = target_pid

            # 4. Identify songs to move (from Sheet)
            all_songs = self.sheets.get_songs_records()
            move_map = {} # {playlist_source_name: [song_records]}
            
            for s in all_songs:
                current_pl = s.get('Playlist')
                if current_pl in related_playlists and current_pl != target_name:
                    y = str(s.get('Year', '')).strip()
                    if y:
                        match = re.search(r'(\d{4})', y)
                        if match:
                            year = int(match.group(1))
                            if start_year <= year <= end_year:
                                if current_pl not in move_map:
                                    move_map[current_pl] = []
                                move_map[current_pl].append(s)

            if not move_map:
                print(f"  ℹ No hay nuevas canciones para mover a '{target_name}' desde las playlists analizadas.")
            else:
                total_to_move = sum(len(songs) for songs in move_map.values())
                print(f"  ➕ Movimiento detectado: {total_to_move} canciones desde {len(move_map)} fuentes.")

                # 5. Execute moves in YouTube Music and Sheet
                for source_name, songs in move_map.items():
                    print(f"  📦 Procesando origen: '{source_name}' ({len(songs)} canciones)...")
                    source_pid = related_pids.get(source_name) or self._resolve_playlist_id(source_name)
                    vids = [s.get('Video ID') for s in songs if s.get('Video ID')]
                    
                    if not vids: continue

                    # Add to Target
                    self.yt.add_playlist_items(target_pid, vids)
                    
                    # Remove from Source
                    if source_pid:
                        source_items = self.yt.get_playlist_items(source_pid, limit=2000)
                        vid_to_items = {}
                        for it in source_items:
                            v = it.get('videoId')
                            if v not in vid_to_items: vid_to_items[v] = []
                            vid_to_items[v].append(it)
                        
                        items_to_remove = []
                        for v in vids:
                            if v in vid_to_items and vid_to_items[v]:
                                items_to_remove.append(vid_to_items[v].pop(0))
                        
                        if items_to_remove:
                            self.yt.remove_playlist_items(source_pid, items_to_remove)
                            print(f"    ✅ YT: Movidas de '{source_name}' a '{target_name}'.")
                    
                    # Quitar Likes (siempre que se archiva)
                    for v in vids:
                        self.yt.rate_song(v, 'INDIFFERENT')
                    
                    # Update Sheet records in memory
                    for s in songs:
                        s['Playlist'] = target_name

            # 6. Limpieza final: Eliminar playlists de archivo que ya no están en config y están vacías
            print(f"  🧹 Revisando limpieza de archivos obsoletos...")
            current_archives = {f"{playlist_name} ({s}-{e})" for s, e in self._archiving_config.get(playlist_name, [])}
            for pl_candidate, pid in related_pids.items():
                if pl_candidate == playlist_name or pl_candidate == target_name:
                    continue
                
                if pl_candidate.startswith(f"{playlist_name} (") and pl_candidate not in current_archives:
                    items = self.yt.get_playlist_items(pid, limit=1)
                    if not items:
                        print(f"    🗑  Eliminando playlist obsoleta y vacía: '{pl_candidate}'...")
                        self.yt.delete_playlist(pid)

            # Commit sheet changes
            self.sheets.overwrite_songs(all_songs)
            print(f"  ✅ Proceso de división global finalizado.")

        except Exception as e:
            print(f"  \033[91m✗ Error durante el movimiento global: {e}\033[0m")

    def rebalance_playlist_archives(self, playlist_name):
        """Redistributes ALL songs in the pool (base + archives) according to current buckets."""
        import re
        print(f"\n🔄 REBALANCEANDO ARCHIVOS PARA: {playlist_name}...")
        
        # 1. Discover ALL current related playlists in YT
        related_pids = {} # {nombre: pid}
        try:
            search_results = self.yt.yt.search(playlist_name, filter='playlists', scope='library')
            prefix = f"{playlist_name} ("
            for r in search_results:
                title = r.get('title', '')
                pid = r.get('playlistId') or r.get('browseId', '').replace('VL', '')
                if not pid: continue
                if title == playlist_name or (title.startswith(prefix) and title.endswith(")")):
                    related_pids[title] = pid
        except:
            pass
            
        if playlist_name not in related_pids:
            pid = self._resolve_playlist_id(playlist_name)
            if pid: related_pids[playlist_name] = pid

        # 2. Identify all songs in Sheet the belong to this collection
        all_songs = self.sheets.get_songs_records()
        moves_needed = [] # List of (song_record, source_name, target_name)
        
        registered_archives = {f"{playlist_name} ({s}-{e})" for s, e in self._archiving_config.get(playlist_name, [])}
        
        for s in all_songs:
            current_pl = s.get('Playlist', '')
            is_pool = current_pl == playlist_name or (current_pl.startswith(playlist_name + " (") and current_pl.endswith(")"))
            if not is_pool: continue
            
            y_str = str(s.get('Year', '')).strip()
            year = 0
            if y_str:
                match = re.search(r'(\d{4})', y_str)
                if match: year = int(match.group(1))
            
            correct_pl = self.get_target_playlist_by_year(playlist_name, year)
            if current_pl != correct_pl:
                moves_needed.append((s, current_pl, correct_pl))
        
        if not moves_needed:
            print(f"  ✨ Todo está en su sitio. No se requieren movimientos.")
            return

        print(f"  📦 Se han detectado {len(moves_needed)} canciones fuera de lugar.")
        
        # 3. Execute moves
        sources = sorted(list(set(m[1] for m in moves_needed)))
        for source_name in sources:
            source_pid = related_pids.get(source_name) or self._resolve_playlist_id(source_name)
            source_moves = [m for m in moves_needed if m[1] == source_name]
            
            targets = sorted(list(set(m[2] for m in source_moves)))
            for target_name in targets:
                target_songs = [m[0] for m in source_moves if m[2] == target_name]
                vids = [s.get('Video ID') for s in target_songs if s.get('Video ID')]
                
                print(f"    ➡️ Moviendo {len(vids)} canciones: '{source_name}' -> '{target_name}'...")
                target_pid = related_pids.get(target_name) or self._resolve_playlist_id(target_name)
                if not target_pid:
                    target_pid = self.yt.create_playlist(target_name)
                
                if not target_pid:
                    print(f"      ✗ Error: No se pudo resolver o crear '{target_name}'.")
                    continue
                
                # Actualizar catálogo para asegurar limpieza posterior
                related_pids[target_name] = target_pid
                related_pids[source_name] = source_pid # Registrar la fuente también

                self.yt.add_playlist_items(target_pid, vids)
                if source_pid:
                    # Remove from source
                    source_items = self.yt.get_playlist_items(source_pid, limit=2000)
                    vid_to_items = {}
                    for it in source_items:
                        v = it.get('videoId')
                        if v not in vid_to_items: vid_to_items[v] = []
                        vid_to_items[v].append(it)
                    
                    items_to_remove = []
                    for v in vids:
                        if v in vid_to_items and vid_to_items[v]:
                            items_to_remove.append(vid_to_items[v].pop(0))
                    
                    if items_to_remove:
                        self.yt.remove_playlist_items(source_pid, items_to_remove)

                for s in target_songs:
                    s['Playlist'] = target_name

        # 4. Persistence: Update Sheet before cleanup
        print(f"  📝 Actualizando columna 'Playlist' en el Sheet para {len(moves_needed)} canciones...")
        self.sheets.overwrite_songs(all_songs)

        # 5. Final Cleanup
        print(f"  🧹 Limpiando posibles archivos vacíos en YouTube Music...")
        for pl_name, pid in related_pids.items():
            if pl_name == playlist_name: continue
            if pl_name in registered_archives: continue
            
            items = self.yt.get_playlist_items(pid, limit=1)
            if not items:
                print(f"    🗑  Eliminando archivo huérfano y vacío: '{pl_name}'...")
                self.yt.delete_playlist(pid)

        print(f"  ✅ Rebalanceo completado.")

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
            # If a specific playlist is requested, we process it regardless of Config.ARCHIVABLE_PLAYLISTS
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
            library_playlists = self.yt.yt.get_library_playlists(limit=500)
        except Exception as e:
            print(f"\033[91m✗ Error obteniendo playlists de la biblioteca: {e}\033[0m")
            return

        for lp in library_playlists:
            lp_title = lp.get('title', '')
            pid = lp.get('playlistId', '')
            if lp_title and pid:
                resolved_ids[lp_title.lower()] = pid

        total_moved = 0
        total_restored = 0

        for pl_name in playlists_to_process:
            archive_name = f"{pl_name} $"
            pl_lower = pl_name.lower()
            archive_lower = archive_name.lower()

            original_pid = resolved_ids.get(pl_lower)
            archive_pid = resolved_ids.get(archive_lower)
            
            if not original_pid:
                print(f"\n  \033[91m✗ No se encontró la playlist '{pl_name}' en YouTube Music.\033[0m")
                continue

            # --- A. ENCONTRAR CANDIDATOS PARA ARCHIVAR (Main -> Archive) ---
            to_archive = []
            for s in all_songs:
                if s.get('Playlist', '').lower() != pl_lower: continue
                song_year = str(s.get('Year', '')).strip()
                try:
                    if song_year and int(song_year) <= year:
                        to_archive.append(s)
                except: pass

            # --- B. ENCONTRAR CANDIDATOS PARA RESTAURAR (Archive -> Main) ---
            to_restore = []
            if archive_pid:
                for s in all_songs:
                    if s.get('Playlist', '').lower() != archive_lower: continue
                    song_year = str(s.get('Year', '')).strip()
                    try:
                        if song_year and int(song_year) > year:
                            to_restore.append(s)
                    except: pass

            if not to_archive and not to_restore:
                print(f"\n  \033[90m⏭ '{pl_name}': Sin movimientos necesarios para año {year}.\033[0m")
                continue

            # Mostrar resumen de movimientos
            print(f"\n\033[96m{'━'*50}\033[0m")
            print(f"  \033[1;95m📂 {pl_name}\033[0m \033[90m(Año límite: {year})\033[0m")
            
            if to_archive:
                print(f"  \033[91m📥 Para ARCHIVAR ({len(to_archive)}):\033[0m")
                for s in to_archive[:10]:
                    print(f"    - {s.get('Artist', '')} - {s.get('Title', '')} \033[90m({s.get('Year', '')})\033[0m")
                if len(to_archive) > 10: print(f"    \033[90m... y {len(to_archive)-10} más.\033[0m")

            if to_restore:
                print(f"  \033[92m📤 Para RESTAURAR ({len(to_restore)}):\033[0m")
                for s in to_restore[:10]:
                    print(f"    - {s.get('Artist', '')} - {s.get('Title', '')} \033[90m({s.get('Year', '')})\033[0m")
                if len(to_restore) > 10: print(f"    \033[90m... y {len(to_restore)-10} más.\033[0m")

            ans = input(f"\n  ¿Ejecutar movimientos en '{pl_name}'? [\033[92mS\033[0m/n]: ").strip().lower()
            if ans == 'n': continue

            # Resolver Archive PID si no existe y lo necesitamos
            if to_archive and not archive_pid:
                print(f"  📝 Creando playlist '{archive_name}'...")
                try:
                    archive_pid = self.yt.create_playlist(archive_name, f"Archivo: canciones ≤ {year}")
                    resolved_ids[archive_lower] = archive_pid
                except Exception as e:
                    print(f"  \033[91m✗ Error creando playlist: {e}\033[0m")
                    continue

            # --- EJECUCIÓN A: ARCHIVAR ---
            if to_archive:
                print(f"  ➕ Archivando {len(to_archive)} canciones...")
                # Obtener info de tracks originales para eliminar
                original_tracks = self.yt.get_playlist_items(original_pid, limit=5000)
                vid_to_track = {t.get('videoId'): t for t in original_tracks if t.get('videoId')}
                
                vids = [s.get('Video ID') for s in to_archive]
                self.yt.add_playlist_items(archive_pid, vids)
                
                tracks_to_remove = [vid_to_track[v] for v in vids if v in vid_to_track]
                if tracks_to_remove:
                    self.yt.remove_playlist_items(original_pid, tracks_to_remove)
                
                # Un-like y update sheet cache
                for vid in vids:
                    try: self.yt.rate_song(vid, 'INDIFFERENT')
                    except: pass
                
                vids_set = set(vids)
                for s in all_songs:
                    if s.get('Playlist', '').lower() == pl_lower and s.get('Video ID') in vids_set:
                        s['Playlist'] = archive_name
                total_moved += len(vids)

            # --- EJECUCIÓN B: RESTAURAR ---
            if to_restore:
                print(f"  ➕ Restaurando {len(to_restore)} canciones...")
                # Obtener info de archive tracks para eliminar
                archive_tracks = self.yt.get_playlist_items(archive_pid, limit=5000)
                vid_to_track = {t.get('videoId'): t for t in archive_tracks if t.get('videoId')}
                
                vids = [s.get('Video ID') for s in to_restore]
                self.yt.add_playlist_items(original_pid, vids)
                
                tracks_to_remove = [vid_to_track[v] for v in vids if v in vid_to_track]
                if tracks_to_remove:
                    self.yt.remove_playlist_items(archive_pid, tracks_to_remove)
                
                # Re-like y update sheet cache
                for vid in vids:
                    try: self.yt.rate_song(vid, 'LIKE')
                    except: pass
                
                vids_set = set(vids)
                for s in all_songs:
                    if s.get('Playlist', '').lower() == archive_lower and s.get('Video ID') in vids_set:
                        s['Playlist'] = pl_name
                total_restored += len(vids)

        if total_moved > 0 or total_restored > 0:
            print(f"\n  📝 Actualizando sheet ({total_moved + total_restored} cambios)...")
            self.sheets.overwrite_songs(all_songs)
            print(f"\033[92m✓ Sheet actualizado.\033[0m")

        print(f"\n\033[92m✅ Archivado completado. Archivadas: {total_moved}, Restauradas: {total_restored}.\033[0m")

    def cleanup_inbox_duplicates(self):
        pass







    def audit_fused_artists(self, artists):
        """Scans the current tracking list for artists with separators and asks if they should be ignored."""
        import re
        collab_pattern = re.compile(r'\s*,\s*|(?<!\w)&\s*|\s+vs\.?\s+', re.IGNORECASE)
        
        modified = False
        to_keep = []
        
        for a in artists:
            name = a.get('Artist Name', '')
            status = a.get('Status', '')
            
            # Skip if already marked as Multi or explicitly as a Single entity in the Type column
            if a.get('Type') in ('Multi', 'Single') or not collab_pattern.search(name):
                to_keep.append(a)
                continue
            
            # SUSPECTED FUSION
            print(f"\n\033[1;93m⚠ Artista en seguimiento detectado con múltiples nombres: '{name}'\033[0m")
            print(f"    Estado: {status} | Tipo: {a.get('Type', 'Normal')}")
            print(f"    ¿Qué deseas hacer con este registro?")
            print(f"    - 'i': Marcar como 'Multi' (se enviará a Status: Archived). No se trackeará como uno.")
            print(f"    - 's': MANTENER como un solo artista/banda (Tipo: Single).")
            print(f"    - 'c': Continuar sin cambios (preguntar la próxima vez).")
            
            choice = input(f"    Opción (i/s/c): ").strip().lower()
            
            if choice == 'i':
                a['Type'] = 'Multi'
                a['Status'] = 'Archived'  # Mantenemos los 3 estados del usuario en Status
                to_keep.append(a)
                modified = True
                print(f"    ✅ '{name}' marcado como Multi (fusionado).")
            elif choice == 's':
                a['Type'] = 'Single'
                to_keep.append(a)
                modified = True
                print(f"    ✅ '{name}' confirmado como un solo artista/banda.")
            else:
                to_keep.append(a)
                
        if modified:
            self.sheets.save_artists(to_keep)
            print(f"    ✅ Cambios de auditoría guardados en la hoja 'Artists'.")
        else:
            print("  No se encontraron nuevas fusiones que revisar.")
            
        return to_keep

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
    def sync_genre_summary(self):
        """
        Aggregates all genres from the Songs sheet, counts them,
        and updates the 'Genre' summary sheet. Includes interactive filtering.
        """
        from collections import Counter
        import string
        import json
        import os

        print("\n\033[96m" + "━"*50 + "\033[0m")
        print("\033[1;96m📊 SYNCING GENRE SUMMARY (INTERACTIVE)\033[0m")
        print("\033[96m" + "━"*50 + "\033[0m")

        # 1. Load Preferences
        prefs = {"ignored": [], "approved": []}
        if os.path.exists(Config.GENRE_PREFS_FILE):
            try:
                with open(Config.GENRE_PREFS_FILE, 'r') as f:
                    prefs = json.load(f)
            except Exception as e:
                print(f"  ⚠ Error loading genre preferences: {e}")

        ignored = set(prefs.get("ignored", []))
        approved = set(prefs.get("approved", []))
        needs_save = False

        # 2. Extract and Process Songs
        all_songs = self.sheets.get_songs_records()
        if not all_songs:
            print("  ⚠ No songs found in the 'Songs' sheet.")
            return

        genre_counts = Counter()
        
        # Collect all raw candidate genres (normalized for case)
        raw_candidates = set()
        for s in all_songs:
            genre_str = s.get('Genre', '')
            if not genre_str: continue
            parts = [p.strip() for p in genre_str.split(',') if p.strip()]
            for p in parts:
                raw_candidates.add(string.capwords(p.lower()))

        # 3. Interactive Filter
        print(f"  🔍 Found {len(raw_candidates)} total candidate genres.")
        
        for p in sorted(raw_candidates):
            if p in ignored:
                continue
            if p in approved:
                continue
            
            # Unknown genre! Ask user
            print(f"\n  [?] New genre: '\033[1;95m{p}\033[0m'")
            choice = input("      Track it? (y=Yes, n=No/Skip once, i=Ignore always, q=Quit/Save): ").lower().strip()
            
            if choice == 'y':
                approved.add(p)
                needs_save = True
            elif choice == 'i':
                ignored.add(p)
                needs_save = True
            elif choice == 'q':
                print("  ⏹ Stopping prompt and saving progress...")
                break
            # 'n' or anything else skips this time but stays 'unknown'

        # 4. Filter and Count
        for s in all_songs:
            genre_str = s.get('Genre', '')
            if not genre_str: continue
            parts = [string.capwords(p.strip().lower()) for p in genre_str.split(',') if p.strip()]
            for p in parts:
                if p in approved:
                    genre_counts[p] += 1

        # 5. Save Preferences
        if needs_save:
            prefs["ignored"] = sorted(list(ignored))
            prefs["approved"] = sorted(list(approved))
            with open(Config.GENRE_PREFS_FILE, 'w') as f:
                json.dump(prefs, f, indent=4)
            print(f"  ✓ Updated {os.path.basename(Config.GENRE_PREFS_FILE)}")

        # 6. Update Sheet
        sorted_genres = sorted(
            genre_counts.items(), 
            key=lambda item: (-item[1], item[0])
        )

        print(f"  ✓ Final summary includes {len(sorted_genres)} approved genres.")
        print(f"  📝 Updating 'Genre' sheet...")
        
        self.sheets.overwrite_genre_sheet(sorted_genres)
        print("\033[92m✅ Genre synchronization complete.\033[0m")

    def list_playlists_counts(self):
        """Displays total song counts for each playlist in YT and Sheet."""
        print("\n\033[94m📊 OBTENIENDO ESTADO GLOBAL DE PLAYLISTS...\033[0m")
        
        # 1. Get YouTube counts
        try:
            yt_playlists = self.yt.get_library_playlists()
            yt_data = {p['title'].lower().strip(): p for p in yt_playlists}
        except Exception as e:
            print(f"❌ Error al conectar con YouTube Music: {e}")
            return

        # 2. Get Sheet counts
        try:
            songs_records = self.sheets.get_songs_records()
            from collections import Counter
            sheet_counts = Counter(str(s.get('Playlist', '')).strip() for s in songs_records)
        except Exception as e:
            print(f"❌ Error al conectar con Google Sheets: {e}")
            return

        # 3. Identify the Inbox title in YT
        inbox_id = Config.PLAYLIST_ID
        inbox_title_in_yt = None
        for p in yt_playlists:
            p_id = p.get('playlistId') or p.get('browseId', '').replace('VL', '')
            if p_id == inbox_id:
                inbox_title_in_yt = p['title']
                break

        # 4. Prepare data for display
        all_playlist_names = set(Config.SOURCE_PLAYLISTS)
        for base, intervals in self._archiving_config.items():
            all_playlist_names.add(base)
            for start, end in intervals:
                all_playlist_names.add(f"{base} ({start}-{end})")
        
        for pl_name in sheet_counts.keys():
            if pl_name: all_playlist_names.add(pl_name)

        # Sort names: # first, then alphabetically
        def sort_key(name):
            if name == '#': return '0000_inbox'
            return name.lower()
        
        sorted_names = sorted(list(all_playlist_names), key=sort_key)

        print(f"\n\033[1m{'PLAYLIST':<35} | {'YT':>5} | {'SHEET':>5} | {'STATUS'}\033[0m")
        print("-" * 75)

        mismatched = []
        for pl_name in sorted_names:
            # Resolve YT name
            query_name = pl_name
            if pl_name == '#' and inbox_title_in_yt:
                query_name = inbox_title_in_yt
            
            yt_info = yt_data.get(query_name.lower().strip())
            yt_count = int(yt_info['count']) if yt_info and str(yt_info.get('count', '')).isdigit() else 0
            sheet_count = sheet_counts.get(pl_name, 0)

            diff = yt_count - sheet_count
            status = "\033[92m✅ OK\033[0m"
            
            color_pl = "\033[1m" # Bold
            if yt_count != sheet_count:
                color_pl = "\033[93m" # Yellow warning
                mismatched.append(pl_name)
                if diff > 0:
                    status = f"\033[93m⚠️  Sheet lacks {diff}\033[0m"
                else:
                    status = f"\033[93m⚠️  YT lacks {abs(diff)}\033[0m"
            
            if yt_count == 0 and sheet_count == 0:
                color_pl = "\033[90m"
                status = "\033[90m-\033[0m"

            # Skip empty entries that are not in source playlists
            if yt_count == 0 and sheet_count == 0 and pl_name not in Config.SOURCE_PLAYLISTS:
                continue

            print(f"{color_pl}{pl_name:<35}\033[0m | {yt_count:>5} | {sheet_count:>5} | {status}")
        
        print("-" * 75)
        print(f"\033[90mResumen total: {len(sorted_names)} colecciones rastreadas.\033[0m")
        
        # 5. Interactive correction
        if mismatched:
            print(f"\n\033[93m⚠️  Se han detectado {len(mismatched)} playlists con diferencias: {', '.join(mismatched)}\033[0m")
            confirm = input(f"👉 ¿Deseas corregir SOLO ESTAS {len(mismatched)} lanzando 'playlist sync --skip-lastfm'? (s/n): ").strip().lower()
            if confirm in ['s', 'si', 'y', 'yes']:
                for pl in mismatched:
                    print(f"\n🚀 Sincronizando '{pl}'...")
                    self.sync_playlist(playlist_name=pl, skip_lastfm=True)
                print(f"\n✅ Proceso de corrección finalizado.")
            else:
                print("🛑 Operación de corrección omitida.")
        else:
            print(f"\033[92m✅ Todas las playlists están en sincronía.\033[0m\n")
