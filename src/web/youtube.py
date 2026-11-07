"""YouTube helpers: alternative video search and playlist synchronisation (OAuth)."""
import json
import os
import re

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .bpm import _norm_text
from .paths import WEB_CONFIG_DIR


# ── Alternative YouTube video for a song whose current video won't play ──────────
_YT_BAD_WORDS = ("live", "cover", "remix", "karaoke", "tutorial", "lesson", "sped up", "slowed", "nightcore",
                 "8d", "reaction", "mashup", "tribute", "instrumental", "reverb", "how to")
_YT_MILD_BAD_WORDS = ("take", "demo", "alternate", "session", "rehearsal", "outtake", "version", "mono")

def _search_music_songs(query):
    """Song results (audio tracks, no music videos) of a YouTube Music search: [{id, title, channel, length}]."""
    from ytmusicapi import YTMusic  # imported here: the search needs no sign-in
    return [{
        "id": r["videoId"],
        "title": r.get("title", ""),
        "channel": ", ".join(a["name"] for a in r.get("artists") or []),
        "length": r.get("duration") or "",
    } for r in YTMusic().search(query, filter="songs", limit=10) if r.get("videoId")]

def _score_video(video, artist, title):
    """Higher is a better stand-in for the studio recording; None when it is clearly another song."""
    t = _norm_text(re.sub(r"\(.*?\)|\[.*?\]", "", title))
    a = _norm_text(artist)
    title_n, chan_n = _norm_text(video["title"]), _norm_text(video["channel"])
    if not t or t not in title_n:
        return None
    score = 0
    if a and (a in chan_n or chan_n in a):
        score += 4
    elif a and a in title_n:
        score += 1
    if "official audio" in title_n or "official video" in title_n or "official music video" in title_n:
        score += 3
    elif "audio" in title_n or "official" in title_n:
        score += 1
    padded = f" {title_n} "
    score -= 4 * sum(1 for w in _YT_BAD_WORDS if f" {w} " in padded)
    score -= 2 * sum(1 for w in _YT_MILD_BAD_WORDS if f" {w} " in padded)
    return score

def _is_embeddable(video_id):
    try:
        r = requests.get("https://www.youtube.com/oembed",
                         params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}, timeout=8)
        return r.status_code == 200
    except Exception:
        return False

# ── Keep the YouTube Music playlist in step with a replaced video ───────────────
YT_SCOPES = ["https://www.googleapis.com/auth/youtube"]
YT_TOKEN_PATH = os.path.join(WEB_CONFIG_DIR, "youtube_token.json")
YT_API_LINK = "https://console.cloud.google.com/apis/library/youtube.googleapis.com"

class YouTubeAuthRequired(Exception):
    pass

def get_youtube_service(interactive=False):
    """YouTube Data API client for the user's account (separate token: it needs a wider scope than Sheets)."""
    creds = None
    if os.path.exists(YT_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(YT_TOKEN_PATH, YT_SCOPES)
    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not interactive:
            raise YouTubeAuthRequired()
        flow = InstalledAppFlow.from_client_secrets_file(os.path.join(WEB_CONFIG_DIR, "client_secret.json"), YT_SCOPES)
        creds = flow.run_local_server(port=0)
    with open(YT_TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def _insert_playlist_item(yt, snippet):
    """Add a video to a playlist at snippet["position"]; playlists that aren't sorted manually reject a
    position, so those get the video appended (their order comes from their own sort setting)."""
    try:
        yt.playlistItems().insert(part="snippet", body={"snippet": snippet}).execute()
    except HttpError as err:
        if "manualSortRequired" not in str(err) or "position" not in snippet:
            raise
        snippet = {k: v for k, v in snippet.items() if k != "position"}
        yt.playlistItems().insert(part="snippet", body={"snippet": snippet}).execute()

def replace_video_in_playlists(yt, old_id, new_id, hint=""):
    """Swap old_id for new_id (same position) in the user's playlists. The playlists named like `hint` go first
    and, when one of them has the video, the others are left alone. Returns the titles that were changed."""
    playlists, token = [], None
    while True:
        page = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token).execute()
        playlists += page.get("items", [])
        token = page.get("nextPageToken")
        if not token:
            break
    hint_n = _norm_text(re.sub(r"\(.*?\)", "", hint))
    def matches_hint(p):
        t = _norm_text(p["snippet"]["title"])
        return bool(hint_n) and (t.startswith(hint_n) or hint_n.startswith(t))
    groups = [[p for p in playlists if matches_hint(p)], [p for p in playlists if not matches_hint(p)]]

    for group in groups:
        changed = []
        for p in group:
            items = yt.playlistItems().list(part="snippet", playlistId=p["id"], videoId=old_id, maxResults=50).execute().get("items", [])
            for it in items:
                snippet = {"playlistId": p["id"], "resourceId": {"kind": "youtube#video", "videoId": new_id}}
                if it["snippet"].get("position") is not None:
                    snippet["position"] = it["snippet"]["position"]
                # add the new one first so a failure never leaves the playlist without the song
                _insert_playlist_item(yt, snippet)
                yt.playlistItems().delete(id=it["id"]).execute()
                if p["snippet"]["title"] not in changed:
                    changed.append(p["snippet"]["title"])
        if changed:
            return changed
    return []

def _all_playlists(yt):
    playlists, token = [], None
    while True:
        page = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token).execute()
        playlists += page.get("items", [])
        token = page.get("nextPageToken")
        if not token:
            return playlists

def sync_song_in_playlists(yt, artist, title, video_id, hint=""):
    """Make the playlist entry for this song point at video_id: finds the entry by title/artist (the old
    video id is not needed) and swaps it in place. Returns (changed_titles, already_ok)."""
    song_n = _norm_text(re.sub(r"\(.*?\)|\[.*?\]", "", title))
    artist_n = _norm_text(artist)
    hint_n = _norm_text(re.sub(r"\(.*?\)", "", hint))
    playlists = _all_playlists(yt)
    def matches_hint(p):
        t = _norm_text(p["snippet"]["title"])
        return bool(hint_n) and (t.startswith(hint_n) or hint_n.startswith(t))
    already_ok = False
    for group in ([p for p in playlists if matches_hint(p)], [p for p in playlists if not matches_hint(p)]):
        changed = []
        for p in group:
            items, token = [], None
            while True:
                page = yt.playlistItems().list(part="snippet", playlistId=p["id"], maxResults=50, pageToken=token).execute()
                items += page.get("items", [])
                token = page.get("nextPageToken")
                if not token:
                    break
            for it in items:
                sn = it["snippet"]
                item_title = _norm_text(sn.get("title", ""))
                owner = _norm_text(sn.get("videoOwnerChannelTitle", ""))
                if song_n not in item_title or not (artist_n in owner or artist_n in item_title):
                    continue
                if sn["resourceId"]["videoId"] == video_id:
                    already_ok = True
                    continue
                snippet = {"playlistId": p["id"], "resourceId": {"kind": "youtube#video", "videoId": video_id}}
                if sn.get("position") is not None:
                    snippet["position"] = sn["position"]
                _insert_playlist_item(yt, snippet)
                yt.playlistItems().delete(id=it["id"]).execute()
                if p["snippet"]["title"] not in changed:
                    changed.append(p["snippet"]["title"])
        if changed:
            return changed, already_ok
    return [], already_ok
