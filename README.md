# 🌌 Vibemus

**YouTube Music automation** — track artists, discover new releases, synchronize playlists, and maintain a complete music library backed by Google Sheets and Last.fm.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Authentication](#authentication)
4. [Configuration](#configuration)
5. [CLI Reference](#cli-reference)
   - [artist](#artist--manage-tracked-artists)
   - [sync](#sync--discovery--synchronization)
   - [playlist](#playlist--playlist-operations)
   - [system](#system--utilities)
6. [Legacy Commands](#legacy-commands)
7. [Project Structure](#project-structure)

---

## Requirements

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ (for cookie auth) |
| Google Chrome | Latest |

Python dependencies (see `requirements.txt`):
```
ytmusicapi
gspread
oauth2client
```

```bash
pip install -r requirements.txt
```

---

## Installation

```bash
git clone <repo>
cd Vibemus
pip install -r requirements.txt
npm install            # installs puppeteer for grab_cookies.js
```

### Make the `vibemus` command available globally

```bash
echo "alias vibemus='python3 $(pwd)/main.py'" >> ~/.zshrc && source ~/.zshrc
```

---

## Authentication

Vibemus needs three credential files inside the `config/` directory:

| File | Purpose |
|------|---------|
| `config/oauth.json` | YouTube Music OAuth (ytmusicapi) |
| `config/browser.json` | YouTube Music browser cookies |
| `config/service_account.json` | Google Sheets API service account |

### Getting YouTube Music cookies

Run the interactive authentication helper:

```bash
node grab_cookies.js
# or via CLI:
vibemus system auth
```

This opens an isolated Chrome window. Log into YouTube Music, then close the window. The cookies are saved automatically to `config/browser.json`.

### Setting up Google Sheets

1. Create a **Service Account** in [Google Cloud Console](https://console.cloud.google.com/).
2. Download the JSON key and save it as `config/service_account.json`.
3. Share your Google Sheet with the service account email.
4. Make sure the spreadsheet is named **`YouTube Music Vibemus`** (or change `SPREADSHEET_TITLE` in `src/config.py`).

---

## Configuration

Key settings in `src/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `PLAYLIST_ID` | `PL2_CnmTx…` | Your main inbox playlist (`#`) |
| `SOURCE_PLAYLISTS` | `["#", "Indie Pop", …]` | Playlists scanned when organizing artists |
| `LASTFM_USERNAME` | `amartelr` | Last.fm account for scrobble enrichment |
| `SCROBBLE_THRESHOLD` | `13` | Minimum scrobbles for a song to be kept |
| `SYNC_DELAY` | `2` | Seconds between API calls in batch operations |

---

## Caching System

Vibemus uses local JSON caches in the `data/` directory to optimize performance and respect API rate limits.

### 1. Last.fm Cache (`lastfm_cache.json`)
*   **Purpose**: Stores track metadata (genres/tags) and scrobble counts.
*   **Validity (TTL)**: **7 days**. Fresh data is reused automatically. Stale data may be used as a fallback unless a force-refresh is triggered.

### 2. Source Playlists Cache (`source_cache.json`)
*   **Purpose**: Local copy of your "source" playlists (Inbox, Genre lists) to speed up organization tasks.
*   **Validity**: **Manual/Proactive**. It does not expire by time.
*   **Updates**: Refreshed via `vibemus system refresh-cache` or `--refresh-cache`. It is proactively updated (items removed) when songs are successfully moved.
*   **⚠️ Stale Cache Warning**: If you manually remove or move songs using the YouTube Music app, the local cache will be out of sync. `apply-moves` might report songs as "Synced" when they are actually missing from YouTube. Always use `--refresh-cache` if you've made manual changes on YouTube recently.

### 3. Deep Sync Cache (`deep_sync_cache.json`)
*   **Purpose**: Tracks when each artist was last fully scanned during a deep sync.
*   **Validity**: **30 days**. Artists scanned within the last month are skipped during general deep sync operations to save time.

### 4. MusicBrainz Cache (`musicbrainz_cache.json`)
*   **Purpose**: Stores artist and track tags fetched from MusicBrainz.
*   **Validity**: **30 days** for artist info, **7 days** for track info. Helps respect the strict 1 req/s rate limit.

---

## 💡 Sync Logic & Status Guide

Vibemus uses a **double-layer filtering system** to optimize discovery operations and respect API rate limits.

### The "Double-Layer" Filter
When running `vibemus sync deep`, the system evaluates artists in two steps:

1.  **Google Sheet Check (Persistent)**: 
    - The program looks for artists with `Status: Pending` or an empty `Last Checked` field in your spreadsheet.
    - If an artist is marked as `Done` or `Archived`, they are skipped immediately.
2.  **Local Cache Check (Temporal)**:
    - If an artist is "Pending" in the sheet, the system checks the local `data/deep_sync_cache.json`.
    - If the artist was already checked within the last **30 days** (configurable), they are skipped even if their field in the sheet is empty. This prevents infinite retries of artists with no new content.

### Artist Status Meanings
- **`Pending`**: New artist or needs a deep scan.
- **`Done`**: Exploration finished. The system has successfully scanned their discography and added any chosen songs.
- **`Archived`**: You've decided to stop tracking this artist. They won't appear in any sync commands.

> [!TIP]
> **Force a re-scan**: If an artist is being skipped because of the 30-day cooling period, you can force a fresh start by deleting the local cache: `rm data/deep_sync_cache.json`.

---

## CLI Reference

```
vibemus <group> <action> [options]
```

---

### `artist` — Manage Tracked Artists

#### `vibemus artist add "Name" [--playlist "Genre"]`
Search YouTube Music and start tracking an artist.

- **With `--playlist`**: Assigns the target playlist in the 'Artists' sheet and immediately migrates existing songs in the library to that playlist.
- **Deep Sync Interactive**: After adding, it immediately launches the interactive deep sync logic to search for recent releases (2025/2026) and the most popular catalogue gems, allowing you to populate your library right away.

**Examples:**
```bash
vibemus artist add "Radiohead"
vibemus artist add "Hax!" --playlist "Emo"
```

---

#### `vibemus artist remove "Name"`
Stop tracking an artist and clean up their sheet data.

```bash
vibemus artist remove "Band of Horses"
```

---



---

### `sync` — Discovery & Synchronization

---

#### `vibemus sync deep [--auto]`
**Deep maintenance sync** — scans all artists not checked in the last 6 months.

- Applies intelligent deduplication.
- Enriches songs with Last.fm tags.
- Prompts interactively for each artist: **[c]ontinue**, **[s]kip**, or **[r]emove**.
- `--auto` skips all prompts and processes all candidates automatically.

```bash
vibemus sync deep
vibemus sync deep --auto
```

---

#### `vibemus sync playlist [--name "Name"] [--skip-lastfm]`
Reconcile one or all source playlists against your `Songs` sheet.

- Updates scrobble counts, like status, and metadata.
- Moves **liked songs** to the artist's target playlist (from `#` only).
- Archives **disliked songs** (from any playlist).
- `--name` limits the sync to a single named playlist.
- `--skip-lastfm` skips Last.fm enrichment for a faster run.
- **🛡️ Data Safety**: If a song is present in the `Songs` sheet but cannot be found in the corresponding YouTube playlist, the system considers it "Missing from YouTube" and moves it to the `Archived` sheet to keep your catalog clean without losing metadata.

```bash
vibemus sync playlist
vibemus sync playlist --name "#"
vibemus sync playlist --name "#" --skip-lastfm
```

---

#### `vibemus sync artist`
Synchronize your **Artists** tracking list based on your existing **Songs** catalog (excluding Inbox songs).

- **Discovery**: Automatically identifies artists present in your 'Songs' sheet that are not yet being tracked.
- **Onboarding**: Interactively asks for a default playlist for each new artist found.
- **Cleanup**: Updates the `Song Count` for all artists based on the total number of entries in the spreadsheet.
- **Enrichment**: Fetches YouTube Artist IDs and Last.fm Genres for new artists.

```bash
vibemus sync artist
```


---

#### `vibemus sync new-releases`
Scan global new releases from YouTube Music and check for updates from all your tracked artists.

```bash
vibemus sync new-releases
```

---



> [!TIP]
> **Recommended Weekly Routine**
> If you have been manually moving songs around in YouTube Music during the week, run these two commands to leave everything perfectly synced:
> 
> 1. **Process your Inbox**: `vibemus sync playlist --name "#" --skip-lastfm`
>    *This empties the Inbox by processing your Likes (moving them to their definitive playlists) and Dislikes (archiving them).*
> 2. **Sync the General Catalog**: `vibemus sync playlist --skip-lastfm`
>    *This generic command scans all your other tracked playlists. It will detect manual moves between playlists, deletions (archiving them), and additions, reflecting everything accurately in the Google Sheet.*

---

### `playlist` — Playlist Operations

#### `vibemus playlist archive --name "Playlist Name" --year YYYY`
Archive songs from a specific playlist that were released on or before a given year.

- Moves qualifying songs to a parallel `<PlaylistName> $` playlist.
- Removes them from the original playlist to keep it fresh and concise.
- **⚠️ Important Warning:** After running this command, YouTube Music servers might need a few minutes to process the changes across all caches. **Do not run `vibemus sync playlist` immediately** after an archive operation. Doing so might cause the sync to misinterpret the delayed API response and permanently move your songs to the 'Archived' sheet. Wait roughly 3 to 5 minutes before syncing.

```bash
vibemus playlist archive --name "Indie Folk" --year 2021
```

---

#### `vibemus playlist apply-moves [--artist "Name"] [--refresh-cache]`
Sync manual changes made to the "Playlist" column in your Google Sheet back to YouTube Music.

- Scans the **Songs** sheet for songs whose playlist name differs from YouTube.
- Automatically **removes** the song from the old playlist and **adds** it to the new one.
- Ignores changes to/from the `#` playlist.
- **`--artist "Name"`**: Process only moves for a specific artist.
- **`--refresh-cache`**: Forces a fresh download of playlist data from YouTube before starting. Recommended if you have made manual changes on the YouTube Music app.
- **`--api {lastfm,musicbrainz}`**: Choose the metadata provider for genres and artist info. 
  - `lastfm` (default): Fast, includes scrobble counts.
  - `musicbrainz`: High-quality community tags, follows strict 1 req/s rate limit.

```bash
vibemus playlist apply-moves
vibemus playlist apply-moves --artist "The Drums"
vibemus playlist apply-moves --refresh-cache
```

> [!IMPORTANT]
> **Manual Changes on YouTube:** If you've been moving songs using the YouTube Music app, the local cache will be outdated. **Always use `--refresh-cache`** to ensure `apply-moves` sees the current state of your playlists, otherwise it might skip moves thinking they are already "in sync".

---




---



---



---

### `system` — Utilities

#### `vibemus system reset`
Clear the main playlist and reset history. **Requires typing `yes` to confirm.**

```bash
vibemus system reset
```

---

#### `vibemus system refresh-cache`
Force a full refresh of the local source playlist cache (`data/source_cache.json`).

```bash
vibemus system refresh-cache
```

---

#### `vibemus system auth`
Launch the `grab_cookies.js` browser authentication helper. Run this if Vibemus reports that your session has expired.

```bash
vibemus system auth
```

---

## Legacy Commands

Old-style flags (`--deep-sync`, `--add-artist`, etc.) still work and are automatically translated. A deprecation warning shows the equivalent new command:

```
⚠ '--deep-sync' is deprecated. Use: vibemus sync deep
```

| Old command | New command |
|-------------|-------------|
| `--add-artist "X"` | `vibemus artist add "X"` |
| `--remove-artist "X"` | `vibemus artist remove "X"` |



| `--deep-sync` | `vibemus sync deep` |
| `--sync-new-releases` | `vibemus sync new-releases` |
| `--sync-playlist` | `vibemus sync playlist` |
| `--cleanup-inbox` | `vibemus playlist cleanup-inbox` |



| `--refresh-source-cache` | `vibemus system refresh-cache` |

---

## Project Structure

```
Vibemus/
├── main.py                  # Entry point — thin CLI dispatcher
├── grab_cookies.js          # Browser auth helper (Node.js + Puppeteer)
├── requirements.txt
├── package.json
├── config/                  # Credentials (git-ignored)
│   ├── oauth.json
│   ├── browser.json
│   └── service_account.json
├── data/                    # Local caches (git-ignored)
│   ├── source_cache.json
│   ├── deep_sync_cache.json
│   └── lastfm_cache.json
├── src/
│   ├── config.py            # App-wide settings
│   ├── cli/
│   │   ├── parser.py        # Argument parser (subcommands + legacy aliases)
│   │   └── commands.py      # Handler functions per subcommand
│   ├── core/
│   │   └── manager.py       # Core business logic
│   └── services/
│       ├── yt_service.py    # YouTube Music API wrapper
│       ├── sheets_service.py # Google Sheets API wrapper
│       └── lastfm_service.py # Last.fm API wrapper
└── tests/
    └── test_cli_parser.py   # CLI parser unit tests (35 tests)
```
