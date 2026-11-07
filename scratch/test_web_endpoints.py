"""Main web endpoints against a fake sheet (no Google, no network)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.web import server
from src.services.sheet_gateway import SongSheet

HEADER = ["Playlist", "Artist", "Title", "Album", "Liked", "Year", "Genre", "Scrobble",
          "LastfmScrobble", "Video ID", "Chord", "Tonality", "Progression", "Complex",
          "Style", "LastScanned", "Lyrics", "Emotional", "Skill", "Improvisation", "bpm"]


class FakeWs:
    def __init__(self, rows):
        self.values = [HEADER] + rows
        self.written = []

    def get_all_values(self):
        return self.values

    def batch_update(self, data, value_input_option=None):
        self.written += data


def row(vid, artist, title, chord="", tonality=""):
    r = [""] * len(HEADER)
    r[0], r[1], r[2], r[4], r[9], r[10], r[11] = "#", artist, title, "TRUE", vid, chord, tonality
    return r


@pytest.fixture
def client(monkeypatch, tmp_path):
    from src.services import sheet_lock
    monkeypatch.setattr(sheet_lock, "LOCK_FILE", str(tmp_path / "l"))
    monkeypatch.setattr(sheet_lock, "BUSY_FILE", str(tmp_path / "b"))
    ws = FakeWs([row("v1", "Artist1", "Song1", "Am F C G", "C Major"), row("v2", "Artist2", "Song2")])
    fake = SongSheet()
    fake._ws = ws
    monkeypatch.setattr(server, "sheet", fake)
    c = server.app.test_client()
    c.ws = ws
    return c


def test_songs_lists_rows_with_parsed_fields(client):
    songs = client.get("/api/songs").get_json()
    assert [s["title"] for s in songs] == ["Song1", "Song2"]
    assert songs[0]["row"] == 2 and songs[0]["liked"] is True and songs[0]["videoId"] == "v1"


def test_update_writes_only_requested_cell_by_video_id(client):
    r = client.post("/api/update", json={"row": 2, "artist": "Artist2", "title": "Song2",
                                         "lookupVideoId": "v2", "chord": "Dm"})
    assert r.status_code == 200
    assert client.ws.written == [{"range": "K3", "values": [["Dm"]]}]


def test_update_unknown_song_is_400(client):
    r = client.post("/api/update", json={"row": 2, "artist": "No", "title": "One", "chord": "C"})
    assert r.status_code == 400 and client.ws.written == []


def test_update_requires_artist_and_title(client):
    r = client.post("/api/update", json={"row": 2, "chord": "C"})
    assert r.status_code == 400 and r.get_json()["error"] == "CLIENT_OUTDATED"


def test_analyze_chords(client):
    d = client.post("/api/analyze-chords", json={"chord": "C Am F G7 C"}).get_json()
    assert d["tonality"] == "C Major" and d["progression"] == "I - vi - IV - V7"


@pytest.mark.parametrize("chords, key", [
    # I - IV vamps and I - I7 - IV used to come out in the key of the IV (keys confirmed by ear)
    ("<chorus> Emaj7 E7 Amaj7 A Emaj7 E7 Amaj7 A <verse> Emaj7 E7 Amaj7 A Emaj7 E7 Amaj7 Amaj7", "E Major"),
    ("<intro> G Cmaj7 G <verse_1> Cmaj7 G Cmaj7 G Cmaj7 G Cmaj7", "G Major"),
    ("Am Dm E7 Am", "A Minor"),
])
def test_detect_key_from_chords(chords, key):
    from src.web.harmony import clean_and_extract_chords, detect_key_from_chords
    assert detect_key_from_chords(clean_and_extract_chords(chords)) == key


def test_bulk_reskill_writes_only_changes(client):
    d = client.post("/api/bulk-reskill").get_json()
    assert d["success"] and d["updated"] == 1 and d["skipped"] == 1
    assert {w["range"] for w in client.ws.written} == {"N2", "S2"}


def test_generate_improvisation_validates_and_needs_key(client, monkeypatch):
    assert client.post("/api/generate-improvisation", json={}).status_code == 400
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = client.post("/api/generate-improvisation", json={"tonality": "C Major", "progression": "I - V"})
    assert r.status_code == 500 and "GEMINI_API_KEY" in r.get_json()["error"]


def test_sheet_status_idle(client):
    assert client.get("/api/sheet-status").get_json()["busy"] is False


def test_update_voicings_creates_missing_column_and_writes_json(client):
    r = client.post("/api/update", json={"row": 3, "artist": "Artist2", "title": "Song2", "lookupVideoId": "v2",
                                         "voicings": {"F#": "2,-1,4,3,2,2"}})
    assert r.status_code == 200
    col = chr(65 + len(HEADER))  # first column after the current header
    assert client.ws.written == [
        {"range": f"{col}1", "values": [["Voicings"]]},
        {"range": f"{col}3", "values": [['{"F#": "2,-1,4,3,2,2"}']]},
    ]


def test_update_empty_voicings_clears_cell(client):
    client.post("/api/update", json={"row": 3, "artist": "Artist2", "title": "Song2", "lookupVideoId": "v2",
                                     "voicings": {}})
    assert client.ws.written[-1]["values"] == [[""]]


def test_songs_expose_per_song_voicings(client):
    client.ws.values[0] = HEADER + ["Voicings"]
    client.ws.values[1] = client.ws.values[1] + ['{"F#": "2,-1,4,3,2,2"}']
    songs = client.get("/api/songs").get_json()
    assert songs[0]["voicings"] == {"F#": "2,-1,4,3,2,2"} and songs[1]["voicings"] == {}


def test_estimate_key_returns_candidates_without_touching_the_sheet(client, monkeypatch):
    fake = {"tonality": "C# Major", "score": 0.88, "candidates": [{"tonality": "C# Major", "score": 0.88}]}
    monkeypatch.setattr(server, "estimate_key", lambda artist, title, chord_text=None: fake)
    r = client.get("/api/estimate-key?artist=Artist1&title=Song1")
    assert r.status_code == 200 and r.get_json()["tonality"] == "C# Major"
    assert client.ws.written == []


def test_estimate_key_reports_missing_preview_and_missing_params(client, monkeypatch):
    monkeypatch.setattr(server, "estimate_key", lambda artist, title, chord_text=None: None)
    assert client.get("/api/estimate-key?artist=A&title=T").status_code == 404
    assert client.get("/api/estimate-key?artist=A").status_code == 400


def test_detect_key_keeps_iv_v_ii_cadence_in_major():
    # Vansire - Every Time Around: Amaj7 B G#m7 F#m7 is IV7 - V - iii - ii in E major (confirmed by ear)
    from src.web.harmony import clean_and_extract_chords, detect_key_from_chords
    assert detect_key_from_chords(clean_and_extract_chords("Amaj7 B G#m7 F#m7 Amaj7 B G#m7 F#m7")) == "E Major"
