"""Single door to the shared spreadsheet for the web dashboard.

Authenticates with the service account (same as the CLI) and only writes the
cells that change, addressed by Video ID (falling back to artist/title, then
to the row hint) instead of a bare row number.
"""
import gspread

from ..config import Config
from .sheet_lock import write_lock

SPREADSHEET_ID = "1ht3ltF03Z1t7dZTyJN0IDgKRk_bKY-bszn9cPBbWdnI"


def col_idx_to_letter(idx):
    if idx < 0:
        return None
    letter = ""
    while idx >= 0:
        letter = chr(65 + (idx % 26)) + letter
        idx = (idx // 26) - 1
    return letter


def get_column_mapping(headers):
    """Fuzzy header -> column index map (-1 when missing)."""
    mapping = {}
    lower_headers = [str(h).strip().lower() for h in headers]

    def find_idx(*names):
        for n in names:
            nl = n.lower()
            if nl in lower_headers:
                return lower_headers.index(nl)
        return -1

    mapping["playlist"] = find_idx("playlist", "lista", "lista de reproducción", "lista de reproduccion")
    mapping["artist"] = find_idx("artist", "artista", "autor")
    mapping["title"] = find_idx("title", "canción", "cancion", "titulo", "título", "nombre")
    mapping["album"] = find_idx("album", "álbum")
    mapping["liked"] = find_idx("liked", "me gusta", "favorito", "favoritos")
    mapping["year"] = find_idx("year", "año", "ano")
    mapping["genre"] = find_idx("genre", "género", "genero")
    mapping["scrobble"] = find_idx("scrobble", "reproducciones")
    mapping["lastfmScrobble"] = find_idx("lastfmscrobble", "lastfm_scrobble", "lastfm scrobble")
    mapping["videoId"] = find_idx("videoid", "video_id", "video id", "video", "youtube")
    mapping["chord"] = find_idx("chord", "chords", "acorde", "acordes")
    mapping["tonality"] = find_idx("tonality", "tonalidad", "tono", "key")
    mapping["progression"] = find_idx("progression", "progresion", "progresión", "progresion numerica", "progresión numérica")
    mapping["complex"] = find_idx("complex", "complexity", "complejidad", "nivel")
    mapping["emotional"] = find_idx("emotional", "estilo emocional", "estilo_emocional")
    mapping["skill"] = find_idx("skill", "complejidad", "nivel", "skill")
    mapping["improvisation"] = find_idx("improvisation", "improvisación", "escala", "escalas", "guía")
    mapping["style"] = find_idx("style", "estilo", "estilos")
    mapping["lastScanDate"] = find_idx("last scanned", "lastscan", "lastscanned", "lastscandate", "last_scan_date", "último escaneo", "ultimo escaneo", "fecha", "fecha de escaneo")
    mapping["lyrics"] = find_idx("lyrics", "letra", "letras")
    mapping["bpm"] = find_idx("bpm", "tempo")
    mapping["voicings"] = find_idx("voicings", "posiciones", "posiciones de acordes")
    return mapping


# Dashboard columns the web may create itself when a sheet lacks them: key -> header written in row 1
CREATABLE_COLUMNS = {"voicings": "Voicings"}


def _norm(text):
    return str(text or "").strip().lower()


class SongNotFound(Exception):
    pass


class SongSheet:
    """Read/write access to one worksheet (default 'Songs')."""

    def __init__(self, sheet_name="Songs", spreadsheet=None):
        self.sheet_name = sheet_name
        self._spreadsheet = spreadsheet
        self._ws = None

    @property
    def ws(self):
        if self._ws is None:
            if self._spreadsheet is None:
                client = gspread.service_account(filename=Config.SERVICE_ACCOUNT_FILE)
                self._spreadsheet = client.open_by_key(SPREADSHEET_ID)
            self._ws = self._spreadsheet.worksheet(self.sheet_name)
        return self._ws

    def read(self):
        """(header, rows, col_map); rows[0] is sheet row 2."""
        values = self.ws.get_all_values()
        if not values:
            return [], [], get_column_mapping([])
        header = values[0]
        return header, values[1:], get_column_mapping(header)

    @staticmethod
    def _cell(row, idx):
        return row[idx] if idx != -1 and idx < len(row) else ""

    def locate(self, rows, col_map, video_id=None, artist=None, title=None, row_hint=None):
        """Sheet row number of a song: by Video ID, else artist+title, else None.

        row_hint is only trusted when the row at that position still matches.
        """
        def by_vid(r):
            return bool(video_id) and self._cell(r, col_map.get("videoId", -1)).strip() == video_id

        def by_name(r):
            return bool(artist and title) and (
                _norm(self._cell(r, col_map.get("artist", -1))) == _norm(artist)
                and _norm(self._cell(r, col_map.get("title", -1))) == _norm(title))

        if video_id:
            hinted = row_hint and 2 <= row_hint < len(rows) + 2 and by_vid(rows[row_hint - 2])
            if hinted:
                return row_hint
            for idx, r in enumerate(rows):
                if by_vid(r):
                    return idx + 2
        if row_hint and 2 <= row_hint < len(rows) + 2 and by_name(rows[row_hint - 2]):
            return row_hint
        for idx, r in enumerate(rows):
            if by_name(r):
                return idx + 2
        return None

    def write_cells(self, cells, col_map):
        """cells: iterable of (row, key, value). Skips unknown columns; one API call."""
        data = []
        for row, key, value in cells:
            letter = col_idx_to_letter(col_map.get(key, -1))
            if letter:
                data.append({"range": f"{letter}{row}", "values": [[value]]})
        with write_lock():
            for i in range(0, len(data), 500):
                self.ws.batch_update(data[i:i + 500], value_input_option="RAW")
        return len(data)

    def _ensure_columns(self, header, col_map, keys):
        """Appends the CREATABLE_COLUMNS in `keys` missing from row 1 and returns the refreshed col_map."""
        missing = [k for k in keys if k in CREATABLE_COLUMNS and col_map.get(k, -1) == -1]
        if not missing:
            return col_map
        new_header = list(header)
        while new_header and not str(new_header[-1]).strip():
            new_header.pop()  # trailing blanks are grid padding, not columns
        first_new = len(new_header)
        new_header += [CREATABLE_COLUMNS[k] for k in missing]
        cols = getattr(self.ws, "col_count", None)
        if cols is not None and len(new_header) > cols:
            self.ws.add_cols(len(new_header) - cols)
        self.ws.batch_update([{"range": f"{col_idx_to_letter(first_new + i)}1", "values": [[CREATABLE_COLUMNS[k]]]}
                              for i, k in enumerate(missing)], value_input_option="RAW")
        return get_column_mapping(new_header)

    def update_song(self, fields, video_id=None, artist=None, title=None, row_hint=None):
        """Write {key: value} for one song. Raises SongNotFound; returns the row written."""
        with write_lock():
            header, rows, col_map = self.read()
            col_map = self._ensure_columns(header, col_map, fields.keys())
            row = self.locate(rows, col_map, video_id, artist, title, row_hint)
            if row is None:
                raise SongNotFound(f"{artist} - {title}")
            self.write_cells([(row, k, v) for k, v in fields.items()], col_map)
            return row
