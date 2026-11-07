"""Fusión de tonalidad por audio y por acordes (Fase 2). Uso: .venv/bin/python -m pytest scratch/test_key_fusion.py"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.web import audio_key  # noqa: E402
from src.web.harmony import detect_key_from_chords, key_scores_from_chords  # noqa: E402
from src.web.key_fusion import fuse, softmax  # noqa: E402

C_MAJOR_CHROMA = np.array([1.0, 0.1, 0.5, 0.1, 0.8, 0.6, 0.1, 0.9, 0.1, 0.5, 0.1, 0.4])


def test_key_scores_cover_24_keys_and_agree_with_detection():
    scores, flats = key_scores_from_chords(["Am", "F", "C", "G"])
    assert len(scores) == 24
    tonic, mode = max(scores, key=scores.get)
    assert detect_key_from_chords(["Am", "F", "C", "G"]).split()[1] == mode
    assert key_scores_from_chords([]) == ({}, False)
    assert key_scores_from_chords(["xyz"])[0] == {}


def test_softmax_sums_to_one_and_keeps_order():
    p = softmax({"a": 3.0, "b": 1.0, "c": -2.0}, 1.0)
    assert sum(p.values()) == pytest.approx(1.0) and p["a"] > p["b"] > p["c"]


def test_fuse_with_one_source_or_none():
    only_audio = fuse({(0, "Major"): 0.9, (9, "Minor"): 0.5}, None)
    assert only_audio["keys"][0]["key"] == (0, "Major") and only_audio["agree"] is None
    assert fuse({(0, "Major"): 1.0}, None)["keys"][0]["chords"] is None
    assert fuse(None, None) is None and fuse({}, {}) is None


def test_fuse_mix_lets_a_strong_source_win_and_reports_agreement():
    audio = {(0, "Major"): 0.9, (9, "Minor"): 0.88, (7, "Major"): 0.3}
    chords = {(0, "Major"): 2.0, (9, "Minor"): 18.0, (7, "Major"): 1.0}
    fused = fuse(audio, chords)
    assert fused["keys"][0]["key"] == (9, "Minor")          # the chords are far more decisive here
    assert fused["agree"] is False
    assert sum(k["probability"] for k in fused["keys"]) == pytest.approx(1.0)
    assert fuse(audio, {(0, "Major"): 20.0, (9, "Minor"): 1.0, (7, "Major"): 0.0})["agree"] is True


def _stub_preview(monkeypatch, chroma):
    monkeypatch.setattr(audio_key, "_preview_chroma", lambda artist, title: chroma)


def test_estimate_key_fuses_audio_and_chords(monkeypatch):
    _stub_preview(monkeypatch, C_MAJOR_CHROMA)
    result = audio_key.estimate_key("A", "T", "Am F C G Am F C G")
    assert result["tonality"] in ("C Major", "A Minor")
    assert len(result["candidates"]) == 3 and result["candidates"][0]["tonality"] == result["tonality"]
    assert result["sources"]["audio"] == "C Major" and result["sources"]["chords"] is not None
    assert isinstance(result["agree"], bool)


def test_estimate_key_without_chords_uses_the_audio(monkeypatch):
    _stub_preview(monkeypatch, C_MAJOR_CHROMA)
    result = audio_key.estimate_key("A", "T", "")
    assert result["tonality"] == "C Major" and result["agree"] is None and result["sources"]["chords"] is None


def test_estimate_key_without_preview(monkeypatch):
    _stub_preview(monkeypatch, None)
    assert audio_key.estimate_key("A", "T", "C G") is None


def test_estimate_key_refuses_flat_audio(monkeypatch):
    _stub_preview(monkeypatch, np.full(12, 0.3))
    with pytest.raises(audio_key.AudioKeyError):
        audio_key.estimate_key("A", "T", "C G Am F")
