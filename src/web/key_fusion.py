"""Fuses the key heard in the audio with the key implied by the written chords.

Pure functions over plain numbers: both sources give a score for each of the 24 keys ((pitch class, "Major"|"Minor")),
but on different scales (a correlation between -1 and 1 vs a sum of chord weights that grows with the chord count).
Each is turned into a probability with a softmax and the two are mixed, so neither source overrules the other:
and when they disagree the result says so (`agree`) instead of hiding it.

scratch/eval_key_fusion.py tunes and measures it on the Liked songs, whose keys were reviewed by hand (196 songs with
audio): exact key audio 47 %, chords 61 %, this mix 66 % (68 % vs 63 % on the half not used to tune it).

No confidence or "ambiguous" flag is returned on purpose: the mixed probability, the margin to the runner-up, the
agreement between sources and the raw score gaps all predict whether the key is right barely better than chance
(AUC 0.52-0.60), so any threshold would look precise without being so. `probability` is a relative weight to rank the
candidates, not a calibrated chance of being right.
"""
import math

# Tuned on half of the Liked songs by scratch/eval_key_fusion.py (the other half measures the result)
WEIGHT_AUDIO = 0.4       # share of the audio in the mix; the chords get the rest
TEMP_AUDIO = 0.04        # softmax temperature of the audio correlations (small = trusts the best one more)
TEMP_CHORDS = 8.0        # softmax temperature of the chord scores


def softmax(scores, temperature):
    """{key: probability} from {key: score}; a higher score is more likely."""
    top = max(scores.values())
    weights = {k: math.exp((v - top) / temperature) for k, v in scores.items()}
    total = sum(weights.values())
    return {k: w / total for k, w in weights.items()}


def fuse(audio_scores=None, chord_scores=None, weight_audio=None, temp_audio=None, temp_chords=None):
    """Keys ranked from the evidence available.

    audio_scores / chord_scores: {(pitch class, mode): score} or None when that source is missing.
    Returns None when there is no evidence at all, else
    {"keys": [{"key", "probability", "audio", "chords"}, ...] best first,
     "agree": both sources chose the same key (None when only one source is available)}.
    """
    weight_audio = WEIGHT_AUDIO if weight_audio is None else weight_audio
    temp_audio = TEMP_AUDIO if temp_audio is None else temp_audio
    temp_chords = TEMP_CHORDS if temp_chords is None else temp_chords

    audio = softmax(audio_scores, temp_audio) if audio_scores else None
    chords = softmax(chord_scores, temp_chords) if chord_scores else None
    if audio is None and chords is None:
        return None
    keys = sorted(audio or chords)
    if audio is not None and chords is not None:
        mixed = {k: weight_audio * audio[k] + (1 - weight_audio) * chords[k] for k in keys}
    else:
        mixed = dict(audio or chords)
    ranked = sorted(keys, key=lambda k: (-mixed[k], k))
    rows = [{"key": k, "probability": mixed[k], "audio": audio[k] if audio else None,
             "chords": chords[k] if chords else None} for k in ranked]
    agree = None
    if audio is not None and chords is not None:
        agree = max(audio, key=audio.get) == max(chords, key=chords.get)
    return {"keys": rows, "agree": agree}
