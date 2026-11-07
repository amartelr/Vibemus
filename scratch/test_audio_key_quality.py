"""Controles de calidad del análisis de audio (punto 7 del plan). Uso: .venv/bin/python -m pytest scratch/test_audio_key_quality.py"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.web import audio_key  # noqa: E402
from src.web.audio_key import SAMPLE_RATE, AudioKeyError, _chroma_frames, key_candidates  # noqa: E402


def tone(freqs, seconds, amp=0.3):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (amp * sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)).astype(np.float32)


C_MAJOR = (261.63, 329.63, 392.00)


def test_empty_audio_is_rejected():
    with pytest.raises(AudioKeyError):
        _chroma_frames(np.zeros(0, dtype=np.float32))


def test_silent_audio_is_rejected():
    with pytest.raises(AudioKeyError, match="silencioso"):
        _chroma_frames(np.zeros(SAMPLE_RATE * 10, dtype=np.float32))


def test_very_quiet_audio_is_rejected():
    with pytest.raises(AudioKeyError, match="silencioso"):
        _chroma_frames(tone(C_MAJOR, 10, amp=1e-5))


def test_non_finite_audio_is_rejected():
    samples = tone(C_MAJOR, 10)
    samples[100] = np.nan
    with pytest.raises(AudioKeyError, match="corrupto"):
        _chroma_frames(samples)


@pytest.mark.parametrize("chroma", [np.full(12, 0.5), np.zeros(12), np.full(12, np.nan), np.ones(11)])
def test_flat_or_invalid_chroma_has_no_key(chroma):
    with pytest.raises(AudioKeyError):
        key_candidates(chroma)


def test_clear_tonality_is_found():
    ranked = key_candidates(_chroma_frames(tone(C_MAJOR, 10)).mean(axis=1))
    assert ranked[0]["tonality"] == "C Major"
    assert np.isfinite([c["score"] for c in ranked]).all()


def test_long_silence_with_a_useful_section_still_works():
    samples = np.concatenate([np.zeros(SAMPLE_RATE * 8, dtype=np.float32), tone(C_MAJOR, 8)])
    assert key_candidates(_chroma_frames(samples).mean(axis=1))[0]["tonality"] == "C Major"
