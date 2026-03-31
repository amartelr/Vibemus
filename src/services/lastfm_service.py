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

    def _get_track_info_raw(self, artist: str, title: str) -> dict | None:
        """
        Calls track.getInfo via pylast's internal _request in ONE HTTP call,
        returning playcount, listeners, userplaycount, and tags.

        This replaces 3 separate method calls (get_playcount, get_listener_count,
        get_userplaycount) with a single API round-trip.
        """
        try:
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

            def _text(tag):
                els = t.getElementsByTagName(tag)
                return els[0].firstChild.nodeValue.strip() if els and els[0].firstChild else "0"

            playcount = int(_text("playcount") or 0)
            listeners = int(_text("listeners") or 0)

            # userplaycount is inside <track> but only when username is passed
            user_els = t.getElementsByTagName("userplaycount")
            userplaycount = int(user_els[0].firstChild.nodeValue.strip()) if user_els and user_els[0].firstChild else 0

            # Tags
            genre = ""
            tag_els = t.getElementsByTagName("tag")
            tag_names = []
            for tag_el in tag_els:
                name_els = tag_el.getElementsByTagName("name")
                count_els = tag_el.getElementsByTagName("count")
                if name_els and name_els[0].firstChild:
                    count = int(count_els[0].firstChild.nodeValue) if count_els and count_els[0].firstChild else 0
                    if count >= 1:
                        tag_names.append(name_els[0].firstChild.nodeValue.strip())
            if tag_names:
                genre = ", ".join(tag_names[:2])

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
            "_ts": datetime.now(timezone.utc).isoformat(),
        }

        try:
            artist_obj = self.network.get_artist(artist)
            self._throttle()
            top_tags = artist_obj.get_top_tags(limit=5)
            if top_tags:
                tag_names = [t.item.get_name() for t in top_tags if int(t.weight or 0) >= 1]
                if tag_names:
                    result["genre"] = ", ".join(tag_names[:3])
        except Exception as e:
            print(f"\n[LastFM Error] Artist tags for {artist}: {e}")

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
        
        # Fresh cache: always return it (even with force_scrobbles)
        if cached and self._cache_is_fresh(cached, cache_ttl_days):
            return cached

        # Stale / missing — but if force_scrobbles=False and we have *any* cache, use it
        if cached and not force_scrobbles:
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

    def enrich_songs(self, songs, force_scrobbles=True, cache_ttl_days=7):
        """
        Enriches a list of song dicts in-place with Last.fm data.

        Each song dict should have 'Artist' and 'Title' keys.
        Updates 'Genre', 'Scrobble', 'LastfmScrobble' keys.

        TTL-aware: songs cached within cache_ttl_days skip the API call entirely,
        even when force_scrobbles=True.
        """
        total = len(songs)
        processed = 0

        def process_song(song):
            artist = str(song.get("Artist", ""))
            title = str(song.get("Title", ""))
            if not artist or not title:
                return False

            existing_genre = song.get("Genre", "")
            info = self.get_track_info(
                artist, title,
                force_scrobbles=force_scrobbles,
                cache_ttl_days=cache_ttl_days,
            )

            # Only update genre if it's empty
            if not existing_genre:
                song["Genre"] = info.get("genre", "")

            song["Scrobble"] = int(info.get("scrobble", 0))
            # Prefer listener count; fall back to global playcount
            song["LastfmScrobble"] = (
                int(info.get("lastfm_listeners", 0))
                or int(info.get("lastfm_scrobble", 0))
            )
            return True

        # 10 workers — safe with 1 req/song and 0.25s throttle per thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_song, song): song for song in songs}
            for future in concurrent.futures.as_completed(futures):
                if future.result():
                    processed += 1
                    if processed % 50 == 0:
                        print(f"  Last.fm enrichment: {processed}/{total} songs processed...")

        # Final cache save
        self.save_cache()
        print(f"  Last.fm enrichment complete: {total} songs processed (parallel).")
