"""SongSheet writes only the cells asked for, addressed by Video ID / artist+title."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.sheet_gateway import SongSheet, SongNotFound, col_idx_to_letter

HEADER = ["Playlist", "Artist", "Title", "Album", "Liked", "Year", "Genre", "Scrobble",
          "LastfmScrobble", "Video ID", "Chord", "Tonality", "bpm"]


class FakeWs:
    def __init__(self, rows):
        self.values = [HEADER] + rows
        self.batches = []

    def get_all_values(self):
        return self.values

    def batch_update(self, data, value_input_option=None):
        self.batches.append((data, value_input_option))


def row(vid, artist="A", title="T"):
    r = [""] * len(HEADER)
    r[1], r[2], r[9] = artist, title, vid
    return r


def make(rows):
    ws = FakeWs(rows)
    sheet = SongSheet()
    sheet._ws = ws
    return sheet, ws


def test_letters():
    assert [col_idx_to_letter(i) for i in (0, 25, 26, 27)] == ["A", "Z", "AA", "AB"]


def test_moved_row_found_by_video_id():
    sheet, ws = make([row("v1", "X", "Y"), row("v2")])
    assert sheet.update_song({"bpm": 90}, video_id="v2", row_hint=2) == 3
    assert ws.batches == [([{"range": "M3", "values": [[90]]}], "RAW")]


def test_row_hint_trusted_only_if_it_still_matches():
    sheet, ws = make([row("v1", "X", "Y"), row("v2", "A", "T")])
    assert sheet.update_song({"chord": "Am"}, artist="a", title="t", row_hint=2) == 3
    assert ws.batches[0][0] == [{"range": "K3", "values": [["Am"]]}]


def test_duplicate_artist_title_prefers_hint():
    sheet, _ = make([row("v1"), row("v2")])
    assert sheet.update_song({"chord": "C"}, artist="A", title="T", row_hint=3) == 3


def test_missing_song_writes_nothing():
    sheet, ws = make([row("v1")])
    with pytest.raises(SongNotFound):
        sheet.update_song({"chord": "C"}, artist="Nope", title="Nope", row_hint=2)
    assert ws.batches == []


def test_unknown_column_skipped():
    sheet, ws = make([row("v1")])
    _, _, col_map = sheet.read()
    assert sheet.write_cells([(2, "improvisation", "x")], col_map) == 0
    assert ws.batches == []


def test_stale_video_id_falls_back_to_name():
    sheet, _ = make([row("v1", "X", "Y"), row("v2", "A", "T")])
    assert sheet.update_song({"chord": "C"}, video_id="old", artist="A", title="T", row_hint=2) == 3
