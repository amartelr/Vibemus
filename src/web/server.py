
from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS
from googleapiclient.errors import HttpError

from ..services.sheet_gateway import SongSheet, SongNotFound
from ..services.sheet_lock import SheetBusy, busy_info
from .paths import WEB_DIR
from .harmony import (clean_and_extract_chords, detect_key_from_chords, infer_complexity,
                      infer_emotional_style, infer_progression)
from .ultimate_guitar import fetch_ug_chords
from .songsterr import fetch_songsterr_chords
from .pdf_import import parse_chord_pdf
from .gemini import GeminiError, generate_guide
from .bpm import _lookup_bpm, _parse_bpm
from .audio_key import AudioKeyError, estimate_key
from .youtube import (YT_API_LINK, YouTubeAuthRequired, _is_embeddable, _score_video, _search_youtube,
                      get_youtube_service, replace_video_in_playlists, sync_song_in_playlists)

app = Flask(__name__, static_folder=WEB_DIR, static_url_path='')
CORS(app)

sheet = SongSheet()

@app.route('/api/sheet-status', methods=['GET'])
def sheet_status():
    """Whether a CLI command (e.g. a playlist sync) is running and may be rewriting the sheet."""
    info = busy_info()
    return jsonify({"busy": bool(info), "command": (info or {}).get("command", ""), "since": (info or {}).get("since", 0)})

@app.route('/')
def index():
    return send_from_directory(WEB_DIR, 'index.html')


@app.route('/api/songs', methods=['GET'])
def get_songs():
    try:
        headers, rows, col_map = sheet.read()
        if not rows:
            return jsonify({"error": "No data found"}), 404

        def get_val(r, k):
            idx = col_map.get(k, -1)
            if idx != -1 and idx < len(r):
                return r[idx]
            return ""

        songs = []
        for idx, row in enumerate(rows):
            row_num = idx + 2
            
            lyrics_raw = get_val(row, "lyrics")
            import json as _json
            lyrics_parsed = None
            if lyrics_raw:
                try:
                    loaded = _json.loads(lyrics_raw)
                    lyrics_parsed = loaded
                except Exception:
                    lyrics_parsed = None
            
            voicings = {}
            try:
                loaded = _json.loads(get_val(row, "voicings") or "{}")
                if isinstance(loaded, dict):
                    voicings = {str(k): str(v) for k, v in loaded.items() if v}
            except Exception:
                pass

            liked_raw = str(get_val(row, "liked")).strip().lower()
            
            song = {
                "row": row_num,
                "playlist": get_val(row, "playlist"),
                "artist": get_val(row, "artist"),
                "title": get_val(row, "title"),
                "album": get_val(row, "album"),
                "liked": liked_raw in ["true", "yes", "1"],
                "year": get_val(row, "year"),
                "genre": get_val(row, "genre"),
                "scrobble": get_val(row, "scrobble"),
                "lastfmScrobble": get_val(row, "lastfmScrobble"),
                "videoId": get_val(row, "videoId"),
                "chord": get_val(row, "chord"),
                "tonality": get_val(row, "tonality"),
                "progression": get_val(row, "progression"),
                "complex": get_val(row, "complex"),
                "emotional": get_val(row, "emotional"),
                "skill": get_val(row, "skill"),
                "style": get_val(row, "style"),
                "lastScanDate": get_val(row, "lastScanDate"),
                "lyrics": lyrics_parsed,
                "improvisation": get_val(row, "improvisation"),
                "voicings": voicings,
                "bpm": _parse_bpm(get_val(row, "bpm"))
            }
            songs.append(song)
            
        return jsonify(songs)
        
    except HttpError as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500






@app.route('/api/parse-pdf-harmony', methods=['POST'])
def parse_pdf_harmony():
    try:
        upload = request.files.get("file")
        if not upload:
            return jsonify({"found": False, "message": "No se recibió ningún fichero"}), 400
        pdf_bytes = upload.read()
        if not pdf_bytes.startswith(b"%PDF"):
            return jsonify({"found": False, "message": "El fichero no es un PDF"}), 400
        if len(pdf_bytes) > 15 * 1024 * 1024:
            return jsonify({"found": False, "message": "El PDF supera los 15 MB"}), 400
        result = parse_chord_pdf(pdf_bytes, request.form.get("artist", "").strip(), request.form.get("title", "").strip())
        if not result:
            return jsonify({"found": False, "message": "No se encontraron acordes en el PDF (¿es una imagen escaneada?)"})
        return jsonify(result)
    except Exception as e:
        print(f"PDF import failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/suggest-harmony', methods=['POST'])
def suggest_harmony():
    try:
        data = request.json
        artist = data.get("artist", "").strip()
        title = data.get("title", "").strip()
        source = data.get("source", "Songsterr").strip()
        
        if not artist or not title:
            return jsonify({"found": False, "message": "Falta el artista o título de la canción"}), 400
        
        if source == "Songsterr":
            result = fetch_songsterr_chords(artist, title)
        else:
            result = fetch_ug_chords(artist, title)
        
        if result:
            return jsonify(result)
        else:
            return jsonify({"found": False, "message": f"No se encontraron coincidencias en {source}"}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/analyze-chords', methods=['POST'])
def analyze_chords():
    """
    Analiza una cadena de acordes ingresada por el usuario y genera automáticamente:
      - Tonalidad (detectada por centro tonal y diatonismo)
      - Progresión Numérica / Cifrado Romano (i - iv - VI - V, etc.)
      - Complejidad armónica (Baja, Media, Media-Alta, Alta)
      - Estilo Emocional basado en teoría musical
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        chord_string = (data.get("chord") or "").strip()
        user_tonality = (data.get("tonality") or "").strip()
        
        if not chord_string:
            return jsonify({
                "tonality": user_tonality or "",
                "progression": "",
                "complex": "Baja",
                "style": ""
            })
            
        filtered_chords_list = clean_and_extract_chords(chord_string)
        
        # If tonality is not supplied by user, detect it from chords
        if user_tonality:
            final_tonality = user_tonality
        else:
            final_tonality = detect_key_from_chords(filtered_chords_list)
            
        progression = infer_progression(chord_string, final_tonality)
        emotional_style = infer_emotional_style(chord_string, final_tonality)
        complexity = infer_complexity(chord_string, final_tonality)
        
        return jsonify({
            "tonality": final_tonality,
            "progression": progression,
            "complex": complexity,
            "style": emotional_style
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/update', methods=['POST'])
def update_song():
    try:
        import json as _json
        data = request.get_json(force=True, silent=True) or {}
        print("UPDATE_SONG INCOMING DATA:", data)
        row = data.get("row")
        if not row or not isinstance(row, int):
            print("UPDATE_SONG RETURNING 400: Invalid row number")
            return jsonify({"error": "Invalid row number"}), 400
            
        target_artist = data.get("artist")
        target_title = data.get("title")
        
        if not target_artist or not target_title:
            print("UPDATE_SONG RETURNING 400: CLIENT_OUTDATED (Missing artist or title)")
            return jsonify({"error": "CLIENT_OUTDATED", "message": "Por favor, recarga la página. La aplicación se ha actualizado para ser más segura."}), 400
            
        fields = {}
        # Only update fields that are explicitly provided in the payload
        if "liked" in data:
            fields["liked"] = "TRUE" if data["liked"] else "FALSE"
        for key in ("chord", "tonality", "progression", "complex", "emotional", "skill",
                    "style", "improvisation", "bpm", "videoId", "lastScanDate"):
            if key in data:
                fields[key] = data[key] or ""
        if "voicings" in data:
            per_song = data["voicings"]
            fields["voicings"] = _json.dumps(per_song, ensure_ascii=False, sort_keys=True) if per_song else ""
        if "lyricsWithChords" in data:
            lyrics_val = data["lyricsWithChords"]
            fields["lyrics"] = _json.dumps(lyrics_val, ensure_ascii=False) if lyrics_val else ""

        try:
            actual_row = sheet.update_song(fields, video_id=data.get("lookupVideoId"),
                                           artist=target_artist, title=target_title, row_hint=row)
        except SheetBusy:
            return jsonify({"error": "La hoja está ocupada con otra escritura. Inténtalo de nuevo en unos segundos."}), 503
        except SongNotFound:
            return jsonify({"error": "No se pudo encontrar la canción en la hoja. Por favor, sincroniza la aplicación (Sincronizar Cloud) para actualizar las filas."}), 400

        return jsonify({"success": True, "message": f"Row {actual_row} updated successfully"})
        
    except HttpError as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route('/api/generate-improvisation', methods=['POST'])
def generate_improvisation():
    try:
        data = request.get_json(force=True, silent=True) or {}
        artist = data.get('artist', '')
        title = data.get('title', '')
        tonality = data.get('tonality', '')
        progression = data.get('progression', '')
        
        if not tonality or not progression:
            return jsonify({"error": "Se necesita la Tonalidad y la Progresión para generar la guía."}), 400
            
        try:
            guide = generate_guide(artist, title, tonality, progression)
        except GeminiError as e:
            return jsonify({"error": str(e)}), 503 if e.overloaded else 500
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500
        return jsonify({"success": True, "improvisation": guide})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/api/bpm', methods=['GET'])
def get_song_bpm():
    artist = request.args.get("artist", "").strip()
    title = request.args.get("title", "").strip()
    row = request.args.get("row", type=int)
    if not artist or not title:
        return jsonify({"bpm": None})
    sheet_row = None
    col_map = {}
    try:
        _, rows, col_map = sheet.read()
        if col_map.get("bpm", -1) != -1 and col_map.get("artist", -1) != -1 and col_map.get("title", -1) != -1:
            sheet_row = sheet.locate(rows, col_map, artist=artist, title=title, row_hint=row)
            if sheet_row:
                cells = rows[sheet_row - 2]
                stored = _parse_bpm(cells[col_map["bpm"]]) if len(cells) > col_map["bpm"] else None
                if stored:
                    return jsonify({"bpm": stored})
    except Exception as e:
        print(f"BPM sheet read failed for {artist} - {title}: {e}")
        sheet_row = None

    try:
        bpm = _lookup_bpm(artist, title)
    except Exception as e:
        print(f"BPM lookup failed for {artist} - {title}: {e}")
        return jsonify({"bpm": None})

    if bpm and sheet_row:
        try:
            sheet.write_cells([(sheet_row, "bpm", bpm)], col_map)
        except Exception as e:
            print(f"BPM save failed for {artist} - {title}: {e}")
    return jsonify({"bpm": bpm})


@app.route('/api/estimate-key', methods=['GET'])
def estimate_song_key():
    """Key suggested by the audio (Deezer preview). Never written to the sheet: the user decides."""
    artist = request.args.get("artist", "").strip()
    title = request.args.get("title", "").strip()
    if not artist or not title:
        return jsonify({"error": "Faltan artista o título"}), 400
    try:
        result = estimate_key(artist, title)
    except AudioKeyError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        print(f"Key estimation failed for {artist} - {title}: {e}")
        return jsonify({"error": "No se pudo analizar el audio"}), 502
    if not result:
        return jsonify({"error": "Deezer no tiene un preview de esta canción"}), 404
    return jsonify(result)


@app.route('/api/alternative-video', methods=['GET'])
def alternative_video():
    artist = request.args.get("artist", "").strip()
    title = request.args.get("title", "").strip()
    exclude = {v for v in request.args.get("exclude", "").split(",") if v}
    if not artist or not title:
        return jsonify({"videoId": None, "message": "Falta el artista o el título"}), 400
    try:
        scored = []
        for query in (f"{artist} {title}", f"{artist} {title} official audio"):
            for v in _search_youtube(query):
                if v["id"] in exclude or any(v["id"] == c["video"]["id"] for c in scored):
                    continue
                sc = _score_video(v, artist, title)
                if sc is not None:
                    scored.append({"score": sc, "video": v})
        scored.sort(key=lambda c: c["score"], reverse=True)
        for cand in scored[:6]:
            if _is_embeddable(cand["video"]["id"]):
                v = cand["video"]
                return jsonify({"videoId": v["id"], "title": v["title"], "channel": v["channel"], "length": v["length"]})
        return jsonify({"videoId": None, "message": "No hay más vídeos alternativos que se puedan incrustar"})
    except Exception as e:
        print(f"Alternative video search failed for {artist} - {title}: {e}")
        return jsonify({"videoId": None, "message": "No se pudo buscar en YouTube"}), 500


@app.route('/api/sync-playlist-song', methods=['POST'])
def sync_playlist_song():
    data = request.get_json(force=True, silent=True) or {}
    artist, title = (data.get("artist") or "").strip(), (data.get("title") or "").strip()
    video_id = (data.get("videoId") or "").strip()
    if not artist or not title or not video_id:
        return jsonify({"replaced": [], "message": "Faltan datos de la canción"}), 400
    try:
        changed, already_ok = sync_song_in_playlists(get_youtube_service(), artist, title, video_id, data.get("playlist", ""))
        return jsonify({"replaced": changed, "alreadyOk": already_ok})
    except YouTubeAuthRequired:
        return jsonify({"needsAuth": True})
    except HttpError as err:
        reason = str(err)
        if "accessNotConfigured" in reason or "has not been used" in reason:
            return jsonify({"error": f"Activa la YouTube Data API v3 en tu proyecto de Google Cloud: {YT_API_LINK}"}), 500
        return jsonify({"error": reason}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/youtube-auth', methods=['POST'])
def youtube_auth():
    """One-time consent: opens Google's authorization page in the browser of this machine."""
    try:
        get_youtube_service(interactive=True)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route('/api/replace-playlist-video', methods=['POST'])
def replace_playlist_video():
    data = request.get_json(force=True, silent=True) or {}
    old_id, new_id = (data.get("oldVideoId") or "").strip(), (data.get("newVideoId") or "").strip()
    if not old_id or not new_id or old_id == new_id:
        return jsonify({"replaced": [], "message": "Nada que reemplazar"})
    try:
        yt = get_youtube_service()
        changed = replace_video_in_playlists(yt, old_id, new_id, data.get("playlist", ""))
        return jsonify({"replaced": changed})
    except YouTubeAuthRequired:
        return jsonify({"needsAuth": True})
    except HttpError as err:
        reason = str(err)
        if "accessNotConfigured" in reason or "has not been used" in reason:
            return jsonify({"error": f"Activa la YouTube Data API v3 en tu proyecto de Google Cloud: {YT_API_LINK}"}), 500
        return jsonify({"error": reason}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/bulk-restyle', methods=['POST'])
def bulk_restyle():
    """
    Lee todas las canciones de la hoja, recalcula infer_emotional_style
    para las que tienen acorde + tonalidad, y actualiza la columna O (style)
    usando un único batchUpdate para minimizar las llamadas a la API.
    """
    try:
        headers, rows, col_map = sheet.read()
        if not rows:
            return jsonify({"error": "No hay datos en la hoja"}), 404

        chord_idx = col_map.get("chord", -1)
        tonality_idx = col_map.get("tonality", -1)
        targets = [k for k in ("style", "emotional") if col_map.get(k, -1) != -1]

        updated = 0
        skipped = 0
        cells = []

        for idx, row in enumerate(rows):
            row_num = idx + 2
            chord = row[chord_idx].strip() if chord_idx != -1 and chord_idx < len(row) else ""
            tonality = row[tonality_idx].strip() if tonality_idx != -1 and tonality_idx < len(row) else ""

            if not chord or not tonality or not targets:
                skipped += 1
                continue

            new_style = infer_emotional_style(chord, tonality)
            for key in targets:
                idx_col = col_map[key]
                # Solo las celdas que cambian
                if (row[idx_col] if idx_col < len(row) else "") != new_style:
                    cells.append((row_num, key, new_style))
            updated += 1

        if not updated:
            return jsonify({
                "success": True,
                "updated": 0,
                "skipped": skipped,
                "message": "Ninguna canción tenía datos armónicos para recalcular."
            })

        sheet.write_cells(cells, col_map)

        return jsonify({
            "success": True,
            "updated": updated,
            "skipped": skipped,
            "message": f"{updated} canciones actualizadas, {skipped} sin datos armónicos omitidas."
        })

    except HttpError as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/bulk-reskill', methods=['POST'])
def bulk_reskill():
    """
    Lee todas las canciones de la hoja, recalcula infer_complexity
    para las que tienen acordes, y actualiza la columna 'skill' / 'complex'
    usando batchUpdate.
    """
    try:
        headers, rows, col_map = sheet.read()
        if not rows:
            return jsonify({"error": "No hay datos en la hoja"}), 404

        chord_idx = col_map.get("chord", -1)
        tonality_idx = col_map.get("tonality", -1)
        targets = [k for k in ("skill", "complex") if col_map.get(k, -1) != -1]

        if not targets:
            return jsonify({"error": "No se encontró la columna skill o complejidad"}), 400

        updated = 0
        skipped = 0
        cells = []

        for idx, row in enumerate(rows):
            row_num = idx + 2
            chord = row[chord_idx].strip() if chord_idx != -1 and chord_idx < len(row) else ""
            tonality = row[tonality_idx].strip() if tonality_idx != -1 and tonality_idx < len(row) else ""

            if not chord:
                skipped += 1
                continue

            new_skill = infer_complexity(chord, tonality)
            for key in targets:
                idx_col = col_map[key]
                # Solo las celdas que cambian
                if (row[idx_col] if idx_col < len(row) else "") != str(new_skill):
                    cells.append((row_num, key, new_skill))
            updated += 1

        if not updated:
            return jsonify({
                "success": True,
                "updated": 0,
                "skipped": skipped,
                "message": "Ninguna canción tenía acordes para recalcular."
            })

        sheet.write_cells(cells, col_map)

        return jsonify({
            "success": True,
            "updated": updated,
            "skipped": skipped,
            "message": f"{updated} canciones recalculadas con éxito en Google Sheets ({skipped} sin acordes omitidas)."
        })

    except HttpError as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run(port=8000, debug=True):
    """Start the web app (`vibemus web`). debug=True also auto-reloads when a Python file changes."""
    print("Iniciando servidor de armonía musical...")
    app.run(host='::', port=port, debug=debug)


if __name__ == '__main__':
    run()
