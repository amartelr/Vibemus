"""YouTube Data API v3 Service.

Handles OAuth authentication and operations for the regular YouTube platform
(subscriptions, playlists, videos) — distinct from YouTube Music (ytmusicapi).
"""

import os
import json
import time
from datetime import datetime, timezone

from ..config import Config


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
    PLAYLIST_NAME = "📥 Para Ver"

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

    def _add_video_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        """Add a single video to the playlist. Returns True on success."""
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
            return True
        except Exception as e:
            err_str = str(e)
            if "duplicate" in err_str.lower() or "409" in err_str:
                return True  # Already there, that's fine
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
        """Return the 'uploads' playlist ID for a channel."""
        try:
            resp = self._client().channels().list(
                part="contentDetails", id=channel_id
            ).execute()
            items = resp.get("items", [])
            if items:
                return items[0]["contentDetails"]["relatedPlaylists"].get("uploads")
        except Exception:
            pass
        return None

    def _get_recent_videos(
        self, uploads_playlist_id: str, published_after: datetime
    ) -> tuple[list[dict], datetime | None]:
        """Return videos from an uploads playlist published after the given timestamp.

        Fetches the last 10 entries and filters locally — avoids the expensive
        ``search.list`` endpoint (costs 100 quota units vs 1 for playlistItems).
        """
        videos = []
        latest_date = None
        try:
            resp = self._client().playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=10,
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

    def _filter_shorts(self, videos: list[dict]) -> list[dict]:
        """Filter out videos that are YouTube Shorts (duration <= 60s or tagged).
        Also filters the list so that if a channel posted multiple videos, 
        only the longest one is kept.
        
        Uses a single batch request to fetch contentDetails for all candidates.
        """
        if not videos:
            return []
            
        video_ids = [v["videoId"] for v in videos]
        filtered = []
        
        try:
            # Batch fetch details for up to 50 videos at once (costs 1 unit)
            resp = self._client().videos().list(
                part="snippet,contentDetails",
                id=",".join(video_ids)
            ).execute()
            
            details_map = {item["id"]: item for item in resp.get("items", [])}
            
            for v in videos:
                vid = v["videoId"]
                item = details_map.get(vid)
                if not item:
                    # If we can't find details, keep it just in case
                    filtered.append(v)
                    continue
                
                if self._is_short(item):
                    continue
                    
                # Guardamos la duracion en el dict para poder comparar despues
                v["_duration_iso"] = item.get("contentDetails", {}).get("duration", "")
                filtered.append(v)
                
        except Exception as e:
            print(f"    ⚠ Error filtrando Shorts: {e}")
            return videos # Fallback to original list if API fails
            
        # Si un canal sacó varios videos en el mismo día/intervalo, quedarse solo con el de mayor duración
        if len(filtered) > 1:
            try:
                import isodate
                # Intentamos parsear. Si falla isodate, no lo filtramos.
                longest_vid = None
                max_seconds = -1
                
                for v in filtered:
                    dur_iso = v.get("_duration_iso", "")
                    if not dur_iso:
                        continue
                    try:
                        seconds = isodate.parse_duration(dur_iso).total_seconds()
                    except:
                        seconds = 0
                        
                    if seconds > max_seconds:
                        max_seconds = seconds
                        longest_vid = v
                
                if longest_vid:
                    # Limpiamos el helper interno antes de devolverlo al resto del código
                    for vid in filtered:
                        vid.pop("_duration_iso", None)
                    return [longest_vid]
            except ImportError:
                # Si no está isodate instalado no lo filtramos. (Instalar 'isodate' si no lo está)
                pass

        # Limpieza por si quedó algo
        for vid in filtered:
            vid.pop("_duration_iso", None)
            
        return filtered

    def _is_short(self, video_item: dict) -> bool:
        """Helper to determine if a video API item is a Short."""
        snip = video_item.get("snippet", {})
        title = snip.get("title", "").lower()
        desc = snip.get("description", "").lower()
        duration = video_item.get("contentDetails", {}).get("duration", "")

        # 1. Check tags
        if "#shorts" in title or "#shorts" in desc:
            return True
            
        # 2. Check duration (<= 60s)
        if "H" not in duration:
            if "M" not in duration:
                return True
            if duration == "PT1M" or "PT0M" in duration:
                return True
                
        return False

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

    # ── Main entry point ──────────────────────────────────────────────────────

    def sync_subscriptions(self, cleanup_inactive: bool = False):
        """Fetch new subscription videos and add them to the 'Para Ver' playlist.

        Uses a persistent checkpoint so only videos published since the last
        execution are processed.
        """
        # Clear the playlist before adding new videos
        self.clear_playlist()

        yt = self._client()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # Determine the search window start
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
            # First run: look back 24 hours
            from datetime import timedelta
            last_run = now - timedelta(hours=24)
            print(f"\n  ℹ️  Primera ejecución — buscando últimas 24 horas.")
            print(f"  📅 Buscando desde: {last_run.strftime('%d/%m/%Y %H:%M:%S')} (UTC)")

        # Step 1: get or create the target playlist
        playlist_id = self._get_or_create_playlist()

        # Step 2: get all subscriptions
        print("\n  📡 Obteniendo lista de suscripciones...")
        channels = self._get_subscriptions()
        print(f"  ✓ {len(channels)} suscripciones encontradas.")

        if not channels:
            print("  ⚠ No tienes suscripciones activas.")
            return

        # Step 3: for each channel, fetch recent videos
        total_added = 0
        total_found = 0
        print(f"\n  🔍 Escaneando vídeos nuevos en {len(channels)} canales...\n")

        for idx, ch in enumerate(channels, 1):
            ch_title = ch["title"]
            ch_id = ch["channelId"]

            uploads_id = self._get_uploads_playlist_id(ch_id)
            if not uploads_id:
                continue

            new_videos, latest_date = self._get_recent_videos(uploads_id, last_run)
            
            # Filter out Shorts
            if new_videos:
                before_count = len(new_videos)
                new_videos = self._filter_shorts(new_videos)
                shorts_count = before_count - len(new_videos)
                if shorts_count > 0:
                    print(f"    🚫 Filtrados {shorts_count} Shorts.")

            # Check for inactivity (3 months = ~90 days)
            if latest_date:
                days_since_active = (now - latest_date).days
                if days_since_active > 90:
                    status_color = "\033[91m" if cleanup_inactive else "\033[93m"
                    print(f"  [{idx}/{len(channels)}] {status_color}⚡ Inactivo\033[0m: \033[1m{ch_title}\033[0m (Último vídeo: hace {days_since_active} días)")
                    if cleanup_inactive:
                        confirm = input(f"    ❓ Canal inactivo (>3 meses). ¿Anular suscripción? [y/N]: ").lower()
                        if confirm == 'y':
                            if self._unsubscribe(ch["id"]):
                                print(f"    🗑️ Suscripción cancelada.")
                            continue
                        else:
                            print(f"    ⏩ Saltado.")
                    # If not cleaning up or skipped, just skip the video check since we already know there are no new ones
                    # (Unless it was active within the last run period but > 90 days total, but that's unlikely)
                    if not new_videos:
                        continue

            if not new_videos:
                continue

            total_found += len(new_videos)
            print(f"  [{idx}/{len(channels)}] \033[1m{ch_title}\033[0m → {len(new_videos)} vídeo(s) nuevo(s):")

            for v in new_videos:
                pub_str = v["publishedAt"]
                try:
                    pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    pub_fmt = pub_dt.strftime("%d/%m/%Y %H:%M")
                except ValueError:
                    pub_fmt = pub_str

                success = self._add_video_to_playlist(playlist_id, v["videoId"])
                status = "✅" if success else "⚠"
                if success:
                    total_added += 1
                print(f"    {status} [{pub_fmt}] {v['title']}")

            # Small rate-limit sleep to avoid hammering the API
            time.sleep(0.3)

        # Step 4: update checkpoint — only if we haven't crashed
        self._sync_state["last_run"] = now_iso
        self._save_sync_state()

        # Summary
        print("\n" + "─" * 60)
        if total_found == 0:
            print("  ✨ No hay vídeos nuevos desde la última sincronización.")
        else:
            print(f"  📊 {total_found} vídeos encontrados → {total_added} añadidos a '{self.PLAYLIST_NAME}'")
        print(f"  💾 Checkpoint guardado: {now.strftime('%d/%m/%Y %H:%M:%S')} (UTC)")
        print("─" * 60)
