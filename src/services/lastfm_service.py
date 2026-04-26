import threading
import time
import json
import os
import pylast
import concurrent.futures
from datetime import datetime, timezone
from ..config import Config


class LastFMService:
    """Service to interact with Last.fm API with persistent caching."""

    def __init__(self):
        self.network = pylast.LastFMNetwork(
            api_key=Config.LASTFM_API_KEY,
            api_secret=Config.LASTFM_API_SECRET,
            username=Config.LASTFM_USERNAME,
        )
        self.username = Config.LASTFM_USERNAME
        self.cache_file = Config.LASTFM_CACHE_FILE
        self.cache = self._load_cache()
        self._call_count = 0
        self._save_interval = 25  # Save cache every N lookups
        self._lock = threading.RLock()

    # ── Cache I/O ──────────────────────────────────────────────

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_cache(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)

    def _cache_key(self, artist, title):
        return f"{str(artist).lower().strip()}||{str(title).lower().strip()}"

    def _cache_is_fresh(self, cached: dict, ttl_days: int) -> bool:
        """Returns True if the cached entry is younger than ttl_days."""
        ts = cached.get("_ts")
        if not ts:
            return False
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).days
            return age < ttl_days
        except Exception:
            return False

    # ── Rate Limiting ──────────────────────────────────────────

    def _throttle(self):
        """Sleep between API calls to stay under Last.fm's 5 req/s limit."""
        time.sleep(0.25)

    # ── Single-call track info via Last.fm REST ─────────────────

    def _normalize_title(self, title: str) -> str:
        """Simplifies title by removing features, remasters, and extra noise."""
        import re
        t = str(title).lower()
        # Remove features: (feat. X), (with X), (con X), [feat X], etc.
        t = re.sub(r'[\(\[](feat|with|con|featuring)\.?\s+.*?[\)\]]', '', t)
        # Remove common noise and versions
        # Matches: (remastered), (early version), (acoustic), (demo), [live], etc.
        t = re.sub(r'[\(\[](remastered|remaster|early version|acoustic|demo|live|instrumental|radio edit|video version|deluxe|bonus track|version|edit)[\)\]]', '', t)
        # Clean extra spaces and punctuation
        t = re.sub(r'[^\w\s]', '', t)
        return " ".join(t.split())

    def _get_track_info_raw(self, artist: str, title: str) -> dict | None:
        """
        Calls track.getInfo with smart consolidation. 
        If the title looks like it has variations (feat, etc), it searches 
        for similar tracks and sums user scrobbles across them.
        """
        try:
            # 1. Start with the exact match
            track = self.network.get_track(artist, title)
            params = track._get_params()
            params["method"] = "track.getInfo"
            params["username"] = self.username
            params["autocorrect"] = "1"

            doc = pylast._Request(self.network, "track.getInfo", params).execute(cacheable=False)
            self._throttle()

            track_el = doc.getElementsByTagName("track")
            if not track_el:
                return None
            t = track_el[0]

            def _text(tag, node=t):
                els = node.getElementsByTagName(tag)
                return els[0].firstChild.nodeValue.strip() if els and els[0].firstChild else "0"

            # Base data from primary match
            playcount = int(_text("playcount") or 0)
            listeners = int(_text("listeners") or 0)
            userplaycount = 0
            user_els = t.getElementsByTagName("userplaycount")
            if user_els and user_els[0].firstChild:
                userplaycount = int(user_els[0].firstChild.nodeValue.strip())

            # Genre/Tags
            genre = ""
            tag_names = []
            tag_els = t.getElementsByTagName("tag")
            for tag_el in tag_els:
                name_els = tag_el.getElementsByTagName("name")
                count_els = tag_el.getElementsByTagName("count")
                if name_els and name_els[0].firstChild:
                    count = int(count_els[0].firstChild.nodeValue) if count_els and count_els[0].firstChild else 0
                    if count >= 1:
                        tag_names.append(name_els[0].firstChild.nodeValue.strip())
            if tag_names:
                genre = ", ".join(tag_names[:2])

            # 2. CONSOLIDATION LOGIC: Search for variations if title has noise
            norm_target = self._normalize_title(title)
            # Only search if title seems to have "features" or is complex
            has_noise = any(kw in title.lower() for kw in ["feat", "with", "con", " (", " ["])
            
            if has_noise:
                try:
                    search_results = self.network.search_for_track(artist, norm_target).get_next_page()
                    self._throttle()
                    
                    # We limit to top 3 search results to avoid too many API calls
                    candidate_tracks = []
                    for s_track in search_results[:3]:
                        # Only consider if artist matches closely and title normalized matches
                        s_artist = str(s_track.artist).lower()
                        s_title = str(s_track.title).lower()
                        if artist.lower() in s_artist or s_artist in artist.lower():
                            if self._normalize_title(s_title) == norm_target:
                                # Avoid redundant call for the primary track we already got
                                if s_title != title.lower():
                                    candidate_tracks.append(s_track)
                    
                    # Fetch user scrobbles for variations and sum them
                    for cand in candidate_tracks:
                        try:
                            # Use userplaycount call specifically to minimize payload
                            c_userplaycount = int(cand.get_userplaycount() or 0)
                            self._throttle()
                            if c_userplaycount > 0:
                                userplaycount += c_userplaycount
                                # Update global stats if this version is more popular
                                c_playcount = int(cand.get_playcount() or 0)
                                if c_playcount > playcount:
                                    playcount = c_playcount
                        except: continue
                except: pass

            return {
                "playcount": playcount,
                "listeners": listeners,
                "userplaycount": userplaycount,
                "genre": genre,
            }
        except Exception:
            return None

    # ── Public Methods ─────────────────────────────────────────

    def get_artist_info(self, artist, cache_ttl_days=30):
        key = f"artist||{str(artist).lower().strip()}"
        with self._lock:
            cached = self.cache.get(key)
        
        if cached and self._cache_is_fresh(cached, cache_ttl_days):
            return cached

        result = {
            "genre": "",
            "listeners": 0,
            "_ts": datetime.now(timezone.utc).isoformat(),
        }

        try:
            artist_obj = self.network.get_artist(artist)
            self._throttle()
            
            # Fetch genres
            top_tags = artist_obj.get_top_tags(limit=5)
            if top_tags:
                tag_names = [t.item.get_name() for t in top_tags if int(t.weight or 0) >= 1]
                if tag_names:
                    result["genre"] = ", ".join(tag_names[:3])
            
            # Fetch listeners
            try:
                result["listeners"] = int(artist_obj.get_listener_count() or 0)
            except:
                pass
        except Exception as e:
            print(f"\n[LastFM Error] Artist info for {artist}: {e}")

        with self._lock:
            self.cache[key] = result
        
        self._call_count += 1
        if self._call_count % self._save_interval == 0:
            self.save_cache()

        return result

    def get_track_info(self, artist, title, force_scrobbles=False, cache_ttl_days=7):
        """
        Returns { genre, scrobble, lastfm_scrobble, lastfm_listeners } for a track.

        Uses a single track.getInfo API call instead of three separate calls,
        reducing API requests by 3×.

        Cache TTL: if cached data is fresher than cache_ttl_days, it is returned
        as-is regardless of force_scrobbles, avoiding redundant API calls.
        """
        key = self._cache_key(artist, title)
        with self._lock:
            cached = self.cache.get(key)
        
        # If we have a fresh cache AND it has a genre, return it.
        # IF IT HAS NO GENRE, we ignore the cache freshness to try and find it now.
        if cached and self._cache_is_fresh(cached, cache_ttl_days) and cached.get("genre"):
            return cached

        # Stale / missing — but if force_scrobbles=False and we have ANY cache (and it's not a "no-genre" retry case), use it.
        # BUT: if the user specifically wants the genre and we didn't have it, we keep going.
        if cached and not force_scrobbles and cached.get("genre"):
            return cached

        existing_genre = cached.get("genre", "") if cached else ""


        result = {
            "genre": existing_genre,
            "scrobble": 0,
            "lastfm_scrobble": 0,
            "lastfm_listeners": 0,
            "_ts": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # ── Single HTTP call via track.getInfo ──
            raw = self._get_track_info_raw(artist, title)
            if raw is not None:
                result["lastfm_scrobble"] = raw["playcount"]
                result["lastfm_listeners"] = raw["listeners"]
                result["scrobble"] = raw["userplaycount"]
                if not result["genre"] and raw["genre"]:
                    result["genre"] = raw["genre"]
            else:
                # Fallback: individual pylast calls
                try:
                    track = self.network.get_track(artist, title)
                    result["lastfm_scrobble"] = int(track.get_playcount() or 0)
                    self._throttle()
                    result["lastfm_listeners"] = int(track.get_listener_count() or 0)
                    self._throttle()
                    result["scrobble"] = int(track.get_userplaycount() or 0)
                    self._throttle()
                except Exception:
                    pass

            # ── Genre fallback: artist top tags ──
            if not result["genre"]:
                try:
                    artist_obj = self.network.get_artist(artist)
                    self._throttle()
                    top_tags = artist_obj.get_top_tags(limit=3)
                    if top_tags:
                        tag_names = [t.item.get_name() for t in top_tags if int(t.weight or 0) >= 1]
                        if tag_names:
                            result["genre"] = ", ".join(tag_names[:2])
                except Exception:
                    pass

        except pylast.WSError as e:
            if "Track not found" not in str(e) and "Artist not found" not in str(e):
                print(f"  Last.fm API error for '{artist} - {title}': {e}")
        except Exception as e:
            print(f"  Last.fm unexpected error for '{artist} - {title}': {e}")

        # Save to cache
        with self._lock:
            self.cache[key] = result
        
        self._call_count += 1
        if self._call_count % self._save_interval == 0:
            self.save_cache()

        return result

    def enrich_songs(self, songs, force_scrobbles=True, cache_ttl_days=7, force_threshold=None):
        """
        Enriches a list of song dicts in-place with Last.fm data.

        Each song dict should have 'Artist' and 'Title' keys.
        Updates 'Genre', 'Scrobble', 'LastfmScrobble' keys.

        TTL-aware: songs cached within cache_ttl_days skip the API call entirely,
        even when force_scrobbles=True.

        force_threshold: If provided (int), any song with song['Scrobble'] < force_threshold
        will trigger a forced API lookup (bypassing cache TTL if force_scrobbles is True,
        or forcing lookup if force_scrobbles was False).
        """
        total = len(songs)
        processed = 0

        def process_song(song):
            artist = str(song.get("Artist", ""))
            title = str(song.get("Title", ""))
            if not artist or not title:
                return False

            # Check if we should force refresh based on threshold
            local_force = force_scrobbles
            if force_threshold is not None:
                try:
                    c_scrobbles = int(song.get("Scrobble", 0))
                    if c_scrobbles < force_threshold:
                        local_force = True
                except (ValueError, TypeError):
                    pass

            existing_genre = song.get("Genre", "")
            info = self.get_track_info(
                artist, title,
                force_scrobbles=local_force,
                cache_ttl_days=cache_ttl_days,
            )

            # Update genre: Usually keep existing if it's already rich, 
            # but if it's empty or we have a new one from info, update it.
            new_genre = info.get("genre", "")
            if new_genre:
                song["Genre"] = new_genre

            new_scrobbles = int(info.get("scrobble", 0))
            current_scrobbles = 0
            try:
                # We normalize the current value (handles strings with dots/commas if any)
                c_val = str(song.get("Scrobble", 0)).replace('.', '').replace(',', '').strip()
                current_scrobbles = int(c_val) if c_val.isdigit() else 0
            except (ValueError, TypeError):
                pass

            # RULE: Never downgrade scrobbles. Only update if the new value is higher.
            if new_scrobbles > current_scrobbles:
                song["Scrobble"] = new_scrobbles
            else:
                # Keep the existing value if it's higher or equal
                song["Scrobble"] = current_scrobbles

            # Prefer listener count; fall back to global playcount
            song["LastfmScrobble"] = (
                int(info.get("lastfm_listeners", 0))
                or int(info.get("lastfm_scrobble", 0))
            )
            return True

        # Single worker (max_workers=1) combined with throttle is the safest way 
        # to respect Last.fm's 5 req/s limit and avoid 503/403 errors.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            futures = {executor.submit(process_song, song): song for song in songs}
            for future in concurrent.futures.as_completed(futures):
                if future.result():
                    processed += 1
                    if processed % 50 == 0:
                        print(f"  Last.fm enrichment: {processed}/{total} songs processed...")

        # Final cache save
        self.save_cache()
        print(f"  Last.fm enrichment complete: {total} songs processed (parallel).")
