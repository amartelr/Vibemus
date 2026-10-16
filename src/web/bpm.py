"""Song tempo lookup (Deezer) and parsing."""
import re

import requests


# ── Song tempo: stored in the Songs sheet ("bpm" column), looked up on Deezer when missing ──
def _parse_bpm(raw):
    try:
        bpm = round(float(str(raw).replace(",", ".").strip()))
        return bpm if 20 <= bpm <= 300 else None
    except (TypeError, ValueError):
        return None

def _norm_text(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()

def _lookup_bpm(artist, title):
    """Deezer's tempo for the best matching track, folded into a playable 60–160 range."""
    query = requests.get("https://api.deezer.com/search", params={"q": f"{artist} {title}"}, timeout=10).json()
    want_artist = _norm_text(artist)
    for hit in query.get("data", [])[:6]:
        if want_artist not in _norm_text(hit.get("artist", {}).get("name", "")):
            continue
        track = requests.get(f"https://api.deezer.com/track/{hit['id']}", timeout=10).json()
        bpm = float(track.get("bpm") or 0)
        if bpm > 0:
            # Detectors often report double time (e.g. 171 for an 86 BPM song)
            while bpm > 160:
                bpm /= 2
            while bpm < 60:
                bpm *= 2
            return round(bpm)
    return None
