"""Songsterr search and chord extraction."""
import re

from rapidfuzz import fuzz

from .harmony import detect_key_from_chords, infer_complexity, infer_emotional_style, infer_progression
from .ultimate_guitar import clean_ug_search_term, match_ug_song


# ─────────────────────────────────────────────────────
#  Songsterr Integration
# ─────────────────────────────────────────────────────

SONGSTERR_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

SONGSTERR_RHYTHM_POS = re.compile(
    r'rhythm|acoustic|clean|strum|chords|rh[yí]tm',
    re.IGNORECASE,
)
SONGSTERR_LEAD_NEG = re.compile(
    r'lead|solo|melody|vocal|bass|drum|percussion|synth|keyboard|piano|sax|flute|clarinet|violin|cello',
    re.IGNORECASE,
)


def _songsterr_select_rhythm_track(tracks):
    """Pick the most likely rhythm guitar track from Songsterr's track list.

    Pipeline:
      1. Filter to 6 or 7 string instruments (guitar range) with instrumentId 24-31.
      2. Score by name keywords: +10 rhythm, +5 acoustic, -10 lead/solo.
      3. Tiebreak by views.
      4. Return (track_index, track_dict) or None.
    """
    candidates = []
    for idx, trk in enumerate(tracks):
        tuning = trk.get("tuning", [])
        inst_id = trk.get("instrumentId", -1)
        name = trk.get("name", "") or trk.get("instrument", "")

        # Must be a 6 or 7 string guitar (not bass/drums/keys)
        if len(tuning) not in (6, 7):
            continue
        # General MIDI guitar range: 24 (Nylon) .. 31 (Guitar harmonics)
        if not (24 <= inst_id <= 31):
            continue

        # Skip explicit vocal tracks
        if trk.get("isVocalTrack"):
            continue

        score = 0
        if SONGSTERR_RHYTHM_POS.search(name):
            score += 10
        if inst_id in (24, 25):  # acoustic guitars
            score += 5
        if SONGSTERR_LEAD_NEG.search(name):
            score -= 10

        views = int(trk.get("views", 0))
        candidates.append((score, views, idx, trk))

    if not candidates:
        return None

    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    winner = candidates[0]
    return (winner[2], winner[3])


def _songsterr_all_guitar_tracks(tracks):
    """Return list of dicts describing all guitar tracks for the track selector."""
    result = []
    for idx, trk in enumerate(tracks):
        tuning = trk.get("tuning", [])
        inst_id = trk.get("instrumentId", -1)
        if len(tuning) not in (6, 7):
            continue
        if not (24 <= inst_id <= 31):
            continue
        if trk.get("isVocalTrack"):
            continue
        result.append({
            "index": idx,
            "name": trk.get("name", "") or trk.get("instrument", ""),
            "instrument": trk.get("instrument", ""),
            "views": int(trk.get("views", 0)),
            "hash": trk.get("hash", ""),
        })
    return result


def _songsterr_extract_chords_from_page(song_id, artist_str, title_str, track_idx=None):
    """Fetch the Songsterr chords page and extract chord data from embedded state.

    Songsterr embeds a <script id="state"> JSON containing the parsed
    chordpro array. We convert this to our standard format:
    <intro> Am D ... <verse> C G ...
    """
    import requests
    import json
    import re as _re
    import urllib.parse

    try:
        # Build the exact slug to avoid 301 Redirect / 103 Early Hints from Cloudflare
        artist_slug = urllib.parse.quote(artist_str.lower().replace(' ', '-').replace('/', '-'))
        title_slug = urllib.parse.quote(title_str.lower().replace(' ', '-').replace('/', '-'))
        page_url = f"https://www.songsterr.com/a/wsa/{artist_slug}-{title_slug}-chords-s{song_id}"
        
        # Use curl to bypass Python's inability to handle HTTP 103 Early Hints
        import subprocess
        
        result = subprocess.run(
            ["curl", "-sL", "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", page_url],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        html_content = result.stdout
        
        if not html_content or result.returncode != 0:
            return None

        state_match = _re.search(
            r'<script\s+id="state"\s+type="application/json">\s*(.*?)\s*</script>',
            html_content,
            _re.DOTALL,
        )
        if not state_match:
            return None

        state_data = json.loads(state_match.group(1))
        chordpro = state_data.get("chordpro", {}).get("current", [])
        
        if not chordpro or not isinstance(chordpro, list):
            return None
            
        result = []
        current_section = ""

        def format_chord(c):
            base = c.get('baseNote', {}).get('name', '')
            first = c.get('firstNote', {}).get('name', '')
            suffix = c.get('chordType', {}).get('suffix', '')
            
            chord_name = base + suffix
            if first and first != base:
                chord_name += f"/{first}"
            return chord_name

        for item in chordpro:
            itype = item.get("type")
            
            if itype == "section":
                text = item.get("text", "")
                section_name = f"<{text.strip().lower().replace(' ', '_')}>"
                result.append(section_name)
                current_section = section_name
                
            elif itype == "line":
                line_items = item.get("line", [])
                line_chords = []
                for li in line_items:
                    if li.get("type") == "chord":
                        chord_info = li.get("chord", {})
                        if chord_info:
                            line_chords.append(format_chord(chord_info))
                if line_chords:
                    if not current_section:
                        result.append("<verse>")
                        current_section = "<verse>"
                    result.extend(line_chords)

        final_string = " ".join(result)
        return final_string if final_string.strip() else None

    except Exception as e:
        print(f"Songsterr chord extraction failed for song {song_id}: {e}")

    return None


def fetch_songsterr_chords(artist, title):
    """Fetch chord data from Songsterr for a song.

    Flow:
      1. Search Songsterr API for matching songs.
      2. Filter results by fuzzy artist/title match.
      3. For each match, identify the rhythm guitar track.
      4. Extract chord data (from page state or chord labels).
      5. Run music theory analysis (key, progression, complexity, style).
      6. Return results in the same format as fetch_ug_chords().
    """
    import requests
    import json
    import re as _re
    import urllib.parse
    import time

    # Build search queries (reuse UG query builder for clean terms)
    clean_a = clean_ug_search_term(artist)
    clean_t = clean_ug_search_term(title)
    queries = []
    if clean_a and clean_t:
        queries.append(f"{clean_a} {clean_t}")
    if clean_t and clean_t not in queries:
        queries.append(clean_t)
    raw_q = f"{artist} {title}".strip()
    if raw_q not in queries:
        queries.append(raw_q)

    for query in queries:
        try:
            encoded_q = urllib.parse.quote_plus(query)
            search_url = f"https://www.songsterr.com/api/songs?pattern={encoded_q}"
            res = requests.get(search_url, headers=SONGSTERR_HEADERS, timeout=10)
            if res.status_code != 200:
                continue

            results = res.json()
            if not results:
                continue

            # Filter by fuzzy match using existing match function
            matched = []
            for song in results:
                cand_artist = song.get("artist", {}).get("name", "") if isinstance(song.get("artist"), dict) else song.get("artist", "")
                cand_title = song.get("title", "")
                # Strip version suffixes like "(Ver 2)", "(Live)", "(AI)" for matching
                cand_title_clean = _re.sub(
                    r'\s*\((?:Ver\s*\d+|Live|Acoustic|AI|Fingerstyle|Simplified|OKOUTTAKES|OK Outtakes Version).*?\)\s*$',
                    '',
                    cand_title,
                    flags=_re.IGNORECASE,
                ).strip()

                if match_ug_song(artist, title, cand_artist, cand_title_clean):
                    matched.append(song)

            if not matched:
                continue

            # Sort matches: prefer hasChords=True, non-junk, most views on popular track
            def _sort_key(s):
                has_chords = 1 if s.get("hasChords") else 0
                is_junk = 0 if s.get("isJunk") else 1
                # Sum views of all guitar tracks
                total_views = 0
                for t in s.get("tracks", []):
                    tuning = t.get("tuning", [])
                    if len(tuning) in (6, 7) and 24 <= t.get("instrumentId", -1) <= 31:
                        total_views += int(t.get("views", 0))
                return (has_chords, is_junk, total_views)

            matched.sort(key=_sort_key, reverse=True)

            collected_candidates = []

            for song in matched[:5]:  # Process up to 5 matches
                # In modern API, ID is just "id" instead of "songId" sometimes
                song_id = song.get("id") or song.get("songId")
                if not song_id:
                    continue

                tracks = song.get("tracks", [])
                rhythm_result = _songsterr_select_rhythm_track(tracks)
                if not rhythm_result:
                    continue

                rhythm_idx, rhythm_track = rhythm_result
                guitar_tracks = _songsterr_all_guitar_tracks(tracks)

                # Try to extract chords
                chord_string = None
                
                # Check hasChords - some search APIs return chordsPresent instead
                has_chords = song.get("hasChords") or song.get("chordsPresent")

                # Always try to extract from page state even if hasChords flag is missing in search
                cand_artist = song.get("artist", {}).get("name", "") if isinstance(song.get("artist"), dict) else song.get("artist", "")
                chord_string = _songsterr_extract_chords_from_page(song_id, cand_artist or artist, song.get("title", title), rhythm_idx)
                time.sleep(0.3)  # Polite delay

                if not chord_string or not chord_string.strip():
                    continue

                # Run music theory analysis using existing functions
                raw_chords_list = _re.findall(
                    r'\b[A-G][#b]?(?:[a-zA-Z0-9#b\-\+]*(?:/[A-G][#b]?)?)\b',
                    chord_string,
                )
                filtered_chords_list = [
                    c for c in raw_chords_list
                    if c.lower() not in [
                        'intro', 'verse', 'chorus', 'bridge', 'outro', 'solo',
                        'pre', 'interlude', 'tab', 'puente', 'so',
                    ]
                ]

                final_tonality = detect_key_from_chords(filtered_chords_list)
                progression = infer_progression(chord_string, final_tonality)
                emotional_style = infer_emotional_style(chord_string, final_tonality)
                complex_val = infer_complexity(chord_string, final_tonality)

                # Estimate match confidence
                cand_artist = song.get("artist", {}).get("name", "") if isinstance(song.get("artist"), dict) else song.get("artist", "")
                try:
                    match_score = fuzz.token_sort_ratio(
                        f"{artist} {title}",
                        f"{cand_artist} {song.get('title', '')}",
                    )
                    confidence = round(match_score / 100.0, 2)
                except Exception:
                    confidence = 0.95

                tab_url = f"https://www.songsterr.com/a/wsa/{urllib.parse.quote(cand_artist.lower().replace(' ', '-'))}-{urllib.parse.quote(song.get('title', '').lower().replace(' ', '-'))}-tab-s{song_id}"

                collected_candidates.append({
                    "artist": cand_artist or artist,
                    "title": song.get("title", title),
                    "chord": chord_string,
                    "tonality": final_tonality,
                    "progression": progression,
                    "complex": complex_val,
                    "style": emotional_style,
                    "confidence": confidence,
                    "source": "Songsterr",
                    "lyrics_with_chords": None,  # Songsterr doesn't provide lyric alignment
                    "rating": None,
                    "votes": None,
                    "tab_url": tab_url,
                    "songsterr_tracks": guitar_tracks,
                    "rhythm_track": rhythm_track.get("name", ""),
                    "song_id": song_id,
                })

            if not collected_candidates:
                continue

            # Build result in the same format as fetch_ug_chords
            top_cand = dict(collected_candidates[0])
            top_cand["found"] = True
            if len(collected_candidates) > 1:
                top_cand["candidates"] = collected_candidates

            return top_cand

        except Exception as e:
            print(f"Error fetching from Songsterr for query '{query}': {e}")
            continue

    return None
