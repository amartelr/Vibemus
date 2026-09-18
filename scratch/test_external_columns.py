"""Checks that no write path can drop or blank the companion app's columns.

Runs fully offline against a fake worksheet: python scratch/test_external_columns.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.sheets_service import SheetsService, SONG_HEADER

EXTERNAL = ["Chord", "Tonality", "Progression", "Complex", "Style", "LastScanned", "Lyrics"]


class FakeWorksheet:
    def __init__(self, title, values):
        self.title = title
        self.values = [list(r) for r in values]
        self.row_count = max(1000, len(self.values))
        self.col_count = 17
        self.reads = 0

    def row_values(self, idx):
        return list(self.values[idx - 1]) if len(self.values) >= idx else []

    def get_all_values(self, value_render_option=None):
        self.reads += 1
        return [list(r) for r in self.values]

    def clear(self):
        self.values = []

    def update(self, range_name=None, values=None):
        # Mimics values.update at A1: overwrites in place, leaves any tail
        rows = [list(r) for r in values]
        self.values[:len(rows)] = rows

    def batch_clear(self, ranges):
        for rng in ranges:
            start = int(rng.split(":")[0])
            del self.values[start - 1:]

    def append_row(self, row):
        self.values.append(list(row))

    def append_rows(self, rows):
        self.values.extend(list(r) for r in rows)

    def add_cols(self, n):
        self.col_count += n

    def records(self):
        header = [h.strip() for h in self.values[0]]
        return [
            {h: (row[i] if i < len(row) else '') for i, h in enumerate(header)}
            for row in self.values[1:]
        ]


def make_service(sheets):
    svc = SheetsService.__new__(SheetsService)
    svc._artists_cache = None
    svc._songs_vid_cache = None
    svc._active_records_cache = None
    svc._archived_records_cache = None
    svc._external_cache = None
    svc._sheets = sheets
    svc._get_worksheet = lambda title: sheets[title]
    return svc


def song_row(header, **vals):
    return [str(vals.get(h, '')) for h in header]


def new_sheets(songs_header=None, extra_song_rows=None):
    header = songs_header or list(SONG_HEADER)
    rows = [header]
    rows.append(song_row(header, **{
        'Playlist': 'Rock', 'Artist': 'Muse', 'Title': 'Hysteria', 'Video ID': 'vid1',
        'Chord': 'C G Am F', 'Tonality': 'C major', 'Progression': 'I V vi IV',
        'Complex': 'Low', 'Style': 'Pop', 'LastScanned': '2026-09-01', 'Lyrics': 'la la la',
    }))
    rows.extend(extra_song_rows or [])
    archived = [list(SONG_HEADER), song_row(SONG_HEADER, **{
        'Playlist': 'Archived', 'Artist': 'Oasis', 'Title': 'Live Forever', 'Video ID': 'vid9',
        'Chord': 'G D Em', 'Lyrics': 'maybe', 'LastScanned': '2026-08-02',
    })]
    return {"Songs": FakeWorksheet("Songs", rows), "Archived": FakeWorksheet("Archived", archived)}


failures = []


def check(name, cond, detail=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        failures.append(name)


print("\n1. overwrite_songs with a bare dict (the old data-loss path)")
sheets = new_sheets()
svc = make_service(sheets)
svc.overwrite_songs([{'Playlist': 'Rock', 'Artist': 'Muse', 'Title': 'Hysteria', 'Video ID': 'vid1'}])
rec = sheets["Songs"].records()[0]
for col in EXTERNAL:
    check(f"{col} preserved", str(rec.get(col, '')).strip() != '', f"got {rec.get(col)!r}")

print("\n2. Unknown column added by the other app is not dropped")
custom = list(SONG_HEADER) + ["Mood"]
sheets = new_sheets(songs_header=custom)
sheets["Songs"].values[1][custom.index("Mood")] = "happy"
svc = make_service(sheets)
svc.overwrite_songs([{'Playlist': 'Rock', 'Video ID': 'vid1', 'Title': 'Hysteria'}])
check("Mood column still in header", "Mood" in sheets["Songs"].values[0])
check("Mood value kept", sheets["Songs"].records()[0].get("Mood") == "happy", str(sheets["Songs"].records()[0]))

print("\n3. Reordered header: values land in the right columns")
reordered = ["Lyrics", "Video ID", "Playlist", "Chord", "Artist", "Title", "Album", "Liked",
             "Year", "Genre", "Scrobble", "LastfmScrobble", "Tonality", "Progression", "Complex",
             "Style", "LastScanned"]
sheets = new_sheets(songs_header=reordered)
svc = make_service(sheets)
svc.overwrite_songs([{'Playlist': 'Rock', 'Video ID': 'vid1', 'Title': 'Hysteria'}])
check("header order untouched", sheets["Songs"].values[0] == reordered)
rec = sheets["Songs"].records()[0]
check("Lyrics still in its own column", rec.get("Lyrics") == "la la la", str(rec))
check("Chord still in its own column", rec.get("Chord") == "C G Am F", str(rec))

print("\n4. Vibemus may still fill an empty external column, and update a filled one")
sheets = new_sheets()
svc = make_service(sheets)
svc.overwrite_songs([{'Video ID': 'vid1', 'Title': 'Hysteria', 'Chord': 'NEW CHORDS'}])
check("new non-empty Chord wins", sheets["Songs"].records()[0].get("Chord") == "NEW CHORDS")
check("Lyrics untouched", sheets["Songs"].records()[0].get("Lyrics") == "la la la")

print("\n5. Archiving a song carries its external columns across")
sheets = new_sheets()
svc = make_service(sheets)
svc.add_to_archived_batch([{'Playlist': 'Rock', 'Artist': 'Muse', 'Title': 'Hysteria', 'Video ID': 'vid1'}])
arch = [r for r in sheets["Archived"].records() if r.get("Video ID") == "vid1"][0]
check("Chord carried to Archived", arch.get("Chord") == "C G Am F", str(arch))
check("Lyrics carried to Archived", arch.get("Lyrics") == "la la la")

print("\n6. overwrite_archived keeps existing external data")
sheets = new_sheets()
svc = make_service(sheets)
svc.overwrite_archived([{'Playlist': 'Archived', 'Artist': 'Oasis', 'Title': 'Live Forever', 'Video ID': 'vid9'}])
arch = sheets["Archived"].records()[0]
check("Chord preserved", arch.get("Chord") == "G D Em", str(arch))
check("LastScanned preserved", arch.get("LastScanned") == "2026-08-02")

print("\n7. An empty overwrite is refused instead of wiping the sheet")
sheets = new_sheets()
svc = make_service(sheets)
svc.overwrite_songs([])
check("Songs sheet untouched", len(sheets["Songs"].records()) == 1)
svc2 = make_service(new_sheets())
svc2.overwrite_archived([])
check("Archived sheet untouched", len(svc2._sheets["Archived"].records()) == 1)

print("\n8. Values produced this run survive a later write")
sheets = new_sheets()
svc = make_service(sheets)
svc.add_to_songs_batch([{'Video ID': 'vid2', 'Title': 'New Born', 'Chord': 'Em G D'}])
svc.overwrite_songs([{'Video ID': 'vid1', 'Title': 'Hysteria'}, {'Video ID': 'vid2', 'Title': 'New Born'}])
rec2 = [r for r in sheets["Songs"].records() if r.get("Video ID") == "vid2"][0]
check("Chord from this run kept", rec2.get("Chord") == "Em G D", str(rec2))

print("\n9. Empty sheet still gets the full header")
empty = {"Songs": FakeWorksheet("Songs", []), "Archived": FakeWorksheet("Archived", [])}
svc = make_service(empty)
svc.overwrite_songs([{'Video ID': 'vid3', 'Title': 'Uprising'}])
check("default header written", empty["Songs"].values[0] == list(SONG_HEADER), str(empty["Songs"].values[0]))

print("\n10. Legacy 15-column sheet gets LastScanned/Lyrics appended")
legacy = list(SONG_HEADER[:15])
sheets = new_sheets(songs_header=legacy)
svc = make_service(sheets)
svc.overwrite_songs([{'Video ID': 'vid1', 'Title': 'Hysteria'}])
check("header extended", sheets["Songs"].values[0] == list(SONG_HEADER), str(sheets["Songs"].values[0]))
check("grid widened", sheets["Songs"].col_count >= 17)

print("\n11. Repeated overwrites keep data and don't re-read the sheet")
sheets = new_sheets()
svc = make_service(sheets)
svc.overwrite_songs([{'Video ID': 'vid1', 'Title': 'Hysteria'}])
reads_after_first = sheets["Songs"].reads
svc.overwrite_songs([{'Video ID': 'vid1', 'Title': 'Hysteria'}])
check("no extra Songs read", sheets["Songs"].reads == reads_after_first, f"{sheets['Songs'].reads} vs {reads_after_first}")
rec = sheets["Songs"].records()[0]
check("Lyrics survive the second write", rec.get("Lyrics") == "la la la", str(rec))
cached = [r for r in svc.get_songs_records() if r.get("Video ID") == "vid1"][0]
check("cache reflects merged data", cached.get("Chord") == "C G Am F", str(cached))
check("vid cache rebuilt", svc.get_all_video_ids() == {"vid1"}, str(svc.get_all_video_ids()))

print("\n12. Shrinking the sheet truncates the leftover rows")
header = list(SONG_HEADER)
extra = [
    song_row(header, Playlist='Rock', Title='Plug In Baby', **{'Video ID': 'vidA', 'Lyrics': 'a'}),
    song_row(header, Playlist='Rock', Title='Bliss', **{'Video ID': 'vidB', 'Lyrics': 'b'}),
]
sheets = new_sheets(extra_song_rows=extra)
svc = make_service(sheets)
check("starts with 3 songs", len(sheets["Songs"].records()) == 3)
svc.overwrite_songs([{'Video ID': 'vid1', 'Title': 'Hysteria'}])
recs = sheets["Songs"].records()
check("leftover rows removed", len(recs) == 1, f"{len(recs)} rows left")
check("surviving row intact", recs[0].get("Lyrics") == "la la la", str(recs[0]))

print("\n" + ("❌ FAILURES: " + ", ".join(failures) if failures else "✅ All checks passed"))
sys.exit(1 if failures else 0)
