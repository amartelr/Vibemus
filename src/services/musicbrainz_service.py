import threading
import time
import json
import os
import musicbrainzngs
from datetime import datetime, timezone
from ..config import Config


class MusicBrainzService:
    """Service to interact with MusicBrainz API with persistent caching and rate limiting."""

    def __init__(self):
        musicbrainzngs.set_useragent(
            Config.MUSICBRAINZ_APP,
            Config.MUSICBRAINZ_VERSION,
            Config.MUSICBRAINZ_CONTACT
        )
        self.cache_file = Config.MUSICBRAINZ_CACHE_FILE
        self.cache = self._load_cache()
        self._call_count = 0
        self._save_interval = 10
        self._lock = threading.RLock()
        self._last_call_ts = 0

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
        ts = cached.get("_ts")
        if not ts:
            return False
        if ttl_days < 0: return True  # Special case for "always fresh" in assistant
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).days
            return age < ttl_days
        except Exception:
            return False

    # ── Rate Limiting ──────────────────────────────────────────

    def _throttle(self):
        """Strict 1 request per second as per MB terms."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_call_ts
            if elapsed < 1.1:
                time.sleep(1.1 - elapsed)
            self._last_call_ts = time.time()

    # ── Public Methods ─────────────────────────────────────────

    def get_artist_info(self, artist_name, cache_ttl_days=30):
        key = f"artist||{str(artist_name).lower().strip()}"
        with self._lock:
            cached = self.cache.get(key)
        
        if cached and self._cache_is_fresh(cached, cache_ttl_days):
            return cached

        result = {
            "genre": "",
            "_ts": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self._throttle()
            search_result = musicbrainzngs.search_artists(artist=artist_name, limit=1)
            if search_result.get("artist-list"):
                artist = search_result["artist-list"][0]
                tags = artist.get("tag-list", [])
                # Filter tags that look like genres (MusicBrainz has all sorts of tags)
                tag_names = [t["name"] for t in tags if int(t.get("count", 0)) >= 1]
                if tag_names:
                    result["genre"] = ", ".join(tag_names[:3])
        except Exception as e:
            print(f"\n[MusicBrainz Error] Artist tags for {artist_name}: {e}")

        with self._lock:
            self.cache[key] = result
            self._call_count += 1
            if self._call_count % self._save_interval == 0:
                self.save_cache()

        return result

    def get_track_info(self, artist_name, title, force_scrobbles=False, cache_ttl_days=7):
        """
        Mimics LastFMService.get_track_info interface.
        Note: MusicBrainz doesn't provide scrobble counts.
        """
        key = self._cache_key(artist_name, title)
        with self._lock:
            cached = self.cache.get(key)
        
        if cached and self._cache_is_fresh(cached, cache_ttl_days):
            return cached

        result = {
            "genre": "",
            "scrobble": 0,
            "lastfm_scrobble": 0,
            "lastfm_listeners": 0,
            "_ts": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self._throttle()
            search_result = musicbrainzngs.search_recordings(
                query=title, artist=artist_name, limit=1
            )
            
            if search_result.get("recording-list"):
                recording = search_result["recording-list"][0]
                
                # Recordings sometimes have direct tags
                tags = recording.get("tag-list", [])
                tag_names = [t["name"] for t in tags]
                
                # If no direct tags, check the artist tags for this recording
                if not tag_names:
                    artist_credit = recording.get("artist-credit", [])
                    if artist_credit:
                        # Fetch artist info (will be throttled/cached internally)
                        artist_info = self.get_artist_info(artist_name)
                        tag_names = [t.strip() for t in artist_info["genre"].split(",") if t.strip()]

                if tag_names:
                    result["genre"] = ", ".join(tag_names[:2])

        except Exception as e:
            print(f"  MusicBrainz error for '{artist_name} - {title}': {e}")

        with self._lock:
            self.cache[key] = result
            self._call_count += 1
            if self._call_count % self._save_interval == 0:
                self.save_cache()

        return result
