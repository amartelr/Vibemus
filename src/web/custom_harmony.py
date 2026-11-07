"""Custom harmony source: lyrics from LRCLIB or lyrics.ovh (free, no key) + key and chords heard in the Deezer preview,
turned into a chord sheet by Gemini. The result has the same shape as an Ultimate Guitar suggestion."""
import re
from urllib.parse import quote

import requests

from .audio_key import AudioKeyError, estimate_key, estimate_preview_chords
from .bpm import _lookup_bpm, _norm_text
from .gemini import generate_chord_sheet, generate_lyrics_sheet
from .harmony import (clean_and_extract_chords, detect_key_from_chords, infer_complexity,
                      infer_emotional_style, infer_progression)
from .pdf_import import _PDF_CHORD_RE, normalize_pdf_chord
from .tabs import clean_ug_content, extract_lyrics_with_chords

LRCLIB_URL = "https://lrclib.net/api"
LYRICS_OVH_URL = "https://api.lyrics.ovh/v1"
LRCLIB_HEADERS = {"User-Agent": "Vibemus (personal dashboard)"}
CHORD_TAG = re.compile(r"\[ch(?:\s[^\]]*)?](.*?)\[/ch\]", re.IGNORECASE)


def fetch_lyrics(artist, title):
    """Plain lyrics of the song (LRCLIB first, lyrics.ovh as a fallback), or '' when neither has them."""
    return _lrclib_lyrics(artist, title) or _lyrics_ovh(artist, title)


def _lyrics_ovh(artist, title):
    try:
        res = requests.get(f"{LYRICS_OVH_URL}/{quote(artist, safe='')}/{quote(title, safe='')}", timeout=15)
        return (res.json().get("lyrics") or "").strip() if res.status_code == 200 else ""
    except (requests.RequestException, ValueError):
        return ""


def _lrclib_lyrics(artist, title):
    try:
        hit = requests.get(f"{LRCLIB_URL}/get", params={"artist_name": artist, "track_name": title},
                           headers=LRCLIB_HEADERS, timeout=10)
        if hit.status_code == 200 and hit.json().get("plainLyrics"):
            return hit.json()["plainLyrics"].strip()
        found = requests.get(f"{LRCLIB_URL}/search", params={"artist_name": artist, "track_name": title},
                             headers=LRCLIB_HEADERS, timeout=10).json()
    except (requests.RequestException, ValueError):
        return ""
    want_artist, want_title = _norm_text(artist), _norm_text(title)
    for item in found if isinstance(found, list) else []:
        if want_artist in _norm_text(item.get("artistName", "")) and want_title in _norm_text(item.get("trackName", "")) \
                and item.get("plainLyrics"):
            return item["plainLyrics"].strip()
    return ""


def sanitize_markup(text):
    """Keeps the sheet readable by the Ultimate Guitar parsers: normalizes chord names and unwraps anything
    inside [ch] that is not a chord (the model sometimes tags words)."""
    def fix(m):
        chord = normalize_pdf_chord(m.group(1).strip())
        return f"[ch]{chord}[/ch]" if _PDF_CHORD_RE.match(chord) else ""
    return CHORD_TAG.sub(fix, text.replace("\r", ""))


def fetch_custom_chords(artist, title, fresh=False):
    """Suggestion {chord, tonality, progression, lyrics_with_chords, ...} or None when there is nothing to work from.
    Raises GeminiError / RuntimeError (Gemini), which the route reports to the user."""
    lyrics = fetch_lyrics(artist, title)
    try:
        heard = estimate_preview_chords(artist, title)
    except AudioKeyError as e:
        print(f"Custom harmony: no audio analysis for {artist} - {title}: {e}")
        heard = None
    except Exception as e:
        print(f"Custom harmony: audio analysis failed for {artist} - {title}: {e}")
        heard = None
    if not lyrics and not heard:
        return None

    raw = sanitize_markup(generate_chord_sheet(artist, title, heard["tonality"] if heard else "desconocida",
                                               lyrics, heard["chords"] if heard else [], fresh=fresh))
    chord_string = clean_ug_content(raw)
    if not clean_and_extract_chords(chord_string):
        return None
    lyrics_with_chords = extract_lyrics_with_chords(raw)

    # Same key logic as "detectar tonalidad": the audio decides, and the written chords rule out keys they do not fit
    tonality = None
    try:
        key = estimate_key(artist, title, chord_string)
        tonality = key["tonality"] if key else None
    except Exception:
        pass
    tonality = tonality or detect_key_from_chords(clean_and_extract_chords(chord_string))

    try:
        bpm = _lookup_bpm(artist, title)
    except Exception:
        bpm = None
    return {
        "found": True,
        "artist": artist,
        "title": title,
        "chord": chord_string,
        "tonality": tonality,
        "progression": infer_progression(chord_string, tonality),
        "complex": infer_complexity(chord_string, tonality),
        "style": infer_emotional_style(chord_string, tonality),
        "confidence": 0.7 if heard and lyrics else 0.5,
        "source": "Personalizada (letra + audio + Gemini)",
        "lyrics_with_chords": lyrics_with_chords,
        "has_lyrics": bool(lyrics and lyrics_with_chords),
        "bpm": bpm,
    }


def add_lyrics_to_chords(artist, title, chord_text, tonality="", lyrics="", fresh=False):
    """Lays the song's existing chords over its lyrics (given, or found online) without touching the chords.
    Returns {'lyrics_with_chords', 'lyrics_found'}, or None when no lyrics are available.
    Raises GeminiError / RuntimeError (Gemini), which the route reports to the user."""
    lyrics = (lyrics or "").strip() or fetch_lyrics(artist, title)
    if not lyrics:
        return None
    raw = sanitize_markup(generate_lyrics_sheet(artist, title, tonality, chord_text, lyrics, fresh=fresh))
    sheet = extract_lyrics_with_chords(raw)
    if not sheet:
        return None
    return {"lyrics_with_chords": sheet}
