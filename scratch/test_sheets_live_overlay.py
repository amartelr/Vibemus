"""A rewrite must not roll back what the companion app saved while the sync was busy."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.sheets_service import SheetsService

HEADER = ["Playlist", "Artist", "Title", "Album", "Liked", "Year", "Genre", "Scrobble",
          "LastfmScrobble", "Video ID", "Chord", "Tonality", "Progression", "Complex",
          "Style", "LastScanned", "Lyrics"]


class FakeWs:
    def __init__(self, title, rows):
        self.title, self._rows = title, rows

    def get_all_values(self, **_):
        return [HEADER] + self._rows


def make_service(live_songs, live_archived=()):
    svc = object.__new__(SheetsService)  # skip Google authentication
    svc._external_cache = {}
    svc._live_external = None
    svc._live_external_at = 0.0
    sheets = {"Songs": FakeWs("Songs", live_songs), "Archived": FakeWs("Archived", list(live_archived))}
    svc._get_worksheet = lambda t: sheets[t]
    svc._execute_with_retry = lambda fn, *a, **k: fn(*a, **k)
    svc._external_values = lambda: svc._external_cache
    return svc


def row(vid, title="Salt", liked="FALSE", chord="", scanned="", lyrics=""):
    r = [""] * len(HEADER)
    r[0], r[1], r[2], r[4], r[9] = "#", "Artist", title, liked, vid
    r[10], r[15], r[16] = chord, scanned, lyrics
    return r


def stale(vid, **kw):
    return dict(zip(HEADER, row(vid, **kw)))


def test_live_values_beat_the_stale_copy():
    svc = make_service([row("v1", liked="TRUE", chord="<verse> C G", scanned="2026-10-15T18:40:00Z", lyrics="[{}]")])
    out = svc._build_song_rows([stale("v1", title="Salt (new title)")], HEADER, use_live=True)[0]
    cols = dict(zip(HEADER, out))
    assert cols["Chord"] == "<verse> C G"
    assert cols["LastScanned"] == "2026-10-15T18:40:00Z"
    assert cols["Lyrics"] == "[{}]"
    assert cols["Liked"] == "TRUE"
    assert cols["Title"] == "Salt (new title)"  # Vibemus keeps owning its own columns


def test_without_live_the_stale_copy_wins_as_before():
    svc = make_service([row("v1", scanned="2026-10-15T18:40:00Z")])
    cols = dict(zip(HEADER, svc._build_song_rows([stale("v1")], HEADER)[0]))
    assert cols["LastScanned"] == ""


def test_values_filled_by_this_run_survive_when_the_sheet_has_none():
    svc = make_service([row("v1")])
    cols = dict(zip(HEADER, svc._build_song_rows([stale("v1", chord="<verse> Am F")], HEADER, use_live=True)[0]))
    assert cols["Chord"] == "<verse> Am F"


def test_song_moved_to_archived_keeps_its_data():
    svc = make_service([], live_archived=[row("v1", chord="<verse> D A", scanned="2026-10-15T19:00:00Z")])
    cols = dict(zip(HEADER, svc._build_song_rows([stale("v1")], HEADER, use_live=True)[0]))
    assert cols["Chord"] == "<verse> D A" and cols["LastScanned"] == "2026-10-15T19:00:00Z"


def test_unreadable_sheet_falls_back_without_crashing():
    svc = make_service([row("v1", scanned="x")])
    svc._get_worksheet = lambda t: (_ for _ in ()).throw(RuntimeError("quota"))
    cols = dict(zip(HEADER, svc._build_song_rows([stale("v1", chord="C")], HEADER, use_live=True)[0]))
    assert cols["Chord"] == "C"


def test_replace_rows_writes_only_changed_cells():
    svc = object.__new__(SheetsService)
    svc._execute_with_retry = lambda fn, *a, **k: fn(*a, **k)
    calls = []

    class Ws:
        title, row_count, col_count = "Songs", 10, 20
        def get_all_values(self):
            return [["Artist", "Title", "Liked"], ["A", "T", "TRUE"], ["B", "U", "FALSE"], ["Old", "Row", ""]]
        def batch_update(self, data): calls.append(("update", data))
        def batch_clear(self, ranges): calls.append(("clear", ranges))

    svc._replace_rows(Ws(), [["Artist", "Title", "Liked"], ["A", "T", True], ["B", "V", False]])
    assert calls == [("update", [{"range": "B3:B3", "values": [["V"]]}]), ("clear", ["4:4"])]
