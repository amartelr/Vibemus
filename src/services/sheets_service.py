import gspread
import time
from datetime import datetime
from ..config import Config

# Columns Vibemus owns: it is free to rewrite them on every run.
MANAGED_SONG_COLUMNS = [
    "Playlist", "Artist", "Title", "Album", "Liked",
    "Year", "Genre", "Scrobble", "LastfmScrobble", "Video ID"
]

# Columns fed by the companion app that shares this spreadsheet. Vibemus may
# fill one in while it is empty (chord enrichment / harmonic analysis), but it
# must never blank one out nor drop the column from the sheet.
EXTERNAL_SONG_COLUMNS = [
    "Chord", "Tonality", "Progression", "Complex", "Style", "LastScanned", "Lyrics"
]

SONG_HEADER = MANAGED_SONG_COLUMNS + EXTERNAL_SONG_COLUMNS


class SheetsService:
    def __init__(self):
        # Authenticate using newer gspread.service_account approach (uses google-auth)
        # It handles scopes automatically: spreadsheets and drive
        self.client = gspread.service_account(filename=Config.SERVICE_ACCOUNT_FILE)
        self.spreadsheet = self._get_or_create_spreadsheet()
        
        # Cache for current run
        self._artists_cache = None
        self._songs_vid_cache = None
        self._active_records_cache = None
        self._archived_records_cache = None
        # Video ID -> values of the columns Vibemus does not own. Survives the
        # record caches being invalidated, so no write can drop them.
        self._external_cache = None

    def _get_or_create_spreadsheet(self):
        def _open():
            try:
                return self.client.open(Config.SPREADSHEET_TITLE)
            except gspread.SpreadsheetNotFound:
                return self.client.create(Config.SPREADSHEET_TITLE)
        
        return self._execute_with_retry(_open)

    def _execute_with_retry(self, func, *args, **kwargs):
        """Helper to execute gspread calls with exponential backoff on transient API errors."""
        retries = 5
        delay = 2
        while retries > 0:
            try:
                return func(*args, **kwargs)
            except gspread.exceptions.APIError as e:
                code = getattr(e.response, 'status_code', None)
                # 429: Too Many Requests, 500/502/503: Server errors
                if code in [429, 500, 502, 503] and retries > 1:
                    wait = delay
                    if code == 429:
                        wait = 30 # Quota hits usually need more time
                        print(f"  \033[93m⚠ Quota exceeded (429), waiting {wait}s to resume...\033[0m")
                    else:
                        print(f"  \033[93m⚠ Sheet API {code} error, retrying in {wait}s... ({retries-1} left)\033[0m")
                    
                    time.sleep(wait)
                    retries -= 1
                    if code != 429:
                        delay *= 2
                else:
                    raise
            except Exception:
                raise

    def _to_int(self, val):
        """Safely convert a value (potentially with regional formatting) to an integer."""
        if not val:
            return 0
        try:
            # Handle cases like '4.243,00' or '4,243.00'
            s = str(val).strip()
            # Remove thousands separators - this is tricky because dot/comma roles swap
            # If there's both a comma and a dot, the last one is the decimal
            if ',' in s and '.' in s:
                if s.rfind(',') > s.rfind('.'): # Comma is decimal
                    s = s.replace('.', '').replace(',', '.')
                else: # Dot is decimal
                    s = s.replace(',', '')
            elif ',' in s: # Only comma - could be decimal (European) or thousand (US)
                # If there are exactly 2 digits after, likely decimal. 
                # But safer to just check if it's used as a decimal in this context.
                # User mentioned 4.243,00.
                if len(s.split(',')[-1]) <= 2:
                    s = s.replace('.', '').replace(',', '.')
                else:
                    s = s.replace(',', '')
            
            return int(float(s))
        except:
            return 0

    def _get_worksheet(self, title):
        def _fetch():
            try:
                return self.spreadsheet.worksheet(title)
            except gspread.WorksheetNotFound:
                ws = self.spreadsheet.add_worksheet(title=title, rows=1000, cols=max(20, len(SONG_HEADER)))
                if title == "Artists":
                    ws.append_row(["Artist Name", "Artist ID", "Song Count", "Last Checked", "Status", "Genre", "Playlist", "Multiple"])
                elif title == "Genre":
                    ws.append_row(["Genre", "Count"])
                elif title in ["Songs", "Archived"]:
                    ws.append_row(list(SONG_HEADER))
                else:
                    # Default header for playlist exports
                    ws.append_row(["Playlist", "Artist", "Album", "Title", "Views"])
                return ws

        return self._execute_with_retry(_fetch)

    def _song_header(self, ws):
        """Returns the header to write, based on the sheet's CURRENT one.

        Never drops a column: whatever the companion app put in row 1 is kept in
        place, and only genuinely missing Vibemus columns are appended.
        """
        try:
            header = list(self._execute_with_retry(ws.row_values, 1) or [])
        except Exception as e:
            print(f"  \033[93m⚠ Could not read '{ws.title}' header ({e}); falling back to the default one.\033[0m")
            header = []

        # Trailing blanks are grid padding, not columns
        while header and not str(header[-1]).strip():
            header.pop()

        if not header:
            return list(SONG_HEADER)

        known = {str(h).strip() for h in header}
        header.extend(col for col in SONG_HEADER if col not in known)

        self._ensure_columns(ws, len(header))
        return header

    def _ensure_columns(self, ws, needed):
        """Grows the grid if the header no longer fits (never shrinks it)."""
        try:
            if needed > ws.col_count:
                self._execute_with_retry(ws.add_cols, needed - ws.col_count)
        except Exception as e:
            print(f"  \033[93m⚠ Could not widen '{ws.title}' to {needed} columns: {e}\033[0m")

    def _external_values(self):
        """Video ID -> values of every column Vibemus does not own.

        Read once per run from Songs *and* Archived: songs move between the two
        sheets, so archiving a track must not lose the analysis the companion
        app wrote while it was still active. Always built before the first
        destructive write, since the getters below read the live sheet.
        """
        if self._external_cache is not None:
            return self._external_cache

        self._external_cache = {}
        for label, getter in (("Songs", self.get_songs_records), ("Archived", self.get_archived_records)):
            try:
                records = getter()
            except Exception as e:
                print(f"  \033[93m⚠ Could not read '{label}' to preserve external columns: {e}\033[0m")
                continue
            for record in records:
                self._remember_external(record)

        return self._external_cache

    def _remember_external(self, record):
        """Stores the non-empty external values of a record for later writes."""
        vid = str(record.get('Video ID', '') or '').strip()
        if not vid:
            return
        entry = self._external_cache.setdefault(vid, {})
        for key, value in record.items():
            name = str(key).strip()
            if not name or name in MANAGED_SONG_COLUMNS:
                continue
            if str(value or '').strip():
                entry[name] = value

    def _build_song_rows(self, songs, header, year_as_str=True):
        """Turns song dicts into rows aligned to `header`.

        Any external column the caller left empty is refilled from what the
        sheet already held, so callers that build partial dicts can no longer
        wipe the companion app's data.
        """
        external = self._external_values()
        rows = []
        for song in songs:
            merged = dict(song)
            vid = str(merged.get('Video ID', '') or '').strip()
            for key, value in (external.get(vid) or {}).items():
                if not str(merged.get(key, '') or '').strip():
                    merged[key] = value
            # Values produced during this run (chord enrichment, analysis) must
            # survive the writes that come after it.
            self._remember_external(merged)

            row = []
            for col in header:
                name = str(col).strip()
                if name in ('Scrobble', 'LastfmScrobble'):
                    row.append(self._to_int(merged.get(name)))
                elif name == 'Year':
                    year = merged.get('Year', '')
                    row.append(str(year) if year_as_str else year)
                else:
                    value = merged.get(name, '')
                    row.append('' if value is None else value)
            rows.append(row)
        return rows

    def _replace_rows(self, ws, rows):
        """Replaces a sheet's contents with `rows` (header included).

        Writes first and only then clears the leftover tail, so a call that
        fails midway leaves stale rows behind rather than an empty sheet —
        the old clear()-then-write order could wipe everything.
        """
        if not rows:
            return
        self._execute_with_retry(ws.update, range_name='A1', values=rows)
        leftover = len(rows) + 1
        try:
            if ws.row_count >= leftover:
                self._execute_with_retry(ws.batch_clear, [f"{leftover}:{ws.row_count}"])
        except Exception as e:
            print(f"  \033[93m⚠ Could not clear leftover rows in '{ws.title}': {e}\033[0m")

    def _refuses_empty_overwrite(self, songs, existing, label):
        """Guards against replacing a populated sheet with nothing."""
        if not songs and existing:
            print(f"  \033[91m🛑 ERROR: Attempted to overwrite '{label}' ({len(existing)} rows) with an empty list. Aborting to save data.\033[0m")
            return True
        return False

    def export_playlist_to_sheet(self, songs, sheet_name="Songs"):
        """
        Exports a list of songs to a specific sheet.
        Removes existing entries for the given playlist before adding new ones.
        songs: list of dicts with keys: Playlist, Video ID, Artist, Album, Title, Duration, Views
        sheet_name: Title of the sheet to export to.
        """
        # Ensure sheet exists
        ws = self._get_worksheet(sheet_name)
        
        # Get all existing values
        existing_rows = ws.get_all_values()
        
        # Determine the playlist name we are exporting (assume all songs have same playlist name)
        current_playlist_name = ""
        if songs:
            current_playlist_name = songs[0].get("Playlist", "")
            
        print(f"Exporting {len(songs)} songs to '{sheet_name}' (Playlist: {current_playlist_name})...")

        # Filter out existing rows for this playlist
        # Header is usually row 0
        header = self._song_header(ws)
        new_rows = [header]
        if existing_rows:
            # Remember what this sheet already held, so re-exported songs keep
            # the columns the companion app owns even when `songs` omits them.
            self._external_values()
            old_header = [str(h).strip() for h in existing_rows[0]]
            for row in existing_rows[1:]:
                self._remember_external({h: (row[i] if i < len(row) else '') for i, h in enumerate(old_header)})

            # Find the index of 'Playlist' column just in case, usually 0
            try:
                playlist_col_idx = old_header.index("Playlist")
            except ValueError:
                playlist_col_idx = 0

            # Keep rows that belong to OTHER playlists, realigned to the header
            for row in existing_rows[1:]:
                record = {h: (row[i] if i < len(row) else '') for i, h in enumerate(old_header)}
                if len(row) > playlist_col_idx and row[playlist_col_idx] == current_playlist_name:
                    continue
                new_rows.append([record.get(str(h).strip(), '') for h in header])

        # Add new songs
        new_rows.extend(self._build_song_rows(songs, header, year_as_str=False))

        print(f"Updating sheet... (Total rows: {len(new_rows)})")
        self._replace_rows(ws, new_rows)
        
        # Move sheet to be after 'History' if possible
        
        # Move sheet to be after 'History' if possible
        try:
            # Find index of History
            worksheets = self.spreadsheet.worksheets()
            history_idx = -1
            for i, w in enumerate(worksheets):
                if w.title == "History":
                    history_idx = i
                    break
            
            if history_idx != -1:
                # Update index?
                pass 
        except:
            pass


    def get_artists(self):
        """Returns list of artists dicts."""
        if self._artists_cache:
            return self._artists_cache
            
        ws = self._get_worksheet("Artists")
        self._artists_cache = self._execute_with_retry(ws.get_all_records)
        return self._artists_cache

    def save_artists(self, artists_data):
        """
        Overwrite artists sheet.
        artists_data: list of dicts with keys matching headers.
        """
        ws = self._get_worksheet("Artists")
        # Header
        headers = ["Artist Name", "Artist ID", "Song Count", "Last Checked", "Status", "Genre", "Playlist", "Multiple"]
        
        # Safety check: if artists_data is empty but we HAD artists before, abort to prevent wiping.
        if not artists_data and self._artists_cache:
            print("  \033[91m🛑 ERROR: Attempted to save an empty artist list. Aborting to save data.\033[0m")
            return

        # Prepare rows
        rows = [headers]
        for artist in artists_data:
            mult_val = artist.get("Multiple", "")
            if mult_val is True:
                mult_val = "TRUE"
            elif mult_val is False:
                mult_val = "FALSE"
            rows.append([
                artist.get("Artist Name", ""),
                artist.get("Artist ID", ""),
                artist.get("Song Count", 0),
                artist.get("Last Checked", ""),
                artist.get("Status", ""),
                artist.get("Genre", ""),
                artist.get("Playlist", ""),
                mult_val
            ])
        
        # Overwrite content at A1 (without separate ws.clear call to save network latency)
        self._execute_with_retry(ws.update, range_name='A1', values=rows)
        self._artists_cache = artists_data

    def update_artist_fields(self, artist_name, fields: dict):
        """Updates multiple fields of a specific artist in memory and saves to Sheets in a single call."""
        artists = self.get_artists()
        updated = False
        norm_target = str(artist_name).lower().strip()
        for a in artists:
            if str(a.get("Artist Name", "")).lower().strip() == norm_target:
                for k, v in fields.items():
                    a[k] = v
                updated = True
                break
        if updated:
            self.save_artists(artists)

    def add_artist(self, artist_row, silent=False):
        """Appends a single artist row to the Artists sheet if not already present."""
        artists = self.get_artists()
        
        # Guard against duplications in memory
        aid = str(artist_row.get("Artist ID", "")).strip()
        name = str(artist_row.get("Artist Name", "")).strip()
        norm_name = name.lower()
        
        exists = False
        for a in artists:
            # Check ID match
            if aid and str(a.get("Artist ID", "")).strip() == aid:
                exists = True
                break
            # Check exact Name match (fallback)
            if str(a.get("Artist Name", "")).lower().strip() == norm_name:
                exists = True
                break
                
        if not exists:
            artists.append(artist_row)
            self.save_artists(artists)
            if not silent:
                print(f"      🆕 Artist '{name}' added to tracking list.")
        else:
            # If it already exists, just save artists to ensure sheet is in sync with memory
            # (In case memory had the duplicate but sheet didn't, or vice-versa)
            self.save_artists(artists)

    def update_artist_status(self, artist_name, status):
        """Updates the status of a specific artist."""
        self.update_artist_fields(artist_name, {"Status": status})

    def update_artist_last_checked(self, artist_name, date_str):
        """Updates the last checked date of a specific artist."""
        self.update_artist_fields(artist_name, {"Last Checked": date_str})

    def update_artist_playlist(self, artist_name, playlist_name, artist_id=None, genre=None, song_count=0, silent=False):
        """Updates the target playlist of a specific artist. Adds it if missing."""
        artists = self.get_artists()
        updated = False
        # Normalize for comparison
        norm_name = str(artist_name).lower().strip()
        for a in artists:
            # Match by ID first if provided, then by Name
            if (artist_id and str(a.get("Artist ID", "")).strip() == str(artist_id).strip()) or \
               (str(a.get("Artist Name", "")).lower().strip() == norm_name):
                a["Playlist"] = playlist_name
                # Only update if provided
                if artist_id: a["Artist ID"] = artist_id
                if genre: a["Genre"] = genre
                if song_count: a["Song Count"] = song_count
                updated = True
                break
        
        if updated:
            self.save_artists(artists)
        else:
            # Case B: Artist is totally new, add a new row
            status = "Pending"
            new_artist = {
                "Artist Name": artist_name,
                "Artist ID": artist_id or "",
                "Playlist": playlist_name,
                "Status": status, # Status for artists awaiting their first scan
                "Song Count": song_count or 0,
                "Last Checked": datetime.now().strftime("%d/%m/%Y") if not artist_id else "", # empty to trigger sync if not yet performed
                "Genre": genre or "",
                "Multiple": ""
            }

            self.add_artist(new_artist, silent=silent or (status == "Archived"))



    def get_all_video_ids(self):
        """Returns the set of all Video IDs present in the Songs sheet.

        Replaces the old get_history() — Songs is now the single source
        of truth for deduplication.
        """
        if self._songs_vid_cache is not None:
            return self._songs_vid_cache

        records = self.get_songs_records()
        self._songs_vid_cache = {r.get('Video ID') for r in records if r.get('Video ID')}
        return self._songs_vid_cache

    def get_songs_records(self):
        """Returns all records from the Songs sheet as a list of dictionaries."""
        if self._active_records_cache is not None:
            return self._active_records_cache
            
        ws = self._get_worksheet("Songs")
        # Use UNFORMATTED_VALUE to get raw numbers instead of locale-formatted strings
        data = self._execute_with_retry(ws.get_all_values, value_render_option='UNFORMATTED_VALUE')
        if not data:
            self._active_records_cache = []
            return []

        self._active_records_cache = self._rows_to_records(data[0], data[1:])
        return self._active_records_cache

    def _rows_to_records(self, header, rows):
        """Zips sheet rows against their header into dicts."""
        names = [str(h).strip() for h in header]
        return [
            {h: (row[i] if i < len(row) else '') for i, h in enumerate(names) if h}
            for row in rows
        ]

    def overwrite_songs(self, records):
        """Rewrites the entire Songs sheet using an atomic update for performance and reliability."""
        ws = self._get_worksheet("Songs")
        header = self._song_header(ws)
        # Read (and cache) the live contents BEFORE clearing anything
        if self._refuses_empty_overwrite(records, self.get_songs_records(), "Songs"):
            return
        rows = [header] + self._build_song_rows(records, header)

        self._active_records_cache = None
        self._songs_vid_cache = None
        try:
            self._replace_rows(ws, rows)
            # Mirror what we just wrote instead of forcing a re-read: Songs now
            # carries Lyrics, so re-fetching it on every write burns API quota.
            self._active_records_cache = self._rows_to_records(header, rows[1:])
            self._songs_vid_cache = {r['Video ID'] for r in self._active_records_cache if r.get('Video ID')}
        except Exception as e:
            print(f"Error overwriting Songs: {e}")

    def add_to_songs_batch(self, songs_data):
        """Adds a list of songs to the Songs sheet."""
        if not songs_data:
            return
        ws = self._get_worksheet("Songs")
        header = self._song_header(ws)
        new_rows = self._build_song_rows(songs_data, header, year_as_str=False)

        self._active_records_cache = None
        self._songs_vid_cache = None
        if new_rows:
            self._execute_with_retry(ws.append_rows, new_rows)

    def overwrite_archived(self, archived_data):
        """Overwrites the Archived sheet with the provided data, preserving headers."""
        try:
            ws = self._get_worksheet("Archived")
            header = self._song_header(ws)
            # Read (and cache) the live contents BEFORE clearing anything
            if self._refuses_empty_overwrite(archived_data, self.get_archived_records(), "Archived"):
                return
            rows = self._build_song_rows(archived_data, header)

            self._archived_records_cache = None
            self._replace_rows(ws, [header] + rows)
            # Mirror what we just wrote (see overwrite_songs)
            self._archived_records_cache = self._rows_to_records(header, rows)
        except Exception as e:
            print(f"Error overwriting Archived: {e}")

    def add_to_archived_batch(self, songs_data):
        """Adds a list of songs to the Archived sheet."""
        if not songs_data:
            return
        ws = self._get_worksheet("Archived")
        header = self._song_header(ws)
        new_rows = self._build_song_rows(songs_data, header, year_as_str=False)

        self._archived_records_cache = None
        if new_rows:
            self._execute_with_retry(ws.append_rows, new_rows)

    def get_archived_vids(self):
        """Returns a set of Video IDs from the Archived sheet."""
        records = self.get_archived_records()
        return {r.get('Video ID') for r in records if r.get('Video ID')}

    def get_archived_records(self):
        """Returns all records from the Archived sheet as a list of dictionaries."""
        if self._archived_records_cache is not None:
            return self._archived_records_cache
            
        ws = self._get_worksheet("Archived")
        data = self._execute_with_retry(ws.get_all_values, value_render_option='UNFORMATTED_VALUE')
        if not data:
            self._archived_records_cache = []
            return []

        self._archived_records_cache = self._rows_to_records(data[0], data[1:])
        return self._archived_records_cache

    def overwrite_songs_sheet(self, songs_data):
        """Overwrites the Songs sheet with provided list of song dicts."""
        self.overwrite_songs(songs_data)

    def overwrite_genre_sheet(self, genre_counts):
        """Overwrites the Genre sheet with provided list of tuples (genre, count)."""
        ws = self._get_worksheet("Genre")
        header = ["Genre", "Count"]
        rows = [header]
        for genre, count in genre_counts:
            rows.append([genre, count])
        self._execute_with_retry(ws.clear)
        self._execute_with_retry(ws.update, range_name='A1', values=rows)
