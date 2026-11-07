"""Reconocimiento de acordes del preview con opción de "sin acorde" (Fase 3). Uso: .venv/bin/python -m pytest scratch/test_chord_frames.py"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.web import audio_key  # noqa: E402
from src.web.audio_key import NO_CHORD, SAMPLE_RATE, HOP, chords_in_frames  # noqa: E402

WINDOW = max(1, int(audio_key.CHORD_WINDOW_SECONDS * SAMPLE_RATE / HOP))
PC = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def window_of(*notes, noise=0.0, scale=1.0):
    """One 12 x WINDOW block with the given pitch classes lit."""
    block = np.full((12, WINDOW), noise)
    for n in notes:
        block[PC[n], :] += scale
    return block


def clip(*blocks):
    return np.concatenate(blocks, axis=1)


def test_silence_is_no_chord():
    assert chords_in_frames(np.zeros((12, WINDOW * 3)), "A Minor") == [NO_CHORD]


def test_clear_diatonic_chords_are_named():
    frames = clip(window_of("A", "C", "E"), window_of("F", "A", "C"), window_of("C", "E", "G"), window_of("G", "B", "D"))
    assert chords_in_frames(frames, "A Minor") == ["Am", "F", "C", "G"]
    assert chords_in_frames(frames, "C Major") == ["Am", "F", "C", "G"]


def test_repeats_are_merged():
    frames = clip(window_of("A", "C", "E"), window_of("A", "C", "E"), window_of("F", "A", "C"))
    assert chords_in_frames(frames, "A Minor") == ["Am", "F"]


def test_chromatic_chord_is_not_forced_onto_a_diatonic_triad():
    # F# major (F# A# C#) shares no note with any triad of C major
    frames = clip(window_of("C", "E", "G"), window_of("F#", "A#", "C#"), window_of("C", "E", "G"))
    assert chords_in_frames(frames, "C Major") == ["C", NO_CHORD, "C"]


def test_flat_noise_is_no_chord():
    # every pitch class equally loud resembles no triad more than another
    frames = window_of(*PC, scale=1.0)
    assert chords_in_frames(np.concatenate([frames, frames], axis=1), "C Major") == [NO_CHORD]


def test_threshold_is_adjustable():
    # a C major triad with a lot of noise on top: named with a lax threshold, "no chord" with a strict one
    frames = window_of("C", "E", "G", noise=0.6)
    assert chords_in_frames(frames, "C Major", min_similarity=0.5) == ["C"]
    assert chords_in_frames(frames, "C Major", min_similarity=0.95) == [NO_CHORD]


def test_estimate_preview_chords_leaves_out_no_chord(monkeypatch):
    frames = clip(window_of("C", "E", "G"), window_of("F#", "A#", "C#"), window_of("G", "B", "D"), window_of("C", "E", "G"))
    monkeypatch.setattr(audio_key, "_preview_frames", lambda artist, title: frames)
    monkeypatch.setattr(audio_key, "key_candidates", lambda chroma: [{"tonality": "C Major", "score": 1.0, "audio": 1.0}])
    heard = audio_key.estimate_preview_chords("A", "T")
    assert heard == {"tonality": "C Major", "chords": ["C", "G", "C"]}
    monkeypatch.setattr(audio_key, "_preview_frames", lambda artist, title: None)
    assert audio_key.estimate_preview_chords("A", "T") is None


def test_chord_names_follow_the_key_signature():
    # D#m and G#m in B major (not Ebm / Abm); Cm and Eb in Bb major keep their flats
    sharp = clip(window_of("D#", "F#", "A#"), window_of("G#", "B", "D#"))
    assert chords_in_frames(sharp, "B Major") == ["D#m", "G#m"]
    flat = clip(window_of("C", "D#", "G"), window_of("D#", "G", "A#"))
    assert chords_in_frames(flat, "Bb Major") == ["Cm", "Eb"]
    assert audio_key.chord_root_names("F Major")[10] == "Bb" and audio_key.chord_root_names("E Major")[10] == "A#"
