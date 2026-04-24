"""YouTube Data API v3 Service.

Handles OAuth authentication and operations for the regular YouTube platform
(subscriptions, playlists, videos) — distinct from YouTube Music (ytmusicapi).
"""

import os
import json
import time
from datetime import datetime, timezone

from ..config import Config


class QuotaExceededError(Exception):
    """Raised when the YouTube Data API quota has been exhausted."""
    pass


# ── OAuth Scopes needed ───────────────────────────────────────────────────────
# youtube.readonly  → read subscriptions, channel info, search
# youtube           → create/manage playlists and add videos
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
]


def _build_youtube_client():
    """Build and return an authenticated YouTube Data API v3 client.

    On first use it will open a browser for the OAuth consent flow and save
    the resulting token to ``data/youtube_token.json``.  Subsequent calls
    load the saved token and refresh it if it has expired.

    Raises
    ------
    FileNotFoundError
        If ``config/youtube_client_secrets.json`` is missing.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "Missing dependencies for YouTube Data API. "
            "Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        )

    if not os.path.exists(Config.YT_CLIENT_SECRETS_FILE):
        raise FileNotFoundError(
            f"\n❌ YouTube client secrets not found: {Config.YT_CLIENT_SECRETS_FILE}\n\n"
            "Para configurar:\n"
            "  1. Ve a https://console.cloud.google.com/\n"
            "  2. Crea (o selecciona) un proyecto → Habilita la YouTube Data API v3\n"
            "  3. Credenciales → Crear → ID de cliente OAuth 2.0 → Tipo: 'Aplicación de escritorio'\n"
            "  4. Descarga el JSON y guárdalo como: config/youtube_client_secrets.json\n"
        )

    creds = None

    # Load existing token
    if os.path.exists(Config.YT_TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(Config.YT_TOKEN_FILE, SCOPES)
        except Exception:
            creds = None

    # Refresh or start new OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                Config.YT_CLIENT_SECRETS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0, open_browser=True)

        # Persist the token for next time
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        with open(Config.YT_TOKEN_FILE, "w") as fh:
            fh.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


class YouTubeDataService:
    """Client for YouTube Data API v3 subscription-to-playlist sync."""

    # Name of the custom playlist created/used for "watch later" videos
    PLAYLIST_NAME = "! 📥 Para Ver"

    def __init__(self):
        self._yt = None  # Lazy-initialised on first API call
        self._sync_state = self._load_sync_state()

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _client(self):
        """Return (and lazily build) the authenticated YouTube API client."""
        if self._yt is None:
            self._yt = _build_youtube_client()
        return self._yt

    # ── Sync State (checkpoint) ───────────────────────────────────────────────

    def _load_sync_state(self) -> dict:
        """Load the persistent sync state from disk."""
        if os.path.exists(Config.YT_SUBS_SYNC_FILE):
            try:
                with open(Config.YT_SUBS_SYNC_FILE, "r") as fh:
                    return json.load(fh)
            except Exception:
                pass
        return {}

    def _save_sync_state(self):
        """Persist the current sync state to disk."""
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        with open(Config.YT_SUBS_SYNC_FILE, "w") as fh:
            json.dump(self._sync_state, fh, indent=2, default=str)

    # ── Playlist helpers ──────────────────────────────────────────────────────

    def _get_or_create_playlist(self) -> str:
        """Return the playlist ID for PLAYLIST_NAME, creating it if needed.

        The playlist ID is cached in the sync state so we only look it up once.
        """
        # Use cached ID if available
        playlist_id = self._sync_state.get("playlist_id")
        if playlist_id:
            return playlist_id

        yt = self._client()

        # Search in the user's existing playlists first
        request = yt.playlists().list(part="snippet", mine=True, maxResults=50)
        while request:
            response = request.execute()
            for item in response.get("items", []):
                if item["snippet"]["title"] == self.PLAYLIST_NAME:
                    playlist_id = item["id"]
                    self._sync_state["playlist_id"] = playlist_id
                    self._save_sync_state()
                    print(f"  ✓ Playlist existente encontrada: '{self.PLAYLIST_NAME}' ({playlist_id})")
                    return playlist_id
            request = yt.playlists().list_next(request, response)

        # Create it
        print(f"  ✨ Creando nueva playlist: '{self.PLAYLIST_NAME}'...")
        resp = yt.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": self.PLAYLIST_NAME,
                    "description": "Videos de suscripciones añadidos automáticamente por Vibemus.",
                },
                "status": {"privacyStatus": "private"},
            },
        ).execute()
        playlist_id = resp["id"]
        self._sync_state["playlist_id"] = playlist_id
        self._save_sync_state()
        print(f"  ✓ Playlist creada: '{self.PLAYLIST_NAME}' (id: {playlist_id})")
        return playlist_id

    def _add_video_to_playlist(
        self,
        playlist_id: str,
        video_id: str,
        channel_id: str = "",
        channel_title: str = "",
    ) -> bool:
        """Add a single video to the playlist. Returns True on success.

        When *channel_id* is provided and the insert succeeds the addition is
        recorded in ``_sync_state["channel_history"]`` for later top-channel
        ranking.  This history is **only written** via ``_save_sync_state()``
        — callers are responsible for saving after a batch.

        Raises
        ------
        QuotaExceededError
            If the YouTube API quota has been exhausted — the caller should
            stop processing and save its checkpoint immediately.
        """
        try:
            self._client().playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            ).execute()
            # ── Record in channel history ────────────────────────────────────
            if channel_id:
                history: dict = self._sync_state.setdefault("channel_history", {})
                entry = history.setdefault(
                    channel_id,
                    {"title": channel_title or channel_id, "dates": []},
                )
                entry["title"] = channel_title or entry["title"]
                entry["dates"].append(datetime.now(timezone.utc).isoformat())
                # Trim to last 90 days to keep the file from growing forever
                cutoff = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=90)).isoformat()
                entry["dates"] = [d for d in entry["dates"] if d >= cutoff]
            return True
        except Exception as e:
            err_str = str(e)
            if "duplicate" in err_str.lower() or "409" in err_str:
                return True  # Already there, that's fine
            # Detect quota exhaustion BEFORE printing a confusing generic error
            if "quotaExceeded" in err_str or "quota" in err_str.lower():
                raise QuotaExceededError(
                    f"Cuota de YouTube API agotada al añadir {video_id}. "
                    "La cuota se renueva a medianoche (hora del Pacífico). "
                    "Vuelve a ejecutar el comando mañana para continuar."
                ) from e
            print(f"    ⚠ Error añadiendo {video_id}: {e}")
            return False

    # ── Subscription helpers ──────────────────────────────────────────────────

    def _get_subscriptions(self) -> list[dict]:
        """Return all subscribed channels as list of {id, channelId, title}."""
        yt = self._client()
        channels = []
        request = yt.subscriptions().list(
            part="snippet", mine=True, maxResults=50, order="alphabetical"
        )
        while request:
            response = request.execute()
            for item in response.get("items", []):
                sub_id = item.get("id")
                snip = item.get("snippet", {})
                channel_id = snip.get("resourceId", {}).get("channelId")
                title = snip.get("title", "Unknown")
                if channel_id and sub_id:
                    channels.append({"id": sub_id, "channelId": channel_id, "title": title})
            request = yt.subscriptions().list_next(request, response)
        return channels

    def _get_uploads_playlist_id(self, channel_id: str) -> str | None:
        """Return the 'uploads' playlist ID for a channel.

        Strategy (cheapest first):
        1. In-memory / on-disk cache  → 0 API units
        2. Derive from channel ID     → 0 API units  (UCxxxxxx → UUxxxxxx)
        3. Fallback API call          → 1 unit (result is cached for next run)
        """
        # 1. Check cache
        uploads_cache: dict = self._sync_state.setdefault("uploads_cache", {})
        if channel_id in uploads_cache:
            return uploads_cache[channel_id]

        # 2. Derive: YouTube stores uploads in a playlist whose ID is the
        #    channel ID with the first two chars replaced by 'UU'.  This is
        #    an unofficial but extremely stable convention.
        if channel_id.startswith("UC"):
            derived = "UU" + channel_id[2:]
            uploads_cache[channel_id] = derived
            self._save_sync_state()
            return derived

        # 3. API fallback for edge-case channel ID formats
        try:
            resp = self._client().channels().list(
                part="contentDetails", id=channel_id
            ).execute()
            items = resp.get("items", [])
            if items:
                uploads_id = items[0]["contentDetails"]["relatedPlaylists"].get("uploads")
                if uploads_id:
                    uploads_cache[channel_id] = uploads_id
                    self._save_sync_state()
                    return uploads_id
        except Exception:
            pass
        return None

    def _get_recent_videos(
        self,
        uploads_playlist_id: str,
        published_after: datetime,
        max_results: int = 10,
    ) -> tuple[list[dict], datetime | None]:
        """Return videos from an uploads playlist published after the given timestamp.

        Fetches the last *max_results* entries and filters locally — avoids the
        expensive ``search.list`` endpoint (costs 100 quota units vs 1 for
        playlistItems).  Pass ``max_results=50`` when scanning a wider window
        (e.g. last 7 days) so you capture all uploads in that period.
        """
        videos = []
        latest_date = None
        try:
            resp = self._client().playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=min(max_results, 50),  # API hard-cap is 50
            ).execute()

            items = resp.get("items", [])
            for idx, item in enumerate(items):
                snip = item.get("snippet", {})
                published_str = snip.get("publishedAt", "")
                if not published_str:
                    continue

                try:
                    pub_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                except ValueError:
                    continue

                # The first item is always the latest
                if idx == 0:
                    latest_date = pub_dt

                # Make published_after timezone-aware if it isn't already
                if published_after.tzinfo is None:
                    published_after = published_after.replace(tzinfo=timezone.utc)

                if pub_dt > published_after:
                    video_id = snip.get("resourceId", {}).get("videoId")
                    title = snip.get("title", "Unknown")
                    channel = snip.get("channelTitle", "")
                    if video_id:
                        videos.append(
                            {
                                "videoId": video_id,
                                "title": title,
                                "description": snip.get("description", ""),
                                "channel": channel,
                                "publishedAt": published_str,
                            }
                        )
        except Exception as e:
            # Skip channels with private/unavailable upload playlists
            if "403" not in str(e) and "404" not in str(e):
                print(f"    ⚠ Error fetching uploads ({uploads_playlist_id}): {e}")
        return videos, latest_date


    def _unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from a channel using its subscription ID."""
        try:
            self._client().subscriptions().delete(id=subscription_id).execute()
            return True
        except Exception as e:
            print(f"    ⚠ Error cancelando suscripción: {e}")
            return False

    def _is_short_by_title(self, title: str) -> bool:
        """Zero-cost heuristic: detect Shorts from title/snippet alone."""
        t = title.lower()
        return "#shorts" in t or "#short" in t

    def _iso_to_seconds(self, iso: str) -> int:
        """Convert ISO 8601 duration (PT1H2M3S) to total seconds."""
        if not iso:
            return 0
        import re
        m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
        if not m:
            return 0
        h, mn, s = (int(x) if x else 0 for x in m.groups())
        return h * 3600 + mn * 60 + s

    def _is_short(self, video_item: dict) -> bool:
        """Full check using contentDetails duration + snippet tags."""
        snip = video_item.get("snippet", {})
        title = snip.get("title", "").lower()
        desc = snip.get("description", "").lower()
        duration = video_item.get("contentDetails", {}).get("duration", "")

        # 2. Tag check (free if snippet already fetched)
        if "#shorts" in title or "#short" in title or "#shorts" in desc:
            return True

        # 3. Duration check — anything <= 180 seconds (3 min) is considered a Short/Clip
        # (YouTube allows vertical clips up to 3 mins; regular videos are usually longer)
        if duration:
            total_seconds = self._iso_to_seconds(duration)
            if total_seconds > 0 and total_seconds <= 180:
                return True

        return False

    def _filter_all_candidates(
        self, candidates: list[dict]
    ) -> list[dict]:
        """Global batch filter for ALL candidate videos across ALL channels.

        - Pre-filters Shorts by title (0 API cost).
        - Fetches contentDetails for remaining videos in batches of 50
          (1 unit per batch — typically just 1-2 calls for the whole run).
        - Keeps only the longest video per channel.

        Parameters
        ----------
        candidates:
            List of dicts, each with keys: videoId, title, channel, channelId,
            publishedAt.

        Returns
        -------
        Filtered list (≤1 video per channel, no Shorts).
        """
        if not candidates:
            return []

        # Phase A — free title pre-filter (catches obvious #shorts)
        after_title = [
            v for v in candidates if not self._is_short_by_title(v["title"])
        ]
        title_filtered = len(candidates) - len(after_title)
        if title_filtered:
            print(f"  🚫 {title_filtered} Shorts descartados por título (0 cuota).")

        if not after_title:
            return []

        # Phase B — single global videos.list run to get durations
        video_ids = [v["videoId"] for v in after_title]
        details_map: dict[str, dict] = {}
        try:
            for i in range(0, len(video_ids), 50):
                batch_ids = video_ids[i : i + 50]
                resp = self._client().videos().list(
                    part="contentDetails",  # snippet already in playlistItems
                    id=",".join(batch_ids),
                ).execute()
                for item in resp.get("items", []):
                    details_map[item["id"]] = item
        except Exception as e:
            print(f"  ⚠ Error al obtener duraciones: {e}. Usando candidatos sin filtro de duración.")
            # Fall through — we'll still apply per-channel longest logic below

        # Phase C — apply duration-based Short filter + keep longest per channel
        # (Duration parsing moved to self._iso_to_seconds)

        # Group by channel, attach duration
        from collections import defaultdict
        by_channel: dict[str, list[dict]] = defaultdict(list)
        api_filtered = 0

        for v in after_title:
            vid = v["videoId"]
            detail = details_map.get(vid)
            if detail:
                # Build a minimal item to reuse _is_short
                fake_item = {
                    "snippet": {
                        "title": v["title"], 
                        "description": v.get("description", "")
                    },
                    "contentDetails": detail.get("contentDetails", {}),
                }
                if self._is_short(fake_item):
                    api_filtered += 1
                    continue
                duration_iso = detail.get("contentDetails", {}).get("duration", "")
            else:
                duration_iso = ""

            v["_seconds"] = self._iso_to_seconds(duration_iso)
            by_channel[v["channelId"]].append(v)

        if api_filtered:
            print(f"  🚫 {api_filtered} Shorts adicionales descartados por duración.")

        # Pick the longest video per channel
        winners: list[dict] = []
        for ch_id, vids in by_channel.items():
            best = max(vids, key=lambda x: x.get("_seconds", 0))
            best.pop("_seconds", None)
            winners.append(best)

        return winners

    def cleanup_playlist_shorts(self):
        """Find and remove Shorts already present in the '📥 Para Ver' playlist."""
        playlist_id = self._get_or_create_playlist()
        yt = self._client()
        
        print(f"\n  🔍 Analizando playlist '{self.PLAYLIST_NAME}' en busca de Shorts...")
        
        # 1. Get all items in playlist
        items_to_check = []
        request = yt.playlistItems().list(
            part="snippet,contentDetails", # contentDetails in playlistItems gives videoId
            playlistId=playlist_id,
            maxResults=50
        )
        
        while request:
            response = request.execute()
            for item in response.get("items", []):
                items_to_check.append({
                    "id": item["id"], # The unique ID of the item in the playlist
                    "videoId": item["snippet"]["resourceId"]["videoId"],
                    "title": item["snippet"]["title"]
                })
            request = yt.playlistItems().list_next(request, response)
            
        if not items_to_check:
            print("  ✨ La playlist está vacía.")
            return

        print(f"  📦 {len(items_to_check)} vídeos totales. Comprobando duraciones...")
        
        # 2. Batch check videos (50 at a time) to find Shorts
        shorts_item_ids = []
        for i in range(0, len(items_to_check), 50):
            batch = items_to_check[i:i+50]
            batch_ids = [v["videoId"] for v in batch]
            
            resp = yt.videos().list(
                part="snippet,contentDetails",
                id=",".join(batch_ids)
            ).execute()
            
            details_map = {v["id"]: v for v in resp.get("items", [])}
            
            for v in batch:
                detail = details_map.get(v["videoId"])
                if detail and self._is_short(detail):
                    shorts_item_ids.append((v["id"], v["title"]))

        if not shorts_item_ids:
            print("  ✨ No se encontraron Shorts en la playlist.")
            return

        print(f"  🚫 Encontrados {len(shorts_item_ids)} Shorts. Eliminando...\n")
        
        # 3. Delete items
        for sub_id, title in shorts_item_ids:
            try:
                yt.playlistItems().delete(id=sub_id).execute()
                print(f"    🗑️ Eliminado: {title}")
            except Exception as e:
                print(f"    ⚠ Error eliminando '{title}': {e}")

        print("\n  ✅ Limpieza completada.")

    def cleanup_watched_videos(self):
        """Remove videos from the '📥 Para Ver' playlist that appear in recent watch history."""
        from .yt_service import YTMusicService
        
        playlist_id = self._get_or_create_playlist()
        yt = self._client()
        
        print(f"  🔍 Buscando vídeos ya vistos en '{self.PLAYLIST_NAME}'...")
        
        try:
            # 1. Get recent history (200 items)
            ytm = YTMusicService()
            history = ytm.yt.get_history()
            history_ids = {item["videoId"] for item in history if "videoId" in item}
            
            if not history_ids:
                print("    ℹ No se pudo recuperar el historial de reproducciones.")
                return

            # 2. Get playlist items
            playlist_items = []
            request = yt.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50
            )
            while request:
                response = request.execute()
                for item in response.get("items", []):
                    playlist_items.append({
                        "id": item["id"],
                        "videoId": item["snippet"]["resourceId"]["videoId"],
                        "title": item["snippet"]["title"]
                    })
                request = yt.playlistItems().list_next(request, response)

            # 3. Compare and delete
            to_remove = [item for item in playlist_items if item["videoId"] in history_ids]
            
            if not to_remove:
                print("    ✨ No se encontraron vídeos vistos en la playlist.")
                return

            print(f"    🗑️ Encontrados {len(to_remove)} vídeos vistos. Eliminando...")
            for item in to_remove:
                try:
                    yt.playlistItems().delete(id=item["id"]).execute()
                    print(f"      ✅ Eliminado: {item['title']}")
                except Exception as e:
                    print(f"      ⚠ Error eliminando '{item['title']}': {e}")
                    
        except Exception as e:
            print(f"    ⚠ Error en la limpieza de vídeos vistos: {e}")

    def clear_playlist(self):
        """Remove the entire '📥 Para Ver' playlist and clear its cache to save API quota."""
        yt = self._client()
        playlist_id = self._sync_state.get("playlist_id")
        
        if not playlist_id:
            # Intentar encontrarla si no está en caché
            request = yt.playlists().list(part="id,snippet", mine=True, maxResults=50)
            while request:
                response = request.execute()
                for item in response.get("items", []):
                    if item["snippet"]["title"] == self.PLAYLIST_NAME:
                        playlist_id = item["id"]
                        break
                if playlist_id:
                    break
                request = yt.playlists().list_next(request, response)

        if playlist_id:
            print(f"  🧹 Recreando la playlist '{self.PLAYLIST_NAME}' para ahorrar cuota de API...")
            try:
                yt.playlists().delete(id=playlist_id).execute()
                print("    🗑️ Playlist anterior eliminada correctamente (ahorro masivo de cuota).")
            except Exception as e:
                # Si no existía o falla, lo ignoramos, se intentará crear una nueva de todas formas
                pass
            
            # Borrar el caché para forzar que se cree de nuevo en el siguiente paso
            self._sync_state.pop("playlist_id", None)
            self._save_sync_state()

    # ── Top-channels cache ────────────────────────────────────────────────────

    def _load_top_channels_cache(self) -> list[dict]:
        """Load the persisted top-5 channels list (may be empty)."""
        if os.path.exists(Config.YT_TOP_CHANNELS_CACHE_FILE):
            try:
                with open(Config.YT_TOP_CHANNELS_CACHE_FILE, "r") as fh:
                    return json.load(fh)
            except Exception:
                pass
        return []

    def _save_top_channels_cache(self, top: list[dict]) -> None:
        """Persist the top-channels list to disk."""
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        with open(Config.YT_TOP_CHANNELS_CACHE_FILE, "w") as fh:
            json.dump(top, fh, indent=2, default=str)

    def update_top_channels_cache(self, window_days: int = 7, top_n: int = 5, interactive: bool = False) -> list[dict]:
        """Compute and persist the top *top_n* channels by additions in the
        last *window_days* days.

        If *interactive* is True, the user can manually add or remove channels
        from the top list.
        """
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        history: dict = self._sync_state.get("channel_history", {})

        if not history and not interactive:
            print("  ℹ️  No hay historial de adiciones todavía. Ejecuta al menos un sync-subs primero.")
            return []

        # 1. Calcular el top automático basado en historial
        ranked = []
        for ch_id, data in history.items():
            recent_count = sum(1 for d in data.get("dates", []) if d >= cutoff)
            if recent_count > 0:
                ranked.append({
                    "channelId": ch_id,
                    "title": data.get("title", ch_id),
                    "count": recent_count,
                })

        ranked.sort(key=lambda x: x["count"], reverse=True)
        top = ranked[:top_n]

        # 2. Si no es interactivo, guardar y salir
        if not interactive:
            if not top:
                print(f"  ⚠  No hay datos de los últimos {window_days} días. Prueba con una ventana mayor o usa --interactive.")
                return []
            
            print(f"\n  🏆 Top-{len(top)} canales más añadidos (últimos {window_days} días):")
            for i, ch in enumerate(top, 1):
                print(f"     {i}. {ch['title']}  ({ch['count']} vídeo{'s' if ch['count'] != 1 else ''})")

            self._save_top_channels_cache(top)
            print(f"\n  💾 Cache guardado en: {Config.YT_TOP_CHANNELS_CACHE_FILE}")
            return top

        # 3. MODO INTERACTIVO
        current_top = self._load_top_channels_cache()
        if not current_top:
            current_top = top

        while True:
            print("\n" + "━"*50)
            print("⭐ GESTIÓN INTERACTIVA DE TOP CANALES")
            print("━"*50)
            
            if not current_top:
                print("  (Lista vacía)")
            else:
                for i, ch in enumerate(current_top, 1):
                    count_str = f" ({ch['count']} vídeos)" if 'count' in ch else ""
                    print(f"  {i}. \033[1;96m{ch['title']}\033[0m{count_str}")
            
            print("\n  Opciones: [a]ñadir | [q]uitar | [s]ubir | [b]ajar | [g]uardar | [v]olver")
            choice = input("\n👉 Elige una opción: ").strip().lower()

            if choice in ['a', 'añadir']:
                # Buscar en el historial completo
                query = input("🔎 Buscar canal en el historial (nombre): ").strip().lower()
                matches = []
                for ch_id, data in history.items():
                    title = data.get("title", "").lower()
                    if query in title or query in ch_id.lower():
                        matches.append({
                            "channelId": ch_id,
                            "title": data.get("title", ch_id),
                            "count": sum(1 for d in data.get("dates", []) if d >= cutoff)
                        })
                
                if not matches:
                    print("  ❌ No se encontraron canales en el historial con ese nombre.")
                    continue
                
                print("\n  Resultados encontrados:")
                for i, m in enumerate(matches[:10], 1):
                    print(f"    {i}. {m['title']} ({m['count']} vídeos recientes)")
                
                try:
                    idx_str = input("\n👉 Elige el número del canal para añadir (o 'c' para cancelar): ").strip()
                    if idx_str.lower() == 'c': continue
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(matches):
                        new_ch = matches[idx]
                        if any(c['channelId'] == new_ch['channelId'] for c in current_top):
                            print(f"  ℹ️  El canal '{new_ch['title']}' ya está en el top.")
                        else:
                            current_top.append(new_ch)
                            print(f"  ✅ Añadido: {new_ch['title']}")
                    else:
                        print("  ❌ Índice inválido.")
                except ValueError:
                    print("  ❌ Entrada inválida.")

            elif choice in ['q', 'quitar']:
                if not current_top: continue
                try:
                    idx = int(input("👉 Número del canal a quitar: ")) - 1
                    if 0 <= idx < len(current_top):
                        removed = current_top.pop(idx)
                        print(f"  🗑️ Quitado: {removed['title']}")
                    else:
                        print("  ❌ Índice inválido.")
                except ValueError:
                    print("  ❌ Entrada inválida.")

            elif choice in ['s', 'subir']:
                if not current_top: continue
                try:
                    idx = int(input("👉 Número del canal a subir: ")) - 1
                    if 1 <= idx < len(current_top):
                        current_top[idx], current_top[idx-1] = current_top[idx-1], current_top[idx]
                    else:
                        print("  ❌ No se puede subir.")
                except ValueError:
                    print("  ❌ Entrada inválida.")

            elif choice in ['b', 'bajar']:
                if not current_top: continue
                try:
                    idx = int(input("👉 Número del canal a bajar: ")) - 1
                    if 0 <= idx < len(current_top) - 1:
                        current_top[idx], current_top[idx+1] = current_top[idx+1], current_top[idx]
                    else:
                        print("  ❌ No se puede bajar.")
                except ValueError:
                    print("  ❌ Entrada inválida.")

            elif choice in ['g', 'guardar']:
                self._save_top_channels_cache(current_top)
                print(f"\n  💾 Cache guardado en: {Config.YT_TOP_CHANNELS_CACHE_FILE}")
                return current_top

            elif choice in ['v', 'volver', 'q', 'quit', 'exit']:
                confirm = input("⚠️  ¿Salir sin guardar cambios? (s/N): ").strip().lower()
                if confirm == 's':
                    return self._load_top_channels_cache()
            else:
                print("  ❌ Opción no reconocida.")

        return current_top

    def sync_top_channels(
        self,
        playlist_id: str,
        window_days: int = 7,
        max_per_channel: int = 3,
        already_added_ids: set | None = None,
    ) -> int:
        """Fetch and add videos from the cached top-5 channels.

        For each top channel the method searches the last *window_days* days
        of uploads, discards Shorts and duplicates already added in this sync
        run, then inserts:
          - The *longest* video (always)
          - Up to *max_per_channel - 1* additional videos (second-longest, etc.)

        Parameters
        ----------
        playlist_id:
            ID of the destination playlist.
        window_days:
            How far back (in days) to look for new videos.
        max_per_channel:
            Maximum videos to add per channel (default 3).
        already_added_ids:
            Set of video IDs already added during this run so they are not
            duplicated.

        Returns
        -------
        int  — total number of videos added from top channels.
        """
        from datetime import timedelta

        top = self._load_top_channels_cache()
        if not top:
            return 0

        if already_added_ids is None:
            already_added_ids = set()

        window_start = datetime.now(timezone.utc) - timedelta(days=window_days)

        print(f"\n  ⭐ Fase 4 — Top canales ({window_days}d): añadiendo hasta {max_per_channel} vídeos/canal...\n")

        total_added = 0

        for ch in top:
            ch_id = ch["channelId"]
            ch_title = ch["title"]
            uploads_id = self._get_uploads_playlist_id(ch_id)
            if not uploads_id:
                print(f"  ⚠  Sin playlist de uploads para: {ch_title}")
                continue

            # Gather raw candidates (last window_days)
            raw_videos, _ = self._get_recent_videos(uploads_id, window_start, max_results=50)
            if not raw_videos:
                print(f"  ─ {ch_title}: sin vídeos nuevos en los últimos {window_days} días.")
                continue

            # Tag with channelId so the filter can group them
            for v in raw_videos:
                v.setdefault("channelId", ch_id)

            # Filter Shorts + get durations via batch API
            filtered = self._filter_all_candidates(raw_videos)
            # After filter, we may get only 1 (the longest per channel).  To
            # allow up to max_per_channel we redo the per-channel grouping
            # manually from the title-filtered + duration-enriched pool.
            # Re-derive a full sorted list from the raw pool ourselves.
            candidates = self._enrich_and_sort_channel_videos(raw_videos, ch_id)

            # Remove already-added videos
            candidates = [v for v in candidates if v["videoId"] not in already_added_ids]

            if not candidates:
                print(f"  ─ {ch_title}: todos los vídeos ya fueron añadidos hoy.")
                continue

            selected = candidates[:max_per_channel]
            added_here = 0
            for v in selected:
                try:
                    ok = self._add_video_to_playlist(
                        playlist_id, v["videoId"],
                        channel_id=ch_id, channel_title=ch_title,
                    )
                except QuotaExceededError as exc:
                    print(f"\n  🚫 {exc}")
                    self._save_sync_state()
                    return total_added

                if ok:
                    already_added_ids.add(v["videoId"])
                    added_here += 1
                    total_added += 1
                    pub_str = v.get("publishedAt", "")
                    try:
                        pub_fmt = datetime.fromisoformat(
                            pub_str.replace("Z", "+00:00")
                        ).strftime("%d/%m/%Y")
                    except ValueError:
                        pub_fmt = pub_str
                    print(f"  ⭐ [{pub_fmt}] {ch_title} — {v['title']}")

            if added_here == 0:
                print(f"  ─ {ch_title}: ningún vídeo añadido (ya estaban o errores).")

        self._save_sync_state()  # persist channel_history updates
        return total_added

    def _enrich_and_sort_channel_videos(
        self, raw_videos: list[dict], channel_id: str
    ) -> list[dict]:
        """Return *raw_videos* for *channel_id* sorted longest-first, Shorts removed.

        Calls ``videos.list`` once per 50 videos (same cost as the global
        batch filter) and attaches ``_seconds`` for sorting.
        """
        import re
        from datetime import timedelta

        # Title pre-filter
        pool = [v for v in raw_videos
                if v.get("channelId", channel_id) == channel_id
                and not self._is_short_by_title(v["title"])]
        if not pool:
            return []

        # Fetch durations
        video_ids = [v["videoId"] for v in pool]
        details_map: dict[str, dict] = {}
        try:
            for i in range(0, len(video_ids), 50):
                resp = self._client().videos().list(
                    part="contentDetails",
                    id=",".join(video_ids[i: i + 50]),
                ).execute()
                for item in resp.get("items", []):
                    details_map[item["id"]] = item
        except Exception as e:
            print(f"  ⚠ Error obteniendo duraciones para {channel_id}: {e}")

        def _iso_to_seconds(iso: str) -> int:
            if not iso:
                return 0
            m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
            if not m:
                return 0
            h, mn, s = (int(x) if x else 0 for x in m.groups())
            return h * 3600 + mn * 60 + s

        enriched = []
        for v in pool:
            detail = details_map.get(v["videoId"])
            if detail:
                fake = {
                    "snippet": {
                        "title": v["title"], 
                        "description": v.get("description", "")
                    },
                    "contentDetails": detail.get("contentDetails", {}),
                }
                if self._is_short(fake):
                    continue
                duration_iso = detail.get("contentDetails", {}).get("duration", "")
            else:
                duration_iso = ""
            v["_seconds"] = _iso_to_seconds(duration_iso)
            enriched.append(v)

        enriched.sort(key=lambda x: x.get("_seconds", 0), reverse=True)
        for v in enriched:
            v.pop("_seconds", None)
        return enriched

    # ── Main entry point ──────────────────────────────────────────────────────

    def sync_subscriptions(self, cleanup_inactive: bool = False):
        """Fetch new subscription videos and add them to the 'Para Ver' playlist.

        Quota-optimised flow
        --------------------
        Phase 1 – Gather candidates
            For every subscribed channel fetch the raw uploads list
            (1 unit/channel via playlistItems.list).  The uploads playlist
            ID is derived for free (UC→UU) and cached so channels.list is
            **never** called unless strictly necessary.

        Phase 2 – Global batch filter
            All candidates across ALL channels are filtered in as few
            videos.list calls as possible (1 unit per 50 videos).
            Shorts are discarded; only the longest video per channel survives.

        Phase 3 – Insert winners
            One playlistItems.insert (50 units) per surviving video.

        If the API quota is exhausted mid-run, the current subscription
        index is saved so the next run can resume from exactly that point.
        """
        # ── Resume detection ─────────────────────────────────────────────────
        resume_index = self._sync_state.get("resume_index", 0)
        is_resuming = resume_index > 0

        if is_resuming:
            print(
                f"\n  ⏩ Reanudando sync desde la suscripción #{resume_index + 1} "
                f"(checkpoint de cuota anterior)."
            )
        else:
            # Solo recrear la playlist si es la primera ejecución del día (UTC).
            # Si ya se ejecutó hoy, simplemente añadimos vídeos nuevos encima.
            raw_last_check = self._sync_state.get("last_run")
            already_ran_today = False
            if raw_last_check:
                try:
                    last_dt = datetime.fromisoformat(raw_last_check)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    already_ran_today = last_dt.date() == datetime.now(timezone.utc).date()
                except ValueError:
                    pass

            if already_ran_today:
                print("\n  ♻️  Sync del mismo día detectado — se añadirán vídeos sin recrear la playlist.")
            else:
                self.clear_playlist()

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # ── Determine search window ───────────────────────────────────────────
        raw_last = self._sync_state.get("last_run")
        if raw_last:
            try:
                last_run = datetime.fromisoformat(raw_last)
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)
            except ValueError:
                last_run = None
        else:
            last_run = None

        if last_run:
            print(f"\n  📅 Buscando vídeos publicados desde: {last_run.strftime('%d/%m/%Y %H:%M:%S')} (UTC)")
        else:
            from datetime import timedelta
            last_run = now - timedelta(hours=24)
            print(f"\n  ℹ️  Primera ejecución — buscando últimas 24 horas.")
            print(f"  📅 Buscando desde: {last_run.strftime('%d/%m/%Y %H:%M:%S')} (UTC)")

        # ── Step 1: playlist ──────────────────────────────────────────────────
        playlist_id = self._get_or_create_playlist()

        # ── Step 2: subscriptions ─────────────────────────────────────────────
        print("\n  📡 Obteniendo lista de suscripciones...")
        channels = self._get_subscriptions()
        total = len(channels)
        print(f"  ✓ {total} suscripciones encontradas.")

        if not channels:
            print("  ⚠ No tienes suscripciones activas.")
            return

        # ── Phase 1: collect raw candidates (1 unit/channel) ─────────────────
        print(f"\n  🔍 Fase 1 — Recopilando candidatos en {total} canales...\n")
        all_candidates: list[dict] = []   # carries channelId for grouping
        inactivity_log: list[tuple] = []  # (idx, ch) pairs to handle after

        for idx, ch in enumerate(channels):
            if idx < resume_index:
                continue

            display_idx = idx + 1
            ch_title = ch["title"]
            ch_id = ch["channelId"]

            uploads_id = self._get_uploads_playlist_id(ch_id)
            if not uploads_id:
                continue

            new_videos, latest_date = self._get_recent_videos(uploads_id, last_run)

            # Tag each video with its channelId so the global filter can group
            for v in new_videos:
                v.setdefault("channelId", ch_id)

            # Inactivity tracking
            if latest_date:
                days_idle = (now - latest_date).days
                if days_idle > 90:
                    inactivity_log.append((display_idx, ch, days_idle))
                    if cleanup_inactive:
                        status_color = "\033[91m"
                        print(
                            f"  [{display_idx}/{total}] {status_color}⚡ Inactivo\033[0m: "
                            f"\033[1m{ch_title}\033[0m (Último vídeo: hace {days_idle} días)"
                        )
                        confirm = input(
                            f"    ❓ Canal inactivo (>3 meses). ¿Anular suscripción? [y/N]: "
                        ).lower()
                        if confirm == "y":
                            if self._unsubscribe(ch["id"]):
                                print(f"    🗑️ Suscripción cancelada.")
                            new_videos = []  # discard its videos

            all_candidates.extend(new_videos)

        print(f"\n  📦 {len(all_candidates)} vídeos candidatos recogidos de {total} canales.")

        # ── Phase 2: global batch filter (≤1 unit per 50 videos total) ────────
        print("\n  🧹 Fase 2 — Filtrando Shorts y seleccionando el más largo por canal...")
        winners = self._filter_all_candidates(all_candidates)
        print(f"  ✅ {len(winners)} vídeos seleccionados tras filtrado.")

        if not winners:
            self._sync_state["last_run"] = now_iso
            self._sync_state.pop("resume_index", None)
            self._save_sync_state()
            print("\n" + "─" * 60)
            print("  ✨ No hay vídeos nuevos desde la última sincronización.")
            print(f"  💾 Checkpoint guardado: {now.strftime('%d/%m/%Y %H:%M:%S')} (UTC)")
            print("─" * 60)
            return

        # ── Phase 3: insert winners ───────────────────────────────────────────
        print(f"\n  ➕ Fase 3 — Añadiendo {len(winners)} vídeos a '{self.PLAYLIST_NAME}'...\n")
        total_added = 0

        added_video_ids: set[str] = set()  # track for dedup with top-channel phase

        for v in winners:
            pub_str = v.get("publishedAt", "")
            try:
                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                pub_fmt = pub_dt.strftime("%d/%m/%Y %H:%M")
            except ValueError:
                pub_fmt = pub_str

            ch_id = v.get("channelId", "")
            ch_title = v.get("channel", "")
            try:
                success = self._add_video_to_playlist(
                    playlist_id, v["videoId"],
                    channel_id=ch_id, channel_title=ch_title,
                )
            except QuotaExceededError as exc:
                # Save checkpoint at the first channel that failed (resume from it)
                # Best-effort: find the channel index for this video
                failed_ch_id = ch_id
                failed_idx = next(
                    (i for i, ch in enumerate(channels) if ch["channelId"] == failed_ch_id),
                    resume_index,
                )
                self._sync_state["resume_index"] = failed_idx
                self._save_sync_state()
                print(f"\n  🚫 {exc}")
                print(
                    f"  💾 Checkpoint guardado en el canal '{ch_title}'. "
                    "Vuelve a ejecutar mañana para continuar."
                )
                print("─" * 60)
                return

            status = "✅" if success else "⚠"
            if success:
                total_added += 1
                added_video_ids.add(v["videoId"])
            print(f"  {status} [{pub_fmt}] {v['channel']} — {v['title']}")

        # ── Step 4: top-channels bonus ─────────────────────────────────────────
        top_added = 0
        if os.path.exists(Config.YT_TOP_CHANNELS_CACHE_FILE):
            top_added = self.sync_top_channels(
                playlist_id,
                window_days=7,
                max_per_channel=3,
                already_added_ids=added_video_ids,
            )
        else:
            print(
                "\n  ℹ️  Sin cache de top canales. Ejecuta:"
                " vibemus youtube update-top-channels  para activar la fase 4."
            )

        # ── Step 5: checkpoint ────────────────────────────────────────────────
        self._sync_state["last_run"] = now_iso
        self._sync_state.pop("resume_index", None)
        self._save_sync_state()

        print("\n" + "─" * 60)
        total_subs = total_added
        print(f"  📊 Subs: {len(winners)} encontrados → {total_subs} añadidos  |  Top canales: +{top_added}")
        print(f"  💾 Checkpoint guardado: {now.strftime('%d/%m/%Y %H:%M:%S')} (UTC)")
        print("─" * 60)
