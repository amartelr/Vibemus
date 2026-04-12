# 🌌 Vibemus

**YouTube Music automation** — track artists, discover new releases, synchronize playlists, and maintain a complete music library backed by Google Sheets and Last.fm.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Authentication](#authentication)
4. [Configuration](#configuration)
5. [💡 Sync Logic & Status Guide](#-sync-logic--status-guide)
   - [🔄 Sync Commands Comparison](#-sync-commands-comparison)
6. [CLI Reference](#cli-reference)
   - [artist](#artist--manage-tracked-artists)
   - [releases](#releases--artist-release-monitoring)
   - [deep](#deep--deep-scanning--maintenance)
   - [new-releases](#new-releases--latest-drops)
   - [genre](#genre--genre-taxonomy-management)
   - [library](#library--youtube-music-library-sync)
   - [playlist](#playlist--playlist-operations)
   - [system](#system--utilities)
7. [Legacy Commands](#legacy-commands)
8. [Project Structure](#project-structure)

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

### 5. Genre Preferences (`genre_preferences.json`)
*   **Purpose**: Stores your "Approved" and "Ignored" genre lists for the `sync genre` command.
*   **Usage**: Prevents clutter from geographical tags (e.g., "British") or generic terms.
*   **Interactivity**: New genres found during sync will trigger a prompt to add them to either list.

---

## 💡 Sync Logic & Status Guide

Vibemus uses a **double-layer filtering system** to optimize discovery operations and respect API rate limits.

### The "Double-Layer" Filter
When running `vibemus deep sync`, the system evaluates artists in two steps:

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

---

### 🔄 Sync Commands Comparison
Vibemus offers three different ways to discover and sync music. Use this table to choose the right command based on your needs:

| Command | Frequency | Scan Method | Scope | Best for... |
|:---|:---|:---|:---|:---|
| **`new-releases sync`** | **Daily** | Global "New Releases" shelf | Top global hits from your artists | ⚡ Instant daily catch-up (seconds). |
| **`releases sync`** | **Weekly** | Individual artist profiles | Every new single/album from your list | 🎯 Full monitoring of your specific artists. |
| **`deep sync`** | **Monthly** | Discography & Top Tracks | Entire catalog + Pending artists | 💎 Onboarding new artists or catalog gems. |

> [!TIP]
> **Workflow Suggestion**: Use `new-releases` daily to catch big drops instantly. Run `releases` once a week to ensure nothing was missed. Use `deep` only for new artists or when you want a thorough review of your collection.

---

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

#### `vibemus artist sync`
Synchronize your **Artists** tracking list based on your existing **Songs** catalog (excluding Inbox songs).

- **Discovery**: Automatically identifies artists present in your 'Songs' sheet that are not yet being tracked.
- **Onboarding**: Interactively asks for a default playlist for each new artist found.
- **Cleanup**: Updates the `Song Count` for all artists based on the total number of entries in the spreadsheet.
- **Enrichment**: Fetches YouTube Artist IDs and Last.fm Genres for new artists.

```bash
vibemus artist sync
```

---

### `releases` — Artist Release Monitoring

---

#### `vibemus releases sync [--force] [--auto]`
Scan for new albums and singles from **all tracked artists**.

- **Targeted Scan**: Directly visits the profile of every artist in your 'Artists' sheet.
- **Filtering**: Automatically excludes songs already in your library or archive.
- **Metadata**: Shows Last.fm scrobble counts directly in the prompt: `[Listeners🎧 | Your Plays👤]`.
- **`--force`**: Re-scans all artists even if they were checked recently (ignores the 24h window).
- **`--auto`**: Skips interactive prompts and adds all found songs to the `#` playlist.

```bash
vibemus releases sync
vibemus releases sync --force --auto
```

### `deep` — Deep Scanning & Maintenance

---

#### `vibemus deep sync [--auto]`
**Deep maintenance sync** — scans all artists not checked in the last 6 months.

- Applies intelligent deduplication.
- Enriches songs with Last.fm tags.
- Prompts interactively for each artist: **[c]ontinue**, **[s]kip**, or **[r]emove**.
- `--auto` skips all prompts and processes all candidates automatically.

```bash
vibemus deep sync
vibemus deep sync --auto
```

---

### `new-releases` — Latest Drops

---

#### `vibemus new-releases sync [--auto]`
Scan global new releases from YouTube Music and check for updates from all your tracked artists.

- `--auto` skips all prompts and processes all candidates automatically.

```bash
vibemus new-releases sync
vibemus new-releases sync --auto
```

---

### `genre` — Genre Taxonomy Management

---

#### `vibemus genre sync`
Update the **Genre** summary sheet in your Google Spreadsheet.

- **Interactive Filtering**: If it detects a genre not in your "Approved" or "Ignored" lists, it will prompt you:
    - `y` (Yes): Track it (adds to Approved).
    - `n` (No): Skip it this time.
    - `i` (Ignore): Never track it (adds to Ignored).
    - `q` (Quit): Save current decisions and exit.
- **Normalization**: Automatically applies **Title Case** and splits multi-genre strings (e.g., `noise rock, indie` → `Noise Rock` + `Indie`).

```bash
vibemus genre sync
```

---

### `library` — YouTube Music Library Sync

---

#### `vibemus library sync`
Bidirectional synchronization between your YouTube Music Library and your playlists (Songs sheet).

- **📥 ADD**: Songs that are in playlists (Songs sheet, excluding `#`) but NOT saved in your YouTube library will be added.
- **📤 REMOVE**: Songs that are in your library but NOT in any playlist (and not Liked) will be removed.
- **💛 Liked Protection**: Liked songs are never removed, even if they aren't in any playlist.
- **Preview**: Shows a preview of all additions and removals before executing.
- **Confirmation**: Requires explicit confirmation before making any changes.

```bash
vibemus library sync
```

> [!TIP]
> Run this after `playlist sync` or `apply-moves` to ensure your YouTube Music library is fully in sync with your curated playlists.

---

### `playlist` — Playlist Operations

---

#### `vibemus playlist sync [--name "Name"] [--skip-lastfm]`
Reconcile one or all source playlists against your `Songs` sheet.

- Updates scrobble counts, like status, and metadata.
- Moves **liked songs** to the artist's target playlist (from `#` only).
  - *Si el destino final de la canción es una playlist de archivo (fuera de SOURCE_PLAYLISTS), automáticamente le quitará el Like en YouTube.*
  - *Si además la canción tiene muy pocas reproducciones (<= 1 scrobble por defecto), la enviará también a la lista reservada **Pendiente**.*
- Archives **disliked songs** (from any playlist).
- `--name` limits the sync to a single named playlist.
- `--skip-lastfm` skips Last.fm enrichment for a faster run.
- **🛡️ Data Safety**: If a song is present in the `Songs` sheet but cannot be found in the corresponding YouTube playlist, the system considers it "Missing from YouTube" and moves it to the `Archived` sheet to keep your catalog clean without losing metadata.

```bash
vibemus playlist sync
vibemus playlist sync --name "#"
vibemus playlist sync --name "#" --skip-lastfm
```

---

#### `vibemus playlist review-pending [N]`
**Bandeja de revisión de biblioteca antigua** — localiza canciones "olvidadas" para decidir si mantenerlas o eliminarlas.

- **Criterio de Selección**: Busca canciones con **reproducciones menores o iguales al número indicado** (`Scrobble <= N`). Si no se indica nada, el valor por defecto es **2**.
- **Alcance Inteligente**: Solo escanea playlists que tengan un **intervalo de años** en su título (ej. `2010-2015`), ignorando tus listas activas y la bandeja de entrada `#`.
- **Limpieza de Dislikes**: Si marcas una canción como "No me gusta" (Dislike) dentro de la playlist `Pendiente`:
    - El script la **eliminará de todas tus playlists** de YouTube Music.
    - La marcará como **"Indiferente"** en YouTube para limpiar tu algoritmo.
    - La moverá a la pestaña **Archived** de tu Google Sheet.
- **Detección de Likes**: Si la marcas como "Me gusta" (Like):
    - La eliminará de tu lista `Pendiente` (porque ya ha sido evaluada positivamente).
    - Te la mantendrá como Like en YouTube para mejorar tus recomendaciones.
    - Pondrá el contador de reproducciones en el Sheet automáticamente a **4** (para evitar que en el futuro vuelva a entrar en esta bandeja de revisión).
- **Auto-Graduación**: Si una canción sigue evaluándose y escuchándola orgánicamente supera el límite que has introducido en el comando, el bot la considerará "graduada" y la eliminará silenciosamente de la lista Pendiente.
- **Independencia**: La playlist `Pendiente` es totalmente independiente y no se sincroniza con tus listas de género habituales.

```bash
# Busca canciones con 0, 1 o 2 reproducciones (default)
vibemus playlist review-pending

# Busca canciones que nunca has escuchado (0 reproducciones)
vibemus playlist review-pending 0

# Busca canciones con 5 reproducciones o menos
vibemus playlist review-pending 5
```

---

#### `vibemus playlist list`
Displays a comparative table of all your playlists (including historical archives), contrasting the total song count in **YouTube Music** vs. your **Google Sheet (Songs)**.

- **Difference Detection**: Highlights mismatched playlists in yellow and shows exactly how many songs are missing on either side.
- **Interactive Correction**: If discrepancies are found, it offers to automatically run `playlist sync --skip-lastfm` for the affected collections only, ensuring your catalog is perfectly aligned.

```bash
# View global status and (optionally) fix mismatched playlists
vibemus playlist list
```

---

#### `vibemus playlist split --name "Playlist" --parts N`
Divide una colección (playlist principal y sus archivos) en **N partes aproximadamente iguales** basadas en el año de lanzamiento.

- **Diferencial**: El sistema analiza la densidad de canciones en toda tu base de datos para proponer cortes cronológicos inteligentes.
- **Doble Verificación**: Al finalizar, ejecuta un motor de consistencia que asegura que cada canción esté en el "cubo" temporal correcto según su metadato de año.
- **Higiene de Playlists**: Borra automáticamente listas vacías y obsoletas tras los movimientos.

```bash
# Divide la colección "Rock" en 3 bloques temporales equilibrados
vibemus playlist split --name "Rock" --parts 3
```

---

#### `vibemus playlist apply-moves [--artist "Name"] [--playlist "Name"] [--refresh-cache]`
Sync manual changes made to the "Playlist" column in your Google Sheet back to YouTube Music.

- Scans the **Songs** sheet for songs whose playlist name differs from YouTube.
- Automatically **removes** the song from the old playlist and **adds** it to the new one.
- Ignores changes to/from the `#` playlist.
- **`--artist "Name"`**: Process only moves for a specific artist.
- **`--playlist "Name"`**: Process only moves where the target playlist in the sheet matches this name (e.g., "Crank Wave").
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
⚠ '--deep-sync' is deprecated. Use: vibemus deep sync
```

| Old command | New command |
|-------------|-------------|
| `--add-artist "X"` | `vibemus artist add "X"` |
| `--remove-artist "X"` | `vibemus artist remove "X"` |



| `--deep-sync` | `vibemus deep sync` |
| `--sync-releases` | `vibemus releases sync` |
| `--sync-new-releases` | `vibemus new-releases sync` |
| `--sync-playlist` | `vibemus playlist sync` |
| `--cleanup-inbox` | `vibemus playlist cleanup-inbox` |
| `--cleanup-library` | `vibemus library sync` |
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
│   ├── lastfm_cache.json
│   └── genre_preferences.json # Your approved/ignored genre lists
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
