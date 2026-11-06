"""Key estimation from the 30 s Deezer preview of a song (harmonic chroma + Temperley key profiles).

Only the key is estimated: chord order from a short preview is not reliable. Needs `ffmpeg` on the PATH.
"""
import functools
import shutil
import subprocess

import numpy as np
import requests

from .bpm import _norm_text

SAMPLE_RATE = 22050
HOP = 2048

# Same spellings the dashboard's key selector uses (see shiftTonalityKey in web/app.js)
MAJOR_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
MINOR_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B']
# Temperley's profiles scored best on 60 sheet songs (Krumhansl and Albrecht-Shanahan were worse)
MAJOR_PROFILE = np.array([5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0])
MINOR_PROFILE = np.array([5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0])


class AudioKeyError(Exception):
    pass


def _find_preview_url(artist, title):
    query = requests.get("https://api.deezer.com/search", params={"q": f"{artist} {title}"}, timeout=10).json()
    want_artist, want_title = _norm_text(artist), _norm_text(title)
    for hit in query.get("data", [])[:8]:
        if want_artist not in _norm_text(hit.get("artist", {}).get("name", "")):
            continue
        if want_title not in _norm_text(hit.get("title", "")) and _norm_text(hit.get("title", "")) not in want_title:
            continue
        if hit.get("preview"):
            return hit["preview"]
    return None


def _decode_mono(mp3_bytes):
    if not shutil.which("ffmpeg"):
        raise AudioKeyError("ffmpeg no está instalado (brew install ffmpeg)")
    proc = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"],
        input=mp3_bytes, capture_output=True, timeout=60)
    if proc.returncode != 0 or not proc.stdout:
        raise AudioKeyError("No se pudo decodificar el audio")
    return np.frombuffer(proc.stdout, dtype=np.float32)


def _chroma_profile(samples):
    """Average 12-bin pitch-class energy of the clip, from its harmonic part (drums blur the key)."""
    if len(samples) < SAMPLE_RATE * 5:
        raise AudioKeyError("Audio demasiado corto")
    try:
        import librosa  # heavy import: only paid by the first key estimation
    except ImportError:
        raise AudioKeyError("Falta librosa (pip install -r requirements.txt)")
    harmonic = librosa.effects.harmonic(samples, margin=4)
    chroma = librosa.feature.chroma_cqt(y=harmonic, sr=SAMPLE_RATE, hop_length=HOP, bins_per_octave=36)
    return chroma.mean(axis=1)


def key_candidates(chroma):
    """All 24 keys ranked by correlation with the key profiles."""
    ranked = []
    for tonic in range(12):
        for names, profile, mode in ((MAJOR_NAMES, MAJOR_PROFILE, "Major"), (MINOR_NAMES, MINOR_PROFILE, "Minor")):
            r = float(np.corrcoef(np.roll(profile, tonic), chroma)[0, 1])
            ranked.append({"tonality": f"{names[tonic]} {mode}", "score": round(r, 3)})
    return sorted(ranked, key=lambda c: c["score"], reverse=True)


@functools.lru_cache(maxsize=128)
def estimate_key(artist, title):
    """{'tonality', 'score', 'candidates'} from the song's Deezer preview, or None if Deezer has no preview."""
    url = _find_preview_url(artist, title)
    if not url:
        return None
    audio = requests.get(url, timeout=20)
    audio.raise_for_status()
    ranked = key_candidates(_chroma_profile(_decode_mono(audio.content)))
    return {"tonality": ranked[0]["tonality"], "score": ranked[0]["score"], "candidates": ranked[:3]}
