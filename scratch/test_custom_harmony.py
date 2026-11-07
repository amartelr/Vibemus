"""Custom harmony source (lyrics + audio + Gemini) with everything external faked."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.web import audio_key, custom_harmony, server

SHEET = """[Intro]
[ch]Am[/ch] [ch]F[/ch] [ch]C[/ch] [ch]G[/ch]
[Verse 1]
[ch]Am[/ch]La luna sobre el [ch]F[/ch]mar
[ch]C[/ch]canta una can[ch]G[/ch]ción
[Chorus]
[ch]F[/ch]Vamos a bai[ch]C[/ch]lar
[ch]xyz[/ch]palabra
"""


def fake_sources(monkeypatch, lyrics="La luna sobre el mar\ncanta una canción", heard=None):
    monkeypatch.setattr(custom_harmony, "fetch_lyrics", lambda a, t: lyrics)
    monkeypatch.setattr(custom_harmony, "estimate_preview_chords",
                        lambda a, t: heard if heard is not None else {"tonality": "A Minor", "chords": ["Am", "F"]})
    monkeypatch.setattr(custom_harmony, "generate_chord_sheet", lambda *a, **k: SHEET)
    monkeypatch.setattr(custom_harmony, "estimate_key", lambda a, t, chord: {"tonality": "A Minor"})
    monkeypatch.setattr(custom_harmony, "_lookup_bpm", lambda a, t: 90)


def test_custom_suggestion_has_the_ultimate_guitar_shape(monkeypatch):
    fake_sources(monkeypatch)
    res = custom_harmony.fetch_custom_chords("Artista", "Canción")
    assert res["found"] and res["tonality"] == "A Minor" and res["bpm"] == 90
    assert res["chord"].startswith("<intro> Am F C G <verse_1> Am F C G")
    assert res["has_lyrics"]
    sections = {s["section"]: s["lines"] for s in res["lyrics_with_chords"]}
    first = sections["Verse 1"][0]
    assert first["lyric"] == "La luna sobre el mar"
    assert [c["chord"] for c in first["chords"]] == ["Am", "F"]
    assert "xyz" not in res["chord"]  # tagged words that are not chords are dropped


def test_custom_without_any_source_finds_nothing(monkeypatch):
    fake_sources(monkeypatch, lyrics="")
    monkeypatch.setattr(custom_harmony, "estimate_preview_chords", lambda a, t: None)
    assert custom_harmony.fetch_custom_chords("Artista", "Canción") is None


def test_route_uses_custom_source_and_reports_gemini_errors(monkeypatch):
    client = server.app.test_client()
    fake_sources(monkeypatch)
    ok = client.post("/api/suggest-harmony", json={"artist": "A", "title": "T", "source": "Personalizada"}).get_json()
    assert ok["found"] and ok["source"].startswith("Personalizada")

    def boom(*a, **k):
        raise RuntimeError("No se ha configurado la GEMINI_API_KEY en el servidor.")
    monkeypatch.setattr(custom_harmony, "generate_chord_sheet", boom)
    res = client.post("/api/suggest-harmony", json={"artist": "A", "title": "T", "source": "Personalizada"})
    assert res.status_code == 200 and res.get_json()["found"] is False and "GEMINI" in res.get_json()["message"]


def test_songsterr_is_gone():
    assert not hasattr(server, "fetch_songsterr_chords")


def test_chords_in_frames_follow_the_audio():
    def frames_for(pitch_classes, n):
        f = np.full((12, n), 0.05)
        f[list(pitch_classes), :] = 1.0
        return f
    n = int(audio_key.CHORD_WINDOW_SECONDS * audio_key.SAMPLE_RATE / audio_key.HOP)
    am, f_maj = frames_for([9, 0, 4], n), frames_for([5, 9, 0], n)
    seq = audio_key.chords_in_frames(np.hstack([am, am, f_maj, am]), "A Minor")
    assert seq == ["Am", "F", "Am"]


def test_lyrics_fall_back_to_lyrics_ovh(monkeypatch):
    monkeypatch.setattr(custom_harmony, "_lrclib_lyrics", lambda a, t: "")
    monkeypatch.setattr(custom_harmony, "_lyrics_ovh", lambda a, t: "una línea inventada")
    assert custom_harmony.fetch_lyrics("A", "T") == "una línea inventada"
    monkeypatch.setattr(custom_harmony, "_lrclib_lyrics", lambda a, t: "primera fuente")
    assert custom_harmony.fetch_lyrics("A", "T") == "primera fuente"



def test_add_lyrics_keeps_the_chords_and_reports_missing_lyrics(monkeypatch):
    client = server.app.test_client()
    monkeypatch.setattr(custom_harmony, "fetch_lyrics", lambda a, t: "")
    body = {"artist": "A", "title": "T", "chord": "<verse_1> Am F C G", "tonality": "A Minor"}
    res = client.post("/api/add-lyrics", json=body).get_json()
    assert res["found"] is False and res["needs_lyrics"] is True

    seen = {}
    def fake_sheet(artist, title, tonality, chord_text, lyrics, **kw):
        seen.update(chords=chord_text, lyrics=lyrics)
        return SHEET
    monkeypatch.setattr(custom_harmony, "generate_lyrics_sheet", fake_sheet)
    res = client.post("/api/add-lyrics", json={**body, "lyrics": "una línea inventada"}).get_json()
    assert res["found"] and seen == {"chords": "<verse_1> Am F C G", "lyrics": "una línea inventada"}
    assert any(l["chords"] for s in res["lyrics_with_chords"] for l in s["lines"])

    assert client.post("/api/add-lyrics", json={"artist": "A", "title": "T"}).status_code == 400


def test_budget_caps_gemini_retries(monkeypatch):
    from src.web import gemini
    clock = {"t": 0.0}
    monkeypatch.setattr(gemini.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(gemini.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    monkeypatch.setenv("GEMINI_API_KEY", "x")

    class Busy:
        status_code = 503

        def json(self):
            return {"error": {"message": "busy"}}

    timeouts = []

    def slow_post(url, **kw):
        timeouts.append(kw["timeout"])
        clock["t"] += kw["timeout"]  # a slow server uses up the whole timeout
        return Busy()

    monkeypatch.setattr(gemini.requests, "post", slow_post)
    with pytest.raises(gemini.GeminiError) as err:
        gemini._generate("prompt", budget_seconds=90)
    assert err.value.overloaded and "90 s" in str(err.value)
    assert len(timeouts) == 1 and timeouts[0] <= 90  # no second attempt once the budget is gone


def test_sheet_cache_is_reused_until_fresh(monkeypatch, tmp_path):
    from src.web import gemini, sheet_cache
    monkeypatch.setattr(sheet_cache, "CACHE_FILE", str(tmp_path / "sheets.json"))
    calls = []

    def fake_generate(prompt, temperature=None, budget_seconds=None):
        calls.append(prompt)
        return "[Verse 1]\n[ch]Am[/ch]hola"

    monkeypatch.setattr(gemini, "_generate", fake_generate)
    args = ("A", "T", "C Major", "<verse_1> Am", "hola")
    first = gemini.generate_lyrics_sheet(*args)
    again = gemini.generate_lyrics_sheet(*args)
    assert len(calls) == 1 and first == again
    gemini.generate_lyrics_sheet(*args, fresh=True)
    assert len(calls) == 2
