# 🌌 Vibemus

**Automatización de YouTube Music** — rastrea artistas, descubre nuevos lanzamientos, sincroniza playlists y mantén una biblioteca musical completa respaldada por Google Sheets y Last.fm.

---

## Tabla de Contenidos

1. [Requisitos](#requisitos)
2. [Instalación](#instalación)
3. [Autenticación](#autenticación)
4. [Configuración](#configuración)
5. [💡 Lógica de Sincronización y Guía de Estados](#-lógica-de-sincronización-y-guía-de-estados)
   - [🔄 Comparativa de Comandos de Sync](#-comparativa-de-comandos-de-sync)
6. [Referencia de la CLI](#referencia-de-la-cli)
   - [artist](#artist--gestión-de-artistas-seguidos)
   - [releases](#releases--monitoreo-de-lanzamientos)
   - [recom](#recom--recomendaciones-personalizadas)
   - [genre](#genre--gestión-de-taxonomía-de-géneros)
   - [library](#library--sincronización-de-biblioteca-de-youtube-music)
   - [playlist](#playlist--operaciones-de-playlists)
   - [system](#system--utilidades)
7. [Comandos Legados](#comandos-legados)
8. [Estructura del Proyecto](#estructura-del-proyecto)

---

## ⌨️ Atajos de Comandos (Shortcuts)

Para ahorrar escritura, puedes usar los siguientes alias para grupos de comandos y acciones:

| Categoría | Alias de Grupo | Acciones |
|:---|:---|:---|
| **Artist** | `art` | `ls` (list), `sh` (search), `ad` (add), `rm` (remove), `cc` (cleanup-collabs), `sy` (sync), `im` (import), `re` (reset-empty), `ai` (archive-inactive) |
| **Releases** | `rel` | `sy` (sync) |
| **Playlist** | `pl` | `ls` (list), `sy` (sync), `ci` (cleanup-inbox), `cl` (clean), `ex` (export), `cul` (cleanup-likes), `am` (apply-moves), `sp` (split), `rp` (review-pending) |
| **Library** | `lib` | `sy` (sync) |
| **Recom** | `rec` | `sy` (sync), `ny` (new-releases) |
| **Genre** | `gen` | `sy` (sync) |
| **YouTube** | `yt` | `ss` (sync-subs), `cs` (cleanup-shorts), `cw` (cleanup-watched), `utc` (update-top-channels) |
| **System** | `sys` | `rc` (refresh-cache), `au` (auth) |

**Ejemplos:**
```bash
# Full version
vibemus artist list
vibemus playlist sync --name "#"

# Shortcut version
vibemus art ls
vibemus pl sy --name "#"
```

---

## ⚡ Guía de Referencia Rápida

| Categoría | Comando (Corto) | Descripción |
|:---|:---|:---|
| **Descubrimiento** | `rel sy` | Escanea el perfil de cada artista seguido (Monitorización completa). |
| | `rec ny` | Escanea nuevos lanzamientos recomendados de Last.fm (Out Now). |
| | `rec sy` | Descubre nuevos artistas basados en tus recomendaciones de Last.fm. |
| **Artista** | `art ad "Nombre"` | Empieza a seguir a un artista y sincroniza su discografía. |
| | `art sy` | Añade artistas que faltan en tu biblioteca a la lista de seguimiento. |
| | `art ls` | Muestra todos los artistas seguidos actualmente y su estado. |
| **Playlist** | `pl sy [--name PL]` | Consolida el inbox, mueve likes y archiva dislikes. |
| | `pl ls` | Compara el número de canciones entre YT y Google Sheets. |
| | `pl am [--refresh-cache]` | Sincroniza cambios manuales de playlists de Sheets a YouTube. |
| | `pl rp [N]` | Revisa canciones poco escuchadas en una bandeja dedicada. |
| **Mantenimiento** | `lib sy` | Añade canciones de playlists a la biblioteca / elimina huérfanas. |
| | `pl ci` | Elimina canciones de '#' que ya están organizadas. |
| | `pl sp --name PL --parts N` | Divide archivos en bloques basados en el año. |
| **YouTube** | `yt ss [--reset]` | Sincroniza nuevos vídeos de suscripciones a '📥 Para Ver'. |
| | `yt utc` | Recalcula y guarda el caché de los canales top más activos. |
| **Sistema** | `sys au` | Refresca la autenticación de la cuenta de YouTube Music. |
| | `sys rc` | Fuerza la actualización del caché local de metadatos de playlists. |

---

## Requisitos

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ (for cookie auth) |
| Google Chrome | Latest |

Herramientas y dependencias de Python (ver `requirements.txt`):
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

## Instalación

```bash
git clone <repo>
cd Vibemus
pip install -r requirements.txt
npm install            # instala puppeteer para grab_cookies.js
```

### Hacer el comando `vibemus` disponible globalmente

```bash
echo "alias vibemus='python3 $(pwd)/main.py'" >> ~/.zshrc && source ~/.zshrc
```

---

## Autenticación

Vibemus necesita cuatro archivos de credenciales dentro del directorio `config/`:

| Archivo | Propósito |
|------|---------|
| `config/oauth.json` | YouTube Music OAuth (ytmusicapi) |
| `config/browser.json` | Cookies del navegador de YouTube Music |
| `config/service_account.json` | Cuenta de servicio para la API de Google Sheets |
| `config/youtube_client_secrets.json` | YouTube Data API v3 OAuth secrets |

### Obtención de cookies de YouTube Music

Ejecuta el asistente interactivo de autenticación:

```bash
node grab_cookies.js
# or via CLI:
vibemus system auth
```

Esto abrirá una ventana aislada de Chrome. Inicia sesión en YouTube Music y luego cierra la ventana. Las cookies se guardarán automáticamente en `config/browser.json`.

### Configuración de Google Sheets

 1. Crea una **Cuenta de Servicio** en [Google Cloud Console](https://console.cloud.google.com/).
 2. Descarga la clave JSON y guárdala como `config/service_account.json`.
 3. Comparte tu Google Sheet con el email de la cuenta de servicio.
 4. Asegúrate de que la hoja de cálculo se llame **`YouTube Music Vibemus`** (o cambia `SPREADSHEET_TITLE` en `src/config.py`).

### Configuración de la API de YouTube Data (Sincronización de Suscripciones)

 1. Ve a [Google Cloud Console](https://console.cloud.google.com/).
 2. Habilita **YouTube Data API v3**.
 3. Crea un **ID de cliente de OAuth 2.0** como **Aplicación de escritorio**.
 4. Descarga el JSON y guárdalo como `config/youtube_client_secrets.json`.
 5. Ejecuta `vibemus youtube sync-subs` para autorizar (abre el navegador una vez).

---

## Configuración

Ajustes clave en `src/config.py`: 

| Ajuste | Por defecto | Descripción |
|---------|---------|-------------|
| `PLAYLIST_ID` | `PL2_CnmTx…` | Tu playlist principal de entrada (`#`) |
| `SOURCE_PLAYLISTS` | `["#", "Indie Pop", …]` | Playlists escaneadas al organizar artistas |
| `LASTFM_USERNAME` | `amartelr` | Cuenta de Last.fm para enriquecimiento de scrobbles |
| `SCROBBLE_THRESHOLD` | `13` | Mínimo de scrobbles para conservar una canción |
| `SYNC_DELAY` | `2` | Segundos entre llamadas a la API en operaciones por lotes |

---

## Sistema de Caché

Vibemus utiliza cachés locales en formato JSON en el directorio `data/` para optimizar el rendimiento y respetar los límites de la API.

### 1. Caché de Last.fm (`lastfm_cache.json`)
*   **Propósito**: Almacena metadatos de pistas (géneros/etiquetas) y recuento de scrobbles.
*   **Validez (TTL)**: **7 días**. Los datos frescos se reutilizan automáticamente.
*   **⚡ Refresco Condicional**: En `playlist sync`, las canciones en **SOURCE_PLAYLISTS** con **menos de 4 scrobbles** siempre disparan una búsqueda directa en la API de Last.fm (ignora el caché). Los archivos y otras listas usan el TTL estándar.
*   **Fallback**: Se pueden usar datos antiguos si la API no está disponible, a menos que se fuerce el refresco vía `apply-moves`.

### 2. Caché de Playlists de Origen (`source_cache.json`)
*   **Propósito**: Copia local de tus playlists "origen" (Inbox, listas de género) para acelerar las tareas de organización.
*   **Validez**: **Manual/Proactiva**. No expira por tiempo.
*   **Actualizaciones**: Se refresca vía `vibemus system refresh-cache` o `--refresh-cache`. Se actualiza proactivamente (se eliminan items) cuando las canciones se mueven con éxito.
*   **⚠️ Aviso de Caché Obsoleto**: Si eliminas o mueves canciones manualmente usando la app de YouTube Music, el caché local estará desincronizado. `apply-moves` podría informar que las canciones están "Sincronizadas" cuando en realidad faltan en YouTube. Usa siempre `--refresh-cache` si has hecho cambios manuales recientemente.


### 4. Caché de MusicBrainz (`musicbrainz_cache.json`)
*   **Propósito**: Almacena etiquetas de artistas y pistas obtenidas de MusicBrainz.
*   **Validez**: **30 días** para info de artistas, **7 días** para info de pistas. Ayuda a respetar el límite estricto de 1 req/s.

### 5. Preferencias de Géneros (`genre_preferences.json`)
*   **Propósito**: Almacena tus listas de géneros "Aprobados" e "Ignorados" para el comando `sync genre`.
*   **Uso**: Evita el desorden de etiquetas geográficas (ej. "British") o términos genéricos.
*   **Interactividad**: Los nuevos géneros encontrados durante el sync activarán un prompt para añadirlos a cualquiera de las dos listas.

---

## 💡 Lógica de Sincronización y Guía de Estados

Vibemus utiliza un **sistema de filtrado de doble capa** para optimizar las operaciones de descubrimiento y respetar los límites de la API.

### Lógica de Sync de Artistas
Vibemus utiliza el comando `releases sync` para monitorear a tus artistas. Comprueba nuevos lanzamientos y actualiza la fecha de 'Última comprobación' en tu hoja de cálculo.

### Significado de los Estados del Artista
- **`Pending`**: Nuevo artista esperando escaneo.
- **`Done`**: Exploración finalizada. El sistema ha escaneado con éxito su discografía y añadido las canciones elegidas.
- **`Archived`**: Has decidido dejar de seguir a este artista. No aparecerán en ningún comando de sync.

---

### 🔄 Comparativa de Comandos de Sync
Vibemus ofrece tres formas diferentes de descubrir y sincronizar música. Usa esta tabla para elegir el comando adecuado según tus necesidades:

| Comando | Frecuencia | Método de Escaneo | Alcance | Ideal para... |
|:---|:---|:---|:---|:---|
| **`recom new-releases`** | **Diario** | Lanzamientos Recomendados de Last.fm | Últimos singles/álbumes de artistas que sigues (y otros) | ⚡ Escaneo rápido de novedades. |
| **`releases sync`** | **Semanal** | Perfiles individuales de artistas | Cada nuevo single/álbum de tu lista | 🎯 Monitoreo completo de tus artistas específicos. |

> [!TIP]
> **Sugerencia de Flujo de Trabajo**: Usa `recom new-releases` diariamente para captar los grandes lanzamientos al instante. Ejecuta `releases sync` una vez a la semana para asegurar que no se pasó nada por alto.

---

---

## Referencia de la CLI

```
vibemus <group> <action> [options]
```

---

### `artist` — Gestión de Artistas Seguidos
**Alias:** `art`

Añade, elimina, enumera y mantén a tus artistas seguidos en Google Sheets.

---

#### `vibemus artist list`
**Alias:** `vibemus art ls`

Muestra todos los artistas seguidos actualmente y su estado (Pending, Done, Archived).

**Ejemplos:**
```bash
vibemus artist list
vibemus art ls
```

#### `vibemus artist search "Query"`
**Alias:** `vibemus art sh ...`

Busca un artista en YouTube Music para obtener su ID y metadatos antes de añadirlo, o busca un artista que ya esté en tu hoja de cálculo.

**Ejemplos:**
```bash
# Versión completa
vibemus artist search "Arctic Monkeys"

# Versión corta
vibemus art sh "Arctic Monkeys"
```

---

#### `vibemus artist add ["Name"] [--playlist "Genre"] [--api {lastfm,musicbrainz}]`
**Alias:** `vibemus art ad ...`

Busca en YouTube Music y empieza a seguir a un artista.

**Argumentos:**
- `--playlist PL`: Asigna la playlist de destino en la hoja 'Artists' y migra inmediatamente las canciones existentes en la biblioteca a esa playlist.
- `--api {lastfm,musicbrainz}`: Proveedor de metadatos para el descubrimiento inicial de la discografía (por defecto: `lastfm`).

**Ejemplos:**
```bash
# Adición básica
vibemus artist add "Radiohead"
vibemus art ad "Radiohead"

# Añadir con playlist específica y API
vibemus artist add "Hax!" --playlist "Emo" --api lastfm
vibemus art ad "The Smile" --playlist "Art Rock" --api musicbrainz
```

---

#### `vibemus artist remove "Name"`
**Alias:** `vibemus art rm ...`

Deja de seguir a un artista y limpia sus datos en la hoja.

**Ejemplos:**
```bash
vibemus artist remove "Band of Horses"
vibemus art rm "Band of Horses"
```

---

#### `vibemus artist sync`
**Alias:** `vibemus art sy`

Sincroniza tu lista de seguimiento de **Artistas** basada en tu catálogo de **Canciones** existente (excluyendo canciones en el Inbox).

- **Descubrimiento**: Identifica automáticamente artistas presentes en tu hoja 'Songs' que aún no están siendo seguidos.
- **Incorporación**: Pregunta interactivamente por una playlist por defecto para cada nuevo artista encontrado.
- **Limpieza**: Actualiza el `Song Count` para todos los artistas basándose en el número total de entradas en la hoja de cálculo.

**Ejemplos:**
```bash
vibemus artist sync
vibemus art sy
```

---

#### `vibemus artist import`
**Alias:** `vibemus art im`

Importa artistas directamente desde tu biblioteca de YouTube basándose en el número de pistas que tienes de cada uno.

**Ejemplos:**
```bash
vibemus artist import
vibemus art im
```

---

#### `vibemus artist reset-empty`
**Alias:** `vibemus art re`

Restablece el estado 'Last Checked' para artistas con 0 pistas. Útil para reintentar un escaneo inicial fallido.

**Ejemplos:**
```bash
vibemus artist reset-empty
vibemus art re
```

---

#### `vibemus artist archive-inactive`
**Alias:** `vibemus art ai`

Identifica y archiva artistas que no han lanzado nada o no han sido escuchados en años.

**Ejemplos:**
```bash
vibemus artist archive-inactive
vibemus art ai
```

---

#### `vibemus artist cleanup-collabs`
**Alias:** `vibemus art cc`

Limpieza interactiva de nombres de artistas colaborativos para asegurar que están mapeados correctamente a entidades seguidas primarias.

**Ejemplos:**
```bash
vibemus artist cleanup-collabs
vibemus art cc
```

---

### `releases` — Monitoreo de Lanzamientos

---

#### `vibemus releases sync [--force] [--auto] [--liked-only]`
**Alias:** `vibemus rel sy ...`
Escanea nuevos álbumes y singles de **todos los artistas seguidos**.

- **Escaneo Dirigido**: Visita directamente el perfil de cada artista en tu hoja 'Artists'.
- **Filtrado**: Excluye automáticamente canciones que ya están en tu biblioteca o archivo.
- **Metadatos**: Muestra el recuento de scrobbles de Last.fm directamente en el prompt: `[Oyentes🎧 | Tus Reproducciones👤]`.
- `--force`: Vuelve a escanear a todos los artistas aunque hayan sido comprobados recientemente (ignora la ventana de 24h).
- `--auto`: Omite los prompts interactivos y añade todas las canciones encontradas a la playlist `#`.
- `--liked-only`: Solo comprueba artistas que tengan al menos una canción en tu colección de "Me gusta".

**Ejemplos:**
```bash
vibemus rel sy
vibemus rel sy --force --auto
vibemus rel sy --liked-only
```

### `recom` — Recomendaciones Personalizadas
**Alias:** `rec`

---

#### `vibemus recom sync [--auto]`
**Alias:** `vibemus rec sy ...`
Escanea recomendaciones personalizadas de artistas desde Last.fm y ofrece seguirlos.

- **Descubrimiento**: Utiliza tu historial de escucha de Last.fm para encontrar artistas que te podrían gustar.
- **Incorporación**: Para cada artista recomendado, muestra géneros y oyentes, y ofrece añadirlo a tu lista de seguimiento o **escucharlo** (`[o]ír`) abriendo su perfil en YouTube Music.
- `--auto`: Añade automáticamente las 2 canciones más nuevas y las 2 más populares para cada artista recomendado.

**Ejemplos:**
```bash
vibemus rec sy
vibemus rec sy --auto
```

---

#### `vibemus recom new-releases [--auto] [--tracked-only]`
**Alias:** `vibemus rec ny ...`
Escanea la sección de **Nuevos Lanzamientos Recomendados** (Out Now) de Last.fm.

- **Personalizado**: Muestra nuevos lanzamientos de artistas que ya sigues y otros que Last.fm cree que te gustarán.
- **Filtrado Inteligente**: 
    - **Artistas Seguidos**: Marcados con `★`. Se muestran para tu información y se marcan como "vistos" automáticamente.
    - **Nuevos Artistas**: Te pide añadirlos a tu lista de seguimiento si te gusta el lanzamiento o **escucharlo** (`[o]ír`) abriendo la búsqueda en YouTube Music.
- `--tracked-only`: Omite artistas desconocidos y solo muestra lanzamientos de artistas que ya están en tu catálogo.
- `--auto`: Añade automáticamente artistas desconocidos al seguimiento.

**Ejemplos:**
```bash
vibemus rec ny
vibemus rec ny --tracked-only
```

---

### `genre` — Gestión de Taxonomía de Géneros
**Alias:** `gen`

Categorize and audit your artists by genre in the Google Sheet.

---

#### `vibemus genre sync`
**Alias:** `vibemus gen sy`

Actualiza la hoja de resumen de **Géneros** en tu Google Spreadsheet.

- **Filtrado Interactivo**: Si detecta un género que no está en tus listas de "Aprobados" o "Ignorados", te pedirá una decisión.
- **Normalización**: Aplica automáticamente **Title Case** y divide cadenas multi-género.

**Ejemplos:**
```bash
vibemus genre sync
vibemus gen sy
```

---

### `library` — Sincronización de Biblioteca de YouTube Music
**Alias:** `lib`

Sincroniza tu biblioteca de YouTube Music con tus playlists.

---

#### `vibemus library sync`
**Alias:** `vibemus lib sy`

Sincronización bidireccional entre tu biblioteca de YouTube Music y tus playlists curadas.

- **📥 AÑADIR**: Se añaden las canciones que están en playlists (excluyendo `#`) pero NO en tu biblioteca.
- **📤 ELIMINAR**: Se eliminan las canciones que están en tu biblioteca pero NO en ninguna playlist (y no tienen "Me gusta").

**Ejemplos:**
```bash
vibemus library sync
vibemus lib sy
```

> [!TIP]
Ejecuta esto después de `playlist sync` o `apply-moves` para asegurar que tu biblioteca de YouTube Music esté totalmente sincronizada con tus playlists curadas.

---

### `playlist` — Operaciones de Playlists
**Alias:** `pl`

Limpia, exporta y procesa playlists.

---

#### `vibemus playlist list`
**Alias:** `vibemus pl ls`

Muestra una tabla comparativa de todas tus playlists (incluyendo archivos históricos), contrastando el recuento total de canciones en **YouTube Music** frente a tu **Google Sheet (Songs)**.

**Ejemplos:**
```bash
vibemus playlist list
vibemus pl ls
```

---

#### `vibemus playlist sync [--name PL] [--skip-lastfm] [--no-covers]`
**Alias:** `vibemus pl sy ...`

Concilia una o todas las playlists de origen con tu hoja 'Songs'.

**Argumentos:**
- `--name PL`: Limita la sincronización a una sola playlist específica (ej. `vibemus pl sy --name "#"`).
- `--skip-lastfm`: Omite el enriquecimiento de Last.fm para una ejecución mucho más rápida.
- `--no-covers`: Omite la fase de generación/reordenación de portadas de playlists.

**Ejemplos:**
```bash
# Sincronizar todas las playlists de origen
vibemus playlist sync
vibemus pl sy

# Sincronizar una playlist específica omitiendo enriquecimiento
vibemus playlist sync --name "Indie" --skip-lastfm
vibemus pl sy --name "Indie" --skip-lastfm

# Sincronizar sin actualizar portadas
vibemus playlist sync --no-covers
vibemus pl sy --no-covers
```

---

#### `vibemus playlist cleanup-inbox`
**Alias:** `vibemus pl ci`

Elimina canciones del inbox `#` que ya están presentes en otras playlists curadas en la hoja.

**Ejemplos:**
```bash
vibemus playlist cleanup-inbox
vibemus pl ci
```

---

#### `vibemus playlist cleanup-likes`
**Alias:** `vibemus pl cul`

Eliminación masiva del estado 'Me gusta' para canciones que han sido movidas a playlists de archivo para limpiar tu algoritmo de YouTube Music.

**Ejemplos:**
```bash
vibemus playlist cleanup-likes
vibemus pl cul
```

---

#### `vibemus playlist clean`
**Alias:** `vibemus pl cl`

Elimina canciones de las playlists de YouTube que ya no están presentes en la hoja 'Songs'.

**Ejemplos:**
```bash
vibemus playlist clean
vibemus pl cl
```

---

---

#### `vibemus playlist export [playlist_id]`
**Alias:** `vibemus pl ex ...`

Exporta el contenido de una playlist de YouTube a una nueva hoja. Por defecto usa la playlist de destino actual si no se proporciona un ID.

**Ejemplos:**
```bash
vibemus playlist export "PL2_CnmTx8Xf..."
vibemus pl ex "PL2_CnmTx8Xf..."
```

---

#### `vibemus playlist review-pending [threshold] [--skip-lastfm]`
**Alias:** `vibemus pl rp [threshold] [--skip-lastfm]`

**Bandeja de revisión de biblioteca antigua** — localiza canciones "olvidadas" para decidir si mantenerlas o eliminarlas.

**Argumentos:**
- `threshold`: Límite máximo de reproducciones para incluir en la lista (default: **2**).
- `--skip-lastfm`: No actualiza el contador de scrobbles desde la API.

**Ejemplos:**
```bash
# Threshold = 2
vibemus playlist review-pending
vibemus pl rp

# Solo canciones nunca escuchadas
vibemus playlist review-pending 0
vibemus pl rp 0

# Mantenimiento rápido con threshold 5
vibemus playlist review-pending 5 --skip-lastfm
vibemus pl rp 5 --skip-lastfm
```

---

#### `vibemus playlist split --name "Playlist" --parts N`
**Alias:** `vibemus pl sp ...`

Divide una colección en **N partes aproximadamente iguales** basadas en el año de lanzamiento.

**Argumentos:**
- `--name PL`: Playlist base a dividir (ej. 'Pop').
- `--parts N`: Divide toda la colección en N partes aproximadamente iguales.

**Ejemplos:**
```bash
vibemus playlist split --name "Rock" --parts 3
vibemus pl sp --name "Rock" --parts 3
```

---

#### `vibemus playlist apply-moves [--artist NAME] [--playlist NAME] [--refresh-cache] [--api {lastfm,musicbrainz}]`
**Alias:** `vibemus pl am ...`

Sincroniza los cambios manuales realizados en la columna "Playlist" de tu Google Sheet de vuelta a YouTube Music.

**Argumentos:**
- `--artist NAME`: Procesa solo los movimientos para un artista específico.
- `--playlist NAME`: Procesa solo los movimientos donde la playlist de destino en la hoja coincide con este nombre.
- `--refresh-cache`: Fuerza una descarga fresca de los datos de las playlists desde YouTube antes de empezar.
- `--api {lastfm,musicbrainz}`: Elige el proveedor de metadatos (por defecto: `lastfm`).

**Ejemplos:**
```bash
# Sincronizar todos los movimientos
vibemus playlist apply-moves
vibemus pl am

# Sincronizar movimientos para un artista específico
vibemus playlist apply-moves --artist "The Drums"
vibemus pl am --artist "The Drums"

# Sincronizar movimientos a una playlist específica usando MusicBrainz
vibemus playlist apply-moves --playlist "Pop" --api musicbrainz
vibemus pl am --playlist "Pop" --api musicbrainz
```

> [!IMPORTANT]
> **Cambios manuales en YouTube**: Si has estado moviendo canciones usando la app de YouTube Music, el caché local estará obsoleto. **Usa siempre `--refresh-cache`** para asegurar que `apply-moves` vea el estado actual de tus playlists.

---

### `youtube` — Operaciones de YouTube
**Alias:** `yt`

Interactúa con la plataforma estándar de YouTube (no Music) para la gestión de suscripciones.

---

#### `vibemus youtube sync-subs [--reset] [--cleanup]`
**Alias:** `vibemus yt ss ...`

Sincroniza los nuevos vídeos publicados en tus canales suscritos en la playlist **"📥 Para Ver"**.

**Argumentos:**
- `--reset`: Ignora el checkpoint y escanea las últimas 24 horas.
- `--cleanup`: Activa el modo interactivo para cancelar suscripciones de canales inactivos (> 3 meses).

**Ejemplos:**
```bash
# Sincronizar nuevos vídeos
vibemus youtube sync-subs
vibemus yt ss

# Reiniciar y escanear las últimas 24h
vibemus youtube sync-subs --reset
vibemus yt ss --reset

# Limpieza de canales inactivos
vibemus youtube sync-subs --cleanup
vibemus yt ss --cleanup
```

---

#### `vibemus youtube update-top-channels [--window DAYS] [--top N] [--interactive]`
**Alias:** `vibemus yt utc ...`

Calcula y persiste el ranking de los canales más frecuentemente añadidos.

**Argumentos:**
- `--window DAYS`: Ventana de días hacia atrás para el ranking (default: `7`).
- `--top N`: Cuántos canales guardar en el caché (default: `5`).
- `--interactive` (`-i`): Gestionar los canales top interactivamente.

**Ejemplos:**
```bash
# Actualización por defecto (7 días, top 5)
vibemus youtube update-top-channels
vibemus yt utc

# Ventana personalizada y número de top
vibemus youtube update-top-channels --window 30 --top 10
vibemus yt utc --window 30 --top 10

# Modo interactivo
vibemus youtube update-top-channels --interactive
vibemus yt utc -i
```

---

#### `vibemus youtube cleanup-shorts`
**Alias:** `vibemus yt cs`

Eliminar vídeos cortos (Shorts) de la playlist "📥 Para Ver".

**Ejemplos:**
```bash
vibemus youtube cleanup-shorts
vibemus yt cs
```

---

#### `vibemus youtube cleanup-watched`
**Alias:** `vibemus yt cw`

Eliminar vídeos ya vistos de la playlist "📥 Para Ver".

**Ejemplos:**
```bash
vibemus youtube cleanup-watched
vibemus yt cw
```

---

### `system` — Utilidades
**Alias:** `sys`

Caché, reinicio y asistente de autenticación.

---

#### `vibemus system refresh-cache`
**Alias:** `vibemus sys rc`

Fuerza un refresco completo del caché local de playlists de origen (`data/source_cache.json`).

**Ejemplos:**
```bash
vibemus system refresh-cache
vibemus sys rc
```

---

#### `vibemus system auth`
**Alias:** `vibemus sys au`

Lanza el asistente de autenticación del navegador `grab_cookies.js`. Ejecuta esto si Vibemus informa que tu sesión ha expirado.

**Ejemplos:**
```bash
vibemus system auth
vibemus sys au
```

---

#### `vibemus system reset`
**Alias:** `vibemus sys rs`

Limpia la playlist principal y reinicia el historial. **Requiere escribir `yes` para confirmar.**

**Ejemplos:**
```bash
vibemus system reset
vibemus sys rs
```

---

---

## Comandos Legados

| Comando antiguo | Nuevo comando |
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

## Estructura del Proyecto

```
Vibemus/
├── main.py                  # Punto de entrada — despachador de CLI ligero
├── grab_cookies.js          # Asistente de auth por navegador (Node.js + Puppeteer)
├── requirements.txt
├── package.json
├── config/                  # Credenciales (ignorado por git)
│   ├── oauth.json
│   ├── browser.json
│   └── service_account.json
├── data/                    # Cachés locales (ignorado por git)
│   ├── source_cache.json
│   ├── lastfm_cache.json
│   └── genre_preferences.json # Tus listas de géneros aprobados/ignorados
├── src/
│   ├── config.py            # Ajustes generales de la aplicación
│   ├── cli/
│   │   ├── parser.py        # Analizador de argumentos (subcomandos + alias legados)
│   │   └── commands.py      # Funciones manejadoras por subcomando
│   ├── core/
│   │   └── manager.py       # Lógica central de negocio
│   └── services/
│       ├── yt_service.py    # Wrapper de la API de YouTube Music
│       ├── sheets_service.py # Wrapper de la API de Google Sheets
│       └── lastfm_service.py # Wrapper de la API de Last.fm
└── tests/
    └── test_cli_parser.py   # Pruebas unitarias del parser de CLI (35 tests)
```
