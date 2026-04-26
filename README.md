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
   - [new-releases](#new-releases--latest-drops)
   - [genre](#genre--genre-taxonomy-management)
   - [library](#library--youtube-music-library-sync)
   - [playlist](#playlist--playlist-operations)
   - [system](#system--utilities)
7. [Legacy Commands](#legacy-commands)
8. [Project Structure](#project-structure)

---

## ⌨️ Command Shortcuts

To save typing, you can use the following aliases for command groups and actions:

| Category | Group Alias | Actions |
|:---|:---|:---|
| **Artist** | `art` | `ls` (list), `ad` (add), `rm` (remove), `sy` (sync), `cc` (cleanup-collabs) |
| **Playlist** | `pl` | `ls` (list), `sy` (sync), `ci` (cleanup-inbox), `cul` (cleanup-likes), `am` (apply-moves), `sp` (split), `rp` (review-pending) |
| **YouTube** | `yt` | `ss` (sync-subs), `cs` (cleanup-shorts), `cw` (cleanup-watched), `utc` (update-top-channels) |
| **Releases** | `rel` | `sy` (sync) |
| **System** | `sys` | `rc` (refresh-cache), `au` (auth) |
| **Library** | `lib` | `sy` (sync) |
| **Genre** | `gen` | `sy` (sync) |

**Examples:**
```bash
# Full version
vibemus artist list
vibemus playlist sync --name "#"

# Shortcut version
vibemus art ls
vibemus pl sy --name "#"
```

---

## ⚡ Quick Reference Guide

| Category | Command (Short) | Description |
|:---|:---|:---|
| **Discovery** | `rel sy` | Scan profile of every tracked artist (Full monitor). |
| | `nr sy` | Scan global YouTube shelf for tracked artists (Fast scan). |
| **Artist** | `art ad "Name"` | Start tracking a new artist and sync discography. |
| | `art sy` | Add missing artists found in your library to the tracking list. |
| | `art ls` | Show all currently tracked artists and their status. |
| **Playlist** | `pl sy [--name PL]` | Consolidate inbox, move likes, and archive dislikes. |
| | `pl ls` | Compare song counts between YT and Google Sheets. |
| | `pl am [--refresh-cache]` | Push manual playlist changes from Sheets to YouTube. |
| | `pl rp [N]` | Review low-listen songs in a dedicated tray. |
| **Maintenance** | `lib sy` | Add playlist songs to library / remove orphans. |
| | `pl ci` | Remove songs from '#' that are already organized. |
| | `pl sp --name PL --parts N` | Split archives into year-based chunks. |
| **YouTube** | `yt ss [--reset]` | Sync new subscription videos to '📥 Para Ver' (4 phases). |
| | `yt utc` | Recalculate and save the top-N most-active channels cache. |
| **System** | `sys au` | Refresh YouTube Music account authentication. |
| | `sys rc` | Force update of local playlist metadata cache. |

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
google-api-python-client
google-auth-oauthlib
google-auth-httplib2
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
| `config/youtube_client_secrets.json` | YouTube Data API v3 OAuth secrets |

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

### Setting up YouTube Data API (Subscriptions Sync)

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Enable **YouTube Data API v3**.
3. Create **OAuth 2.0 Client ID** as **Desktop App**.
4. Download the JSON and save it as `config/youtube_client_secrets.json`.
5. Run `vibemus youtube sync-subs` to authorize (opens browser once).

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
*   **Validity (TTL)**: **7 days**. Fresh data is reused automatically.
*   **⚡ Conditional Refresh**: In `playlist sync`, songs in **SOURCE_PLAYLISTS** with **fewer than 4 scrobbles** always trigger a direct API lookup to Last.fm (ignoring the cache). Archives and other lists use the standard cache TTL.
*   **Fallback**: Stale data may be used as a fallback if the API is unavailable, unless a force-refresh is triggered via `apply-moves`.

### 2. Source Playlists Cache (`source_cache.json`)
*   **Purpose**: Local copy of your "source" playlists (Inbox, Genre lists) to speed up organization tasks.
*   **Validity**: **Manual/Proactive**. It does not expire by time.
*   **Updates**: Refreshed via `vibemus system refresh-cache` or `--refresh-cache`. It is proactively updated (items removed) when songs are successfully moved.
*   **⚠️ Stale Cache Warning**: If you manually remove or move songs using the YouTube Music app, the local cache will be out of sync. `apply-moves` might report songs as "Synced" when they are actually missing from YouTube. Always use `--refresh-cache` if you've made manual changes on YouTube recently.


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

### Artist Sync Logic
Vibemus uses the `releases sync` command to monitor your artists. It checks for new releases and updates the 'Last Checked' date in your spreadsheet.

### Artist Status Meanings
- **`Pending`**: New artist awaiting scan.
- **`Done`**: Exploration finished. The system has successfully scanned their discography and added any chosen songs.
- **`Archived`**: You've decided to stop tracking this artist. They won't appear in any sync commands.

---

### 🔄 Sync Commands Comparison
Vibemus offers three different ways to discover and sync music. Use this table to choose the right command based on your needs:

| Command | Frequency | Scan Method | Scope | Best for... |
|:---|:---|:---|:---|:---|
| **`new-releases sync`** | **Daily** | Global "New Releases" shelf | Top global hits from your artists | ⚡ Instant daily catch-up (seconds). |
| **`releases sync`** | **Weekly** | Individual artist profiles | Every new single/album from your list | 🎯 Full monitoring of your specific artists. |

> [!TIP]
> **Workflow Suggestion**: Use `new-releases` daily to catch big drops instantly. Run `releases` once a week to ensure nothing was missed.

---

---

## CLI Reference

```
vibemus <group> <action> [options]
```

---

### `artist` — Manage Tracked Artists

#### `vibemus artist list`
**Alias:** `vibemus art ls`
Show all currently tracked artists and their status (Pending, Done, Archived).

---

#### `vibemus artist search "Query"`
**Alias:** `vibemus art sh ...`
Search for an artist on YouTube Music to get their ID and metadata before adding.

**Example:**
```bash
vibemus art sh "Arctic Monkeys"
```

---

#### `vibemus artist add ["Name"] [--playlist "Genre"] [--api {lastfm,musicbrainz}]`
**Alias:** `vibemus art ad ...`
Search YouTube Music and start tracking an artist.

- **`--playlist PL`**: Assigns the target playlist in the 'Artists' sheet and immediately migrates existing songs in the library to that playlist.
- **`--api {lastfm,musicbrainz}`**: Metadata provider for initial discography discovery (default: `lastfm`).
- **Immediate Sync**: After adding, it immediately searches for recent releases and popular tracks to help you populate your library right away.

**Examples:**
```bash
vibemus art ad "Radiohead"
vibemus art ad "Hax!" --playlist "Emo"
vibemus art ad "The Smile" --api musicbrainz
```

---

#### `vibemus artist remove "Name"`
**Alias:** `vibemus art rm ...`
Stop tracking an artist and clean up their sheet data.

```bash
vibemus art rm "Band of Horses"
```

---

#### `vibemus artist sync`
**Alias:** `vibemus art sy`
Synchronize your **Artists** tracking list based on your existing **Songs** catalog (excluding Inbox songs).

- **Discovery**: Automatically identifies artists present in your 'Songs' sheet that are not yet being tracked.
- **Onboarding**: Interactively asks for a default playlist for each new artist found.
- **Cleanup**: Updates the `Song Count` for all artists based on the total number of entries in the spreadsheet.
- **Enrichment**: Fetches YouTube Artist IDs and Last.fm Genres for new artists.

```bash
vibemus art sy
```

---

#### `vibemus artist import`
**Alias:** `vibemus art im`
Import artists directly from your YouTube library based on the number of tracks you have for each.

---

#### `vibemus artist reset-empty`
**Alias:** `vibemus art re`
Reset the 'Last Checked' status for artists with 0 tracks. Useful for retrying a failed initial scan.

---

#### `vibemus artist archive-inactive`
**Alias:** `vibemus art ai`
Identify and archive artists who haven't released anything or haven't been listened to in years.

---

#### `vibemus artist cleanup-collabs`
**Alias:** `vibemus art cc`
Interactive cleanup of collaborative artist names to ensure they are mapped correctly to primary tracked entities.

---

### `releases` — Artist Release Monitoring

---

#### `vibemus releases sync [--force] [--auto] [--liked-only]`
**Alias:** `vibemus rel sy ...`
Scan for new albums and singles from **all tracked artists**.

- **Targeted Scan**: Directly visits the profile of every artist in your 'Artists' sheet.
- **Filtering**: Automatically excludes songs already in your library or archive.
- **Metadata**: Shows Last.fm scrobble counts directly in the prompt: `[Listeners🎧 | Your Plays👤]`.
- **`--force`**: Re-scans all artists even if they were checked recently (ignores the 24h window).
- **`--auto`**: Skips interactive prompts and adds all found songs to the `#` playlist.
- **`--liked-only`**: Only check artists that have at least one song in your Liked Songs collection.

**Examples:**
```bash
vibemus rel sy
vibemus rel sy --force --auto
vibemus rel sy --liked-only
```
- **`--force`**: Re-scans all artists even if they were checked recently (ignores the 24h window).
- **`--auto`**: Skips interactive prompts and adds all found songs to the `#` playlist.
- **`--liked-only`**: Filter artists to sync only those who have at least one song in your YouTube Music playlist named **"LM"** (or in your "Liked Songs" collection if "LM" does not exist). Ideal for a quick review of your most listened/recent artists.

```bash
vibemus releases sync
vibemus releases sync --force --auto
```


### `new-releases` — Latest Drops

---

#### `vibemus new-releases sync [--auto]`
**Alias:** `vibemus nr sy ...`
Scan global new releases from YouTube Music and check for updates from all your tracked artists.

- `--auto` skips all prompts and processes all candidates automatically.

**Examples:**
```bash
vibemus new-releases sync
vibemus nr sy --auto
```

---

### `genre` — Genre Taxonomy Management

---

#### `vibemus genre sync`
**Alias:** `vibemus gen sy`
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
**Alias:** `vibemus lib sy`
Bidirectional synchronization between your YouTube Music Library and your playlists (Songs sheet).

- **📥 ADD**: Songs that are in playlists (Songs sheet, excluding `#`) but NOT saved in your YouTube library will be added.
- **📤 REMOVE**: Songs that are in your library but NOT in any playlist (and not Liked) will be removed.
- **💛 Liked Protection**: Liked songs are never removed, even if they aren't in any playlist.
- **Preview**: Shows a preview of all additions and removals before executing.
- **Confirmation**: Requires explicit confirmation before making any changes.

```bash
vibemus library sync
vibemus lib sy
```

> [!TIP]
> Run this after `playlist sync` or `apply-moves` to ensure your YouTube Music library is fully in sync with your curated playlists.

---

### `playlist` — Playlist Operations

---

#### `vibemus playlist list`
**Alias:** `vibemus pl ls`
Displays a comparative table of all your playlists (including historical archives), contrasting the total song count in **YouTube Music** vs. your **Google Sheet (Songs)**.

- **Difference Detection**: Highlights mismatched playlists in yellow and shows exactly how many songs are missing on either side.
- **Interactive Correction**: If discrepancies are found, it offers to automatically run `playlist sync --skip-lastfm` for the affected collections only, ensuring your catalog is perfectly aligned.

```bash
vibemus playlist list
vibemus pl ls
```

---

#### `vibemus playlist sync [--name PL] [--skip-lastfm] [--no-covers]`
**Alias:** `vibemus pl sy ...`
Reconcile one or all source playlists against your `Songs` sheet.

- Updates scrobble counts, like status, and metadata.
- Moves **liked songs** to the artist's target playlist (from `#` only).
  - *Si el destino final de la canción es una playlist de archivo (fuera de SOURCE_PLAYLISTS), automáticamente le quitará el Like en YouTube.*
  - *Si además la canción tiene muy pocas reproducciones (<= 1 scrobble por defecto), la enviará también a la lista reservada **Pendiente**.*
- Archives **disliked songs** (from any playlist).
- **`--name PL`**: Limits the sync to a single named playlist (e.g. `vibemus pl sy --name "#"`).
- **`--skip-lastfm`**: Skips Last.fm enrichment for a much faster run.
- **`--no-covers`**: Skips the playlist cover generation/reordering phase.
- **🛡️ Data Safety**: If a song is present in the `Songs` sheet but cannot be found in the corresponding YouTube playlist, the system considers it "Missing from YouTube" and moves it to the `Archived` sheet to keep your catalog clean without losing metadata.

**Examples:**
```bash
vibemus pl sy
vibemus pl sy --name "Indie" --skip-lastfm
vibemus pl sy --no-covers
```

---

#### `vibemus playlist cleanup-inbox`
**Alias:** `vibemus pl ci`
Remove songs from the `#` inbox that are already present in other curated playlists in the sheet.

---

#### `vibemus playlist cleanup-likes`
**Alias:** `vibemus pl cul`
Batch removal of 'Like' status for songs that have been moved to archive playlists to clean up your YouTube Music algorithm.

---

#### `vibemus playlist clean`
**Alias:** `vibemus pl cl`
Remove songs from YouTube playlists that are no longer present in the 'Songs' sheet.

---

#### `vibemus playlist export [playlist_id]`
**Alias:** `vibemus pl ex ...`
Export the contents of a YouTube playlist to a new sheet page. Defaults to the current target playlist if no ID is provided.

**Example:**
```bash
vibemus pl ex "PL2_CnmTx8Xf..."
```

---

#### `vibemus playlist review-pending [threshold] [--skip-lastfm]`
**Alias:** `vibemus pl rp [threshold] [--skip-lastfm]`
**Bandeja de revisión de biblioteca antigua** — localiza canciones "olvidadas" para decidir si mantenerlas o eliminarlas.

- **Threshold**: Límite máximo de reproducciones para incluir en la lista (default: **2**).
- **`--skip-lastfm`**: No actualiza el contador de scrobbles desde la API (más rápido, útil para mantenimiento manual).

**Examples:**
```bash
vibemus pl rp      # threshold = 2
vibemus pl rp 0    # solo canciones nunca escuchadas
vibemus pl rp 5 --skip-lastfm  # mantenimiento rápido
```

---

#### `vibemus playlist split --name "Playlist" --parts N`
**Alias:** `vibemus pl sp ...`
Divide una colección (playlist principal y sus archivos) en **N partes aproximadamente iguales** basadas en el año de lanzamiento.

- **Diferencial**: El sistema analiza la densidad de canciones en toda tu base de datos para proponer cortes cronológicos inteligentes.
- **Doble Verificación**: Al finalizar, ejecuta un motor de consistencia que asegura que cada canción esté en el "cubo" temporal correcto según su metadato de año.
- **Higiene de Playlists**: Borra automáticamente listas vacías y obsoletas tras los movimientos.

```bash
# Divide la colección "Rock" en 3 bloques temporales equilibrados
vibemus pl sp --name "Rock" --parts 3
```

---

#### `vibemus playlist apply-moves [--artist NAME] [--playlist NAME] [--refresh-cache] [--api {lastfm,musicbrainz}]`
**Alias:** `vibemus pl am ...`
Sync manual changes made to the "Playlist" column in your Google Sheet back to YouTube Music.

- Scans the **Songs** sheet for songs whose playlist name differs from YouTube.
- Automatically **removes** the song from the old playlist and **adds** it to the new one.
- Ignores changes to/from the `#` playlist.
- **`--artist NAME`**: Process only moves for a specific artist.
- **`--playlist NAME`**: Process only moves where the target playlist in the sheet matches this name (e.g., "Crank Wave").
- **`--refresh-cache`**: Forces a fresh download of playlist data from YouTube before starting. Recommended if you have made manual changes on the YouTube Music app.
- **`--api {lastfm,musicbrainz}`**: Choose the metadata provider for genres and artist info (default: `lastfm`).

**Examples:**
```bash
vibemus pl am
vibemus pl am --artist "The Drums"
vibemus pl am --refresh-cache
vibemus pl am --playlist "Pop" --api musicbrainz
```

> [!IMPORTANT]
> **Manual Changes on YouTube:** If you've been moving songs using the YouTube Music app, the local cache will be outdated. **Always use `--refresh-cache`** to ensure `apply-moves` sees the current state of your playlists, otherwise it might skip moves thinking they are already "in sync".

---




---



---



---

### `youtube` — Regular YouTube Operations (Data API v3)

Este módulo interactúa con la plataforma estándar de YouTube (no solo Music) para automatizar la gestión de nuevas publicaciones de canales a los que estás suscrito.

---

#### `vibemus youtube sync-subs [--reset] [--cleanup]`
**Alias:** `vibemus yt ss ...`
Sincroniza los nuevos vídeos publicados en tus canales suscritos de YouTube en **4 fases optimizadas de cuota**:

| Fase | Qué hace | Coste API |
|:---|:---|:---|
| **1 — Candidatos** | Obtiene los últimos vídeos de cada canal desde el checkpoint | 1 u/canal |
| **2 — Filtrado global** | Descarta Shorts y selecciona el vídeo más largo por canal | 1 u/50 vídeos |
| **3 — Inserción** | Añade los ganadores a "📥 Para Ver" + registra historial por canal | 50 u/vídeo |
| **4 — Top canales** ⭐ | Añade hasta 3 vídeos extra de los 5 canales más activos (ventana 7d) | ~1–10 u/canal |

- **Playlist Automática**: Los vídeos se añaden a una lista privada llamada **"! 📥 Para Ver"** (comienza con `!` para aparecer la primera en orden alfabético — alternativa funcional al "Ver más tarde" del sistema, que está bloqueado por la API).
- **Mismo día — modo acumulativo**: Si `sync-subs` se ejecuta más de una vez en el mismo día (UTC), **no borra ni recrea** la playlist; simplemente añade los vídeos nuevos encima de los existentes.
- **Filtro de Shorts**: Los vídeos de duración ≤ 60s o etiquetados con `#shorts` son ignorados automáticamente.
- **Checkpoint incremental**: Solo procesa vídeos publicados desde la última ejecución (guardado en `data/youtube_subs_sync.json`).
- **Historial por canal**: Cada inserción exitosa anota el canal en `channel_history` (auto-purgado a 90 días) para alimentar el ranking de top canales.
- **Fase 4 activa solo si existe** `data/youtube_top_channels_cache.json` — genéralo con `update-top-channels`.
- **Control de inactividad**: Identifica canales que no han publicado nada en 3 meses.
- **`--reset`**: Ignora el checkpoint y escanea las últimas 24 horas.
- **`--cleanup`**: Activa el modo interactivo para cancelar suscripciones de canales inactivos (> 3 meses).

```bash
vibemus youtube sync-subs
vibemus yt ss --reset
```

> [!TIP]
> La **Fase 4 (top canales) está desactivada por defecto**. Para activarla, ejecuta primero varios `sync-subs` para acumular historial y luego corre `vibemus youtube update-top-channels`.

---

#### `vibemus youtube update-top-channels [--window DAYS] [--top N] [--interactive]`
**Alias:** `vibemus yt utc ...`
Calcula y persiste el ranking de los canales más frecuentemente añadidos.

- **`--window DAYS`**: Ventana de días hacia atrás para el ranking (default: `7`).
- **`--top N`**: Cuántos canales guardar en el caché (default: `5`).
- **`--interactive` (`-i`)**: Permite elegir manualmente los canales del top desde una lista.

**Examples:**
```bash
vibemus yt utc
vibemus yt utc --window 30 --top 10
vibemus yt utc --interactive
```

**Flujo recomendado (primera vez):**
```bash
# 1. Ejecuta el sync normal para acumular historial de adiciones
vibemus youtube sync-subs

# 2. Genera el cache del top-5 (una vez, o cuando quieras actualizar el ranking)
vibemus youtube update-top-channels

# O gestiónalo interactivamente para añadir/quitar canales a mano
vibemus youtube update-top-channels --interactive

# 3. A partir de ahora el sync diario incluye la Fase 4 automáticamente
vibemus youtube sync-subs
```

> [!NOTE]
> El campo `channel_history` dentro de `data/youtube_subs_sync.json` registra cada inserción exitosa por canal con su fecha UTC. Las entradas anteriores a 90 días se purgan automáticamente para mantener el tamaño del fichero bajo control.

---



#### `vibemus youtube cleanup-shorts`
**Alias:** `vibemus yt cs`
Escanea la playlist **"📥 Para Ver"** y elimina cualquier vídeo de formato corto (Shorts) que se haya añadido anteriormente.

```bash
vibemus yt cs
```

---

#### `vibemus youtube cleanup-watched`
**Alias:** `vibemus yt cw`
Escanea la playlist **"📥 Para Ver"** y elimina los vídeos que aparezcan en tus últimos 200 elementos del historial de reproducciones. (Este proceso se ejecuta automáticamente al inicio de `sync-subs`).

```bash
vibemus yt cw
```

---

### `system` — Utilities

#### `vibemus system reset`
**Alias:** `vibemus sys rs`
Clear the main playlist and reset history. **Requires typing `yes` to confirm.**

```bash
vibemus system reset
vibemus sys rs
```

---

#### `vibemus system refresh-cache`
**Alias:** `vibemus sys rc`
Force a full refresh of the local source playlist cache (`data/source_cache.json`).

```bash
vibemus system refresh-cache
vibemus sys rc
```

---

#### `vibemus system auth`
**Alias:** `vibemus sys au`
Launch the `grab_cookies.js` browser authentication helper. Run this if Vibemus reports that your session has expired.

```bash
vibemus system auth
vibemus sys au
```

---

## Legacy Commands

| Old command | New command |
|-------------|-------------|
| `--add-artist "X"` | `vibemus artist add "X"` |
| `--remove-artist "X"` | `vibemus artist remove "X"` |
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
