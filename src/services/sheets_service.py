import gspread
import time
from datetime import datetime
from ..config import Config

class SheetsService:
    def __init__(self):
        # Authenticate using newer gspread.service_account approach (uses google-auth)
        # It handles scopes automatically: spreadsheets and drive
        self.client = gspread.service_account(filename=Config.SERVICE_ACCOUNT_FILE)
        self.spreadsheet = self._get_or_create_spreadsheet()
        
        # Cache for current run
        self._artists_cache = None
        self._songs_vid_cache = None  # replaces History cache

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
                ws = self.spreadsheet.add_worksheet(title=title, rows=1000, cols=10)
                if title == "Artists":
                    ws.append_row(["Artist Name", "Artist ID", "Song Count", "Last Checked", "Status", "Genre", "Playlist"])
                elif title == "Genre":
                    ws.append_row(["Genre", "Count"])
                elif title in ["Songs", "Archived"]:
                    ws.append_row(["Playlist", "Artist", "Title", "Album", "Year", "Genre", "Scrobble", "LastfmScrobble", "Video ID"])
                else:
                    # Default header for playlist exports
                    ws.append_row(["Playlist", "Artist", "Album", "Title", "Views"])
                return ws
        
        return self._execute_with_retry(_fetch)

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
        new_rows = []
        if existing_rows:
            header = existing_rows[0]
            new_rows.append(header)
            
            # Find the index of 'Playlist' column just in case, usually 0
            try:
                playlist_col_idx = header.index("Playlist")
            except ValueError:
                playlist_col_idx = 0
            
            # Keep rows that belong to OTHER playlists
            for row in existing_rows[1:]:
                # safely get column
                if len(row) > playlist_col_idx:
                    row_pl_name = row[playlist_col_idx]
                    if row_pl_name != current_playlist_name:
                        new_rows.append(row)
                else:
                    # Row looks malformed, keep it or discard? Keep it to be safe.
                    new_rows.append(row)
        else:
            # Sheet is empty, add header
            new_rows.append(["Playlist", "Artist", "Title", "Album", "Year", "Genre", "Scrobble", "LastfmScrobble", "Video ID"])

        # Add new songs
        for s in songs:
            new_rows.append([
                s.get("Playlist", ""),
                s.get("Artist", ""),
                s.get("Title", ""),
                s.get("Album", ""),
                s.get("Year", ""),
                s.get("Genre", ""),
                self._to_int(s.get("Scrobble")),
                self._to_int(s.get("LastfmScrobble")),
                s.get("Video ID", "")
            ])
            
        print(f"Updating sheet... (Total rows: {len(new_rows)})")
        self._execute_with_retry(ws.clear)
        self._execute_with_retry(ws.update, range_name='A1', values=new_rows)
        
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
        headers = ["Artist Name", "Artist ID", "Song Count", "Last Checked", "Status", "Genre", "Playlist"]
        
        # Safety check: if artists_data is empty but we HAD artists before, abort to prevent wiping.
        if not artists_data and self._artists_cache:
            print("  \033[91m🛑 ERROR: Attempted to save an empty artist list. Aborting to save data.\033[0m")
            return

        # Prepare rows
        rows = [headers]
        for artist in artists_data:
            rows.append([
                artist.get("Artist Name", ""),
                artist.get("Artist ID", ""),
                artist.get("Song Count", 0),
                artist.get("Last Checked", ""),
                artist.get("Status", ""),
                artist.get("Genre", ""),
                artist.get("Playlist", "")
            ])
        
        self._execute_with_retry(ws.clear)
        self._execute_with_retry(ws.update, range_name='A1', values=rows)
        self._artists_cache = artists_data

    def add_artist(self, artist_row):
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
            print(f"      🆕 Artist '{name}' added to tracking list.")
        else:
            # If it already exists, just save artists to ensure sheet is in sync with memory
            # (In case memory had the duplicate but sheet didn't, or vice-versa)
            self.save_artists(artists)

    def update_artist_status(self, artist_name, status):
        """Updates the status of a specific artist."""
        artists = self.get_artists()
        updated = False
        norm_target = str(artist_name).lower().strip()
        for a in artists:
            if str(a.get("Artist Name", "")).lower().strip() == norm_target:
                a["Status"] = status
                updated = True
                break
        if updated:
            self.save_artists(artists)

    def update_artist_last_checked(self, artist_name, date_str):
        """Updates the last checked date of a specific artist."""
        artists = self.get_artists()
        updated = False
        norm_target = str(artist_name).lower().strip()
        for a in artists:
            if str(a.get("Artist Name", "")).lower().strip() == norm_target:
                a["Last Checked"] = date_str
                updated = True
                break
        if updated:
            self.save_artists(artists)

    def update_artist_playlist(self, artist_name, playlist_name, artist_id=None, genre=None, song_count=0):
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
            new_artist = {
                "Artist Name": artist_name,
                "Artist ID": artist_id or "",
                "Playlist": playlist_name,
                "Status": "Pending", # Status for artists awaiting their first scan
                "Song Count": song_count or 0,
                "Last Checked": datetime.now().strftime("%d/%m/%Y") if not artist_id else "", # empty to trigger sync if not yet performed
                "Genre": genre or ""
            }

            self.add_artist(new_artist)
            print(f"      🆕 Artist '{artist_name}' added to sheet.")



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
        ws = self._get_worksheet("Songs")
        # Use UNFORMATTED_VALUE to get raw numbers instead of locale-formatted strings
        data = self._execute_with_retry(ws.get_all_values, value_render_option='UNFORMATTED_VALUE')
        if not data:
            return []
        headers = data[0]
        records = []
        for row in data[1:]:
            record = {}
            for i, h in enumerate(headers):
                record[h] = row[i] if i < len(row) else ''
            records.append(record)
        return records

    def overwrite_songs(self, records):
        """Rewrites the entire Songs sheet using an atomic update for performance and reliability."""
        ws = self._get_worksheet("Songs")
        header = ["Playlist", "Artist", "Title", "Album", "Year", "Genre", "Scrobble", "LastfmScrobble", "Video ID"]
        rows = [header]
        for r in records:
            rows.append([
                r.get('Playlist', ''),
                r.get('Artist', ''),
                r.get('Title', ''),
                r.get('Album', ''),
                str(r.get('Year', '')),
                r.get('Genre', ''),
                self._to_int(r.get('Scrobble')),
                self._to_int(r.get('LastfmScrobble')),
                r.get('Video ID', '')
            ])
        try:
            self._execute_with_retry(ws.clear)
            # Use batch update for atomicity
            self._execute_with_retry(ws.update, range_name='A1', values=rows)
        except Exception as e:
            print(f"Error overwriting Songs: {e}")

    def add_to_songs_batch(self, songs_data):
        """Adds a list of songs to the Songs sheet."""
        if not songs_data:
            return
        ws = self._get_worksheet("Songs")
        new_rows = []
        for s in songs_data:
            new_rows.append([
                s.get('Playlist', ''),
                s.get('Artist', ''),
                s.get('Title', ''),
                s.get('Album', ''),
                s.get('Year', ''),
                s.get('Genre', ''),
                self._to_int(s.get('Scrobble')),
                self._to_int(s.get('LastfmScrobble')),
                s.get('Video ID', '')
            ])
        if new_rows:
            self._execute_with_retry(ws.append_rows, new_rows)

    def overwrite_archived(self, archived_data):
        """Overwrites the Archived sheet with the provided data, preserving headers."""
        try:
            ws = self._get_worksheet("Archived")
            header = ["Playlist", "Artist", "Title", "Album", "Year", "Genre", "Scrobble", "LastfmScrobble", "Video ID"]
            rows = []
            for s in archived_data:
                rows.append([
                    s.get('Playlist', ''),
                    s.get('Artist', ''),
                    s.get('Title', ''),
                    s.get('Album', ''),
                    str(s.get('Year', '')),
                    s.get('Genre', ''),
                    self._to_int(s.get('Scrobble')),
                    self._to_int(s.get('LastfmScrobble')),
                    s.get('Video ID', '')
                ])
            self._execute_with_retry(ws.clear)
            self._execute_with_retry(ws.append_row, header)
            if rows:
                self._execute_with_retry(ws.append_rows, rows)
        except Exception as e:
            print(f"Error overwriting Archived: {e}")

    def add_to_archived_batch(self, songs_data):
        """Adds a list of songs to the Archived sheet."""
        if not songs_data:
            return
        ws = self._get_worksheet("Archived")
        new_rows = []
        for s in songs_data:
            new_rows.append([
                s.get('Playlist', ''),
                s.get('Artist', ''),
                s.get('Title', ''),
                s.get('Album', ''),
                s.get('Year', ''),
                s.get('Genre', ''),
                self._to_int(s.get('Scrobble')),
                self._to_int(s.get('LastfmScrobble')),
                s.get('Video ID', '')
            ])
        if new_rows:
            self._execute_with_retry(ws.append_rows, new_rows)

    def get_archived_vids(self):
        """Returns a set of Video IDs from the Archived sheet."""
        records = self.get_archived_records()
        return {r.get('Video ID') for r in records if r.get('Video ID')}

    def get_archived_records(self):
        """Returns all records from the Archived sheet as a list of dictionaries."""
        ws = self._get_worksheet("Archived")
        data = self._execute_with_retry(ws.get_all_values, value_render_option='UNFORMATTED_VALUE')
        if not data:
            return []
        headers = data[0]
        records = []
        for row in data[1:]:
            record = {}
            for i, h in enumerate(headers):
                record[h] = row[i] if i < len(row) else ''
            records.append(record)
        return records

    def overwrite_songs_sheet(self, songs_data):
        """Overwrites the Songs sheet with provided list of song dicts."""
        ws = self._get_worksheet("Songs")
        header = ["Playlist", "Artist", "Title", "Album", "Year", "Genre", "Scrobble", "LastfmScrobble", "Video ID"]
        rows = [header]
        for s in songs_data:
            rows.append([
                s.get('Playlist', ''),
                s.get('Artist', ''),
                s.get('Title', ''),
                s.get('Album', ''),
                str(s.get('Year', '')),
                s.get('Genre', ''),
                self._to_int(s.get('Scrobble')),
                self._to_int(s.get('LastfmScrobble')),
                s.get('Video ID', '')
            ])
        self._execute_with_retry(ws.clear)
        self._execute_with_retry(ws.update, range_name='A1', values=rows)

    def overwrite_genre_sheet(self, genre_counts):
        """Overwrites the Genre sheet with provided list of tuples (genre, count)."""
        ws = self._get_worksheet("Genre")
        header = ["Genre", "Count"]
        rows = [header]
        for genre, count in genre_counts:
            rows.append([genre, count])
        self._execute_with_retry(ws.clear)
        self._execute_with_retry(ws.update, range_name='A1', values=rows)
