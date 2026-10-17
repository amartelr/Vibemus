# Vibemus

Un único proyecto con dos mitades que comparten la misma hoja de Google Sheets ("YouTube Music Vibemus"):
- **Biblioteca (CLI)**: mantiene playlists, artistas, scrobbles y archivo en la hoja (`vibemus ...`).
- **Dashboard web** (antes el proyecto `mysongs`): armonía de las canciones, guías de improvisación, mástil y práctica de acordes (`vibemus web`).

## STACK & ARQUITECTURA
- Python 3.x | SOLID principles
- Last.fm API + YouTube API + Google Sheets API
- CLI: `main.py` → `src/cli/` → `src/core/manager.py` → `src/services/`
- Web: `src/web/server.py` (Flask) + `web/` (JS vanilla sin build: `index.html`, `app.js`, `fretboard.js`, `style.css`)
- Autenticación de YouTube Music con `grab_cookies.js` (`vibemus system auth`)

## REGLAS CRÍTICAS
1. Respetar capas: nunca importar de adapters en core
2. Interfaces primero, adaptaciones después
3. Config centralizada en `config/` (secretos de la web en `config/web/`, todo ignorado por git)
4. Mantener servicios stateless
5. **Dos procesos escriben en la misma hoja.** Las columnas de Vibemus (Playlist…Video ID) son de la CLI; las del dashboard (Chord, Tonality, Progression, Complex, Style, LastScanned, Lyrics, bpm, Emotional, Skill, Improvisation, Voicings) y `Liked` son de la web. **`Liked` no es el favorito de YouTube Music**: es la marca "para ir tocando con la guitarra"; solo la modifica la web y la CLI nunca debe escribirla ni sincronizarla con los likes de YT. Una sincronización nunca debe pisarlas: `SheetsService._live_external_values()` relee la hoja justo antes de cada reescritura. Además, `_replace_rows` solo escribe las celdas que difieren y `src/services/sheet_lock.py` da un `flock` (`data/sheet.lock`) alrededor de cada lectura-escritura de ambos procesos; la web avisa si hay un comando de la CLI en curso (`/api/sheet-status`). Aun así, evita `vibemus pl sy` mientras escaneas armonías.
6. **LastScanned** se escribe al instante al pulsar "Autocompletar Armonía" (`recordScanDate()` en `web/app.js`), no al aceptar. Los guardados "solo fecha" envían únicamente `row/artist/title/lastScanDate`.

## COMANDOS
```bash
vibemus web                    # dashboard en http://localhost:8000 (--port N, --no-reload); alias: vibemus serve
./scripts/start_web.sh         # lo mismo, registrando en data/web.log
python3 scripts/recalculate_skills.py   # recalcula la dificultad de todas las canciones (--dry-run, --mode ug)
vibemus playlist sync --name "#"        # sincroniza una playlist (CLI)
```
Pruebas: `.venv/bin/python -m pytest scratch/test_sheets_live_overlay.py scratch/test_sheet_gateway.py scratch/test_sheet_lock.py scratch/test_web_endpoints.py`. No hay suite formal; la web se prueba a mano.

## ARCHIVOS CLAVE
- `src/core/` - Lógica pura (manager)
- `src/services/` - Sheets (`sheets_service.py`), YouTube Music, Last.fm, MusicBrainz
- `src/web/server.py` - rutas Flask (solo HTTP); la lógica vive en módulos hermanos: `harmony.py` (teoría: tonalidad, romanos, estilo, dificultad), `tabs.py`, `ultimate_guitar.py`, `songsterr.py`, `pdf_import.py`, `gemini.py` (guías), `bpm.py` (Deezer), `youtube.py` (OAuth + playlists), `paths.py` (rutas y .env)
- `web/app.js` - estado global, renderizado, llamadas a la API (hotspots: `applyFiltersAndRender`, `selectSong`, `handleAutodetect`, `showToast`)
- `web/fretboard.js` - teoría musical, mástil SVG, audio (Web Audio)
- `src/services/sheet_gateway.py` - única puerta de la web a la hoja (cuenta de servicio, escrituras solo de las celdas que cambian, localiza por Video ID / artista+título)
- `config/web/` - `client_secret.json`, `youtube_token.json` (OAuth solo para YouTube; la hoja usa `config/service_account.json` en CLI y web)
- `.env` - único para CLI y web (`src/config.py` y `src/web/paths.py` lo cargan): `GEMINI_API_KEY` (el servidor solo lo lee al arrancar); `config/keys.json` sigue teniendo prioridad para las claves de la CLI
- `main.py` - Entry point, `requirements.txt` - Deps

## DASHBOARD WEB: decisiones y trampas
- **Gemini para las guías, Claude solo para desarrollo.** Gemini gratis genera guías correctas (`POST /api/generate-improvisation`, `gemini-3-flash-preview` con otros Flash de respaldo). No migrar a Claude sin preguntar. Si hiciera falta: Sonnet 5.5 sin thinking (~2 céntimos/guía); Haiku 4.5 se descartó porque confunde mayúsculas/minúsculas de los números romanos (III como menor).
- **Nombres modales estrictos** (prompt en `server.py`): Mixolidio, Dórico, Lidia, Alterada, Blues + Cromatismos; formato "NOTA ESCALA" (p. ej. "E Mixolidio"). Rechazar nombres inventados como "Domancia".
- **Datos**: Google Sheets es la fuente de verdad (hojas `Songs` y `Archived`); `get_column_mapping()` hace coincidencia difusa de cabeceras, así que renombrar columnas sin actualizarla rompe lecturas. Las filas cambian de sitio cuando la CLI sincroniza: `/api/update` verifica artista/título y busca la fila correcta.
- **Autocompletar armonía** (Ultimate Guitar): `fetch_ug_chords` recorre hasta 3 páginas de búsqueda y ofrece todas las versiones (oficial + comunidad), ordenadas por si tienen letra y por popularidad; la interfaz indica "con letra / sin letra".
- **Acordes**: un solo nombre por tonalidad (`spellChordForKey`), almacenamiento canónico en sostenidos (`canonChordKey`). Los diagramas por defecto evitan cuerdas al aire y buscan formas cercanas (`voiceChordSequence`). La posición predeterminada tiene dos capas: global por acorde (localStorage, `setVoicingPref`) y por canción (columna `Voicings` de `Songs`/`Archived`, JSON `{acorde: trastes}`, `setSongVoicingPref`); la de la canción manda (`getEffectivePrefs`). La web crea la columna si falta; la CLI la conserva (`EXTERNAL_SONG_COLUMNS`).
- **Web Audio**: el primer gesto del usuario llama a `audioContext.resume()`; sin él falla en silencio.
- **LocalStorage**: las letras grandes pueden superar la cuota; validar antes de guardar.
- Repositorio anterior `mysongs` (`/Users/alfredomartel/dev/mysongs`): conservado solo como copia; su historial git contiene credenciales, por eso no se importó aquí.

## CÓMO USARME
- "Ayuda en [archivo].py" - sé específico
- "Refactor [función]" - no carguemos todo
- "Bug en [línea X]" - localiza el contexto
- Responder y preguntar siempre en español
