"""Key estimation from the 30 s Deezer preview of a song (harmonic chroma + Temperley key profiles).

Only the key is estimated: chord order from a short preview is not reliable. Needs `ffmpeg` on the PATH.
"""
import functools
import shutil
import subprocess

import numpy as np
import requests

from .bpm import _norm_text
from .harmony import (NOTE_MAP, SEMITONES, clean_and_extract_chords, key_scores_from_chords,
                      parse_chord_root_and_quality)
from .key_fusion import fuse

SAMPLE_RATE = 22050
HOP = 2048

# Same spellings the dashboard's key selector uses (see shiftTonalityKey in web/app.js)
MAJOR_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
MINOR_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B']
# Temperley's profiles scored best on 60 sheet songs (Krumhansl and Albrecht-Shanahan were worse)
MAJOR_PROFILE = np.array([5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0])
MINOR_PROFILE = np.array([5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0])


# Scale of each mode (the minor one includes the raised 7th, so V and vii° chords are not penalised)
MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10, 11)
# Quality gates: a clip quieter than this (RMS of the samples, full scale = 1) or a chroma this flat holds no key
MIN_RMS = 1e-3
MIN_CHROMA_STD = 1e-6
# How much a key loses when all of the song's chord tones fall outside its scale
CHORD_MISFIT_WEIGHT = 1.5


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


def _chroma_frames(samples):
    """12 x frames pitch-class energy of the clip, from its harmonic part (drums blur the key)."""
    if len(samples) < SAMPLE_RATE * 5:
        raise AudioKeyError("Audio demasiado corto")
    if not np.isfinite(samples).all():
        raise AudioKeyError("Audio corrupto")
    if float(np.sqrt(np.mean(np.square(samples, dtype=np.float64)))) < MIN_RMS:
        raise AudioKeyError("Audio silencioso: no hay música que analizar")
    try:
        import librosa  # heavy import: only paid by the first key estimation
    except ImportError:
        raise AudioKeyError("Falta librosa (pip install -r requirements.txt)")
    harmonic = librosa.effects.harmonic(samples, margin=4)
    frames = librosa.feature.chroma_cqt(y=harmonic, sr=SAMPLE_RATE, hop_length=HOP, bins_per_octave=36)
    if not np.isfinite(frames).all():
        raise AudioKeyError("No se pudo calcular el contenido armónico del audio")
    return frames


def _chroma_profile(samples):
    """Average 12-bin pitch-class energy of the clip."""
    return _chroma_frames(samples).mean(axis=1)


def chord_chroma(chord_text):
    """12-bin pitch-class weight of the chord tones in a chord text (one count per chord written), or None."""
    weights = np.zeros(12)
    for name in clean_and_extract_chords(chord_text or ""):
        root, quality, suffix = parse_chord_root_and_quality(name)
        if root not in NOTE_MAP:
            continue
        r = SEMITONES.index(NOTE_MAP[root])
        third = {"minor": 3, "dim": 3}.get(quality, 4)
        fifth = {"dim": 6, "aug": 8}.get(quality, 7)
        tones = [0, third, fifth]
        low = suffix.lower()
        if "maj7" in low or "m7" in low and "maj" in low:
            tones.append(11)
        elif "7" in low:
            tones.append(10)
        for t in tones:
            weights[(r + t) % 12] += 1
    return weights if weights.sum() else None


def _chord_misfit(chords, tonic, scale):
    """Share of the chord-tone weight that lies outside the key's scale (0 = every chord is diatonic)."""
    inside = {(tonic + d) % 12 for d in scale}
    outside = sum(w for pc, w in enumerate(chords) if pc not in inside)
    return float(outside / chords.sum())


def check_chroma(chroma):
    """Raises AudioKeyError when the 12-bin profile cannot say anything about the key (flat, empty or not finite);
    correlating it would give NaN and a key that looks precise but is not."""
    chroma = np.asarray(chroma, dtype=float)
    if chroma.shape != (12,) or not np.isfinite(chroma).all() or float(np.std(chroma)) < MIN_CHROMA_STD:
        raise AudioKeyError("El audio no tiene contenido armónico analizable")
    return chroma


def key_candidates(chroma, chords=None):
    """All 24 keys ranked by correlation with the key profiles. With the song's chord tones, keys that
    cannot hold those chords (B Major for Em7 - Gmaj7 - Bm) lose score in proportion to how many tones they miss."""
    chroma = check_chroma(chroma)
    ranked = []
    for tonic in range(12):
        for names, profile, scale, mode in ((MAJOR_NAMES, MAJOR_PROFILE, MAJOR_SCALE, "Major"),
                                            (MINOR_NAMES, MINOR_PROFILE, MINOR_SCALE, "Minor")):
            audio = float(np.corrcoef(np.roll(profile, tonic), chroma)[0, 1])
            score = audio
            if chords is not None:
                score -= CHORD_MISFIT_WEIGHT * _chord_misfit(chords, tonic, scale)
            ranked.append({"tonality": f"{names[tonic]} {mode}", "score": round(score, 3), "audio": round(audio, 3)})
    return sorted(ranked, key=lambda c: c["score"], reverse=True)


@functools.lru_cache(maxsize=32)
def _preview_frames(artist, title):
    """Chroma frames (12 x T) of the song's Deezer preview, or None if Deezer has no preview."""
    url = _find_preview_url(artist, title)
    if not url:
        return None
    audio = requests.get(url, timeout=20)
    audio.raise_for_status()
    return _chroma_frames(_decode_mono(audio.content))


def _preview_chroma(artist, title):
    """Pitch-class profile of the song's Deezer preview, or None if Deezer has no preview."""
    frames = _preview_frames(artist, title)
    return None if frames is None else frames.mean(axis=1)


def _key_id(tonality):
    """(pitch class, mode) of 'Bb Major', so that spellings of the same key compare equal."""
    name, mode = tonality.rsplit(" ", 1)
    return SEMITONES.index(NOTE_MAP.get(name, name)), mode


def _key_name(key):
    """'Eb Major' from (3, 'Major'), with the spellings of the dashboard's key selector."""
    pitch, mode = key
    return f"{(MINOR_NAMES if mode == 'Minor' else MAJOR_NAMES)[pitch]} {mode}"


def estimate_key(artist, title, chord_text=None):
    """{'tonality', 'score', 'candidates', 'agree', 'sources'} from the song's Deezer preview, or None if Deezer has no
    preview. The audio's key profiles and the written chords (chord_text) are fused (see key_fusion): the audio alone
    often mixes a key with its relative or parallel mode, the chords alone take the IV for the tonic in vamps.
    'score' ranks the candidates; it is not a calibrated chance of being right. 'agree' tells whether the audio and the
    chords pointed at the same key (None without readable chords)."""
    chroma = _preview_chroma(artist, title)
    if chroma is None:
        return None
    audio_scores = {_key_id(c["tonality"]): c["audio"] for c in key_candidates(chroma)}
    chord_scores, _ = key_scores_from_chords(clean_and_extract_chords(chord_text or ""))
    fused = fuse(audio_scores, chord_scores or None)
    keys = fused["keys"]
    return {"tonality": _key_name(keys[0]["key"]), "score": round(keys[0]["probability"], 3),
            "candidates": [{"tonality": _key_name(k["key"]), "score": round(k["probability"], 3)} for k in keys[:3]],
            "agree": fused["agree"],
            "sources": {"audio": _key_name(max(audio_scores, key=audio_scores.get)),
                        "chords": _key_name(max(chord_scores, key=chord_scores.get)) if chord_scores else None}}


# Chords heard in the preview: diatonic triads of the key, one guess per window of audio
CHORD_WINDOW_SECONDS = 2.0
_MAJOR_TRIADS = ((0, "major"), (2, "minor"), (4, "minor"), (5, "major"), (7, "major"), (9, "minor"))
_MINOR_TRIADS = ((0, "minor"), (3, "major"), (5, "minor"), (7, "minor"), (7, "major"), (8, "major"), (10, "major"))


def chords_in_frames(frames, tonality):
    """Chord sequence (['Am', 'F', ...], repeats merged) heard in the chroma frames, choosing among the
    diatonic triads of the tonality ('A Minor'). It is a hint for the chord sheet, not a transcription."""
    name, mode = tonality.rsplit(" ", 1)
    names = MINOR_NAMES if mode == "Minor" else MAJOR_NAMES
    tonic = names.index(name) if name in names else SEMITONES.index(NOTE_MAP[name])
    candidates = []
    for degree, quality in (_MINOR_TRIADS if mode == "Minor" else _MAJOR_TRIADS):
        root = (tonic + degree) % 12
        template = np.zeros(12)
        for tone in (0, 3 if quality == "minor" else 4, 7):
            template[(root + tone) % 12] = 1.0
        candidates.append((names[root] + ("m" if quality == "minor" else ""), template))
    step = max(1, int(CHORD_WINDOW_SECONDS * SAMPLE_RATE / HOP))
    sequence = []
    for start in range(0, frames.shape[1], step):
        window = frames[:, start:start + step].mean(axis=1)
        if window.sum() <= 0:
            continue
        best = max(candidates, key=lambda c: float(np.dot(c[1], window) / (np.linalg.norm(c[1]) * np.linalg.norm(window))))
        if not sequence or sequence[-1] != best[0]:
            sequence.append(best[0])
    return sequence


def estimate_preview_chords(artist, title):
    """{'tonality', 'chords'} heard in the song's Deezer preview, or None if Deezer has no preview."""
    frames = _preview_frames(artist, title)
    if frames is None:
        return None
    ranked = key_candidates(frames.mean(axis=1))
    tonality = ranked[0]["tonality"]
    return {"tonality": tonality, "chords": chords_in_frames(frames, tonality)}
