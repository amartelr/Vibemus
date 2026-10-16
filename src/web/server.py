import os.path
import re
import time
import json
import os
from dotenv import load_dotenv

# Repo layout: <root>/src/web/server.py (this file), <root>/web/ (static front-end), <root>/config/web/ (secrets)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB_DIR = os.path.join(BASE_DIR, "web")
WEB_CONFIG_DIR = os.path.join(BASE_DIR, "config", "web")
load_dotenv(os.path.join(BASE_DIR, ".env"))
import requests


from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS
import pandas as pd
from rapidfuzz import process, fuzz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..services.sheet_gateway import SongSheet, SongNotFound
from ..services.sheet_lock import SheetBusy, busy_info

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
                "bpm": _parse_bpm(get_val(row, "bpm"))
            }
            songs.append(song)
            
        return jsonify(songs)
        
    except HttpError as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# TAB-TO-CHORD CONVERTER
# Converts guitar tablature (E|---|A|---|... format) to chord names.
# Used when the UG result is type "Tabs" and has no [ch] markers.
# ---------------------------------------------------------------------------

# Standard tuning open-string MIDI offsets (E2 A2 D3 G3 B3 E4)
_STRING_MIDI = [40, 45, 50, 55, 59, 64]  # E A D G B e
_STRING_NAMES = ['E', 'A', 'D', 'G', 'B', 'e']
_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Chord templates: frozenset of intervals (semitones above root, mod 12)
_CHORD_TEMPLATES = [
    (frozenset({0, 4, 7}),       ""),          # Major
    (frozenset({0, 3, 7}),       "m"),         # Minor
    (frozenset({0, 4, 7, 11}),   "maj7"),      # Major 7
    (frozenset({0, 4, 7, 10}),   "7"),         # Dominant 7
    (frozenset({0, 3, 7, 10}),   "m7"),        # Minor 7
    (frozenset({0, 3, 7, 9}),    "m6"),        # Minor 6
    (frozenset({0, 4, 7, 9}),    "6"),         # Major 6
    (frozenset({0, 2, 7}),       "sus2"),      # Sus2
    (frozenset({0, 5, 7}),       "sus4"),      # Sus4
    (frozenset({0, 3, 6}),       "dim"),       # Diminished
    (frozenset({0, 4, 8}),       "aug"),       # Augmented
    (frozenset({0, 7}),          "5"),         # Power chord
    (frozenset({0, 4}),          "(no5)"),     # Root + 3rd only
    (frozenset({0, 3}),          "m(no5)"),    # Root + m3rd only
]

def _midi_to_note(midi):
    """Return the note class name (C, C#, …, B) for a MIDI number."""
    return _NOTE_NAMES[midi % 12]

def _notes_to_chord(notes_set):
    """
    Given a frozenset of note class names, try to identify a chord.
    Returns a string like 'F#m', 'C', 'Am7', or None if unrecognised.
    """
    if len(notes_set) < 2:
        return None
    # Try every note as potential root
    for root_name in notes_set:
        root_idx = _NOTE_NAMES.index(root_name)
        intervals = frozenset(((_NOTE_NAMES.index(n) - root_idx) % 12) for n in notes_set)
        for template, suffix in _CHORD_TEMPLATES:
            if template == intervals:
                return root_name + suffix
    # Partial / loose match: find template that is a subset of our intervals
    for root_name in notes_set:
        root_idx = _NOTE_NAMES.index(root_name)
        intervals = frozenset(((_NOTE_NAMES.index(n) - root_idx) % 12) for n in notes_set)
        for template, suffix in _CHORD_TEMPLATES:
            if template.issubset(intervals) and len(template) >= 2:
                return root_name + suffix
    return None

def _parse_tab_block(block_text):
    """
    Parse a single [tab] block and return a list of chord names found.
    Handles multi-string patterns: identifies columns where multiple strings
    have fret numbers (not dashes or pipes), converts to notes, then to chords.
    """
    import re
    # Extract individual string lines in order: E A D G B e
    # Lines look like: "e|0--2--3--|" or "E|---------|" etc.
    line_map = {}  # string_index -> list of characters between pipes
    string_order = {}  # string_index -> string_name

    for line in block_text.splitlines():
        line = line.strip()
        # Match lines like "e|...", "B|...", "G|...", "D|...", "A|...", "E|..."
        m = re.match(r'^([eEBGDAb])\s*\|([^|\n]*)\|?', line)
        if not m:
            continue
        sname = m.group(1)
        body  = m.group(2)
        # Map to string index (0=low E, 5=high e)
        idx = {'E': 0, 'A': 1, 'D': 2, 'G': 3, 'B': 4, 'e': 5}.get(sname)
        if idx is None:
            continue
        line_map[idx]   = body
        string_order[idx] = sname

    if len(line_map) < 2:
        return []

    # Tokenise each string line into positional columns.
    # A fret token is one or two digits; '-' and '/' and '\' are separators.
    # We build a list of (col, fret_or_None) per string, aligning by character position.
    def tokenise(body):
        """Return list of (char_pos, fret_int) for every fret number in body."""
        tokens = []
        i = 0
        while i < len(body):
            c = body[i]
            if c.isdigit():
                j = i + 1
                while j < len(body) and body[j].isdigit():
                    j += 1
                tokens.append((i, int(body[i:j])))
                i = j
            else:
                i += 1
        return tokens

    string_tokens = {}
    for idx, body in line_map.items():
        string_tokens[idx] = tokenise(body)

    # Group frets that appear at nearby column positions (within ±2 chars)
    # into simultaneous "strum" events.
    all_events = []
    for idx, tokens in string_tokens.items():
        for col, fret in tokens:
            all_events.append((col, idx, fret))
    all_events.sort(key=lambda x: x[0])

    # Cluster events by column proximity
    clusters = []
    for col, idx, fret in all_events:
        placed = False
        for cluster in clusters:
            if abs(cluster['col'] - col) <= 3:
                cluster['notes'].append((idx, fret))
                cluster['col'] = (cluster['col'] + col) // 2  # avg
                placed = True
                break
        if not placed:
            clusters.append({'col': col, 'notes': [(idx, fret)]})

    # Convert each cluster to a chord name
    chords = []
    seen = set()
    for cluster in clusters:
        if len(cluster['notes']) < 2:
            continue
        note_names = set()
        for (str_idx, fret) in cluster['notes']:
            if str_idx not in _STRING_MIDI:
                pass
            midi = _STRING_MIDI[str_idx] + fret
            note_names.add(_midi_to_note(midi))
        chord = _notes_to_chord(frozenset(note_names))
        if chord and chord not in seen:
            chords.append(chord)
            seen.add(chord)

    return chords

def tab_to_chords(raw_content):
    """
    Convert a full UG [tab] raw content string to a chord-list string
    compatible with the rest of the pipeline.
    Returns a string like '<verse_1> F#m B <chorus> F#m7 C' or empty string.
    """
    import re

    # Split content into sections using [SectionName] markers (not [tab] / [ch])
    section_split = re.split(
        r'(\[(?!tab\b)(?!/tab\b)(?!ch\b)(?!/ch\b)[^\]]+\])',
        raw_content, flags=re.IGNORECASE
    )

    result_parts = []
    current_section = '<intro>'

    i = 0
    while i < len(section_split):
        part = section_split[i]
        # Check if this part is a section header like [Chorus]
        if re.match(r'^\[(?!tab)(?!/tab)(?!ch)(?!/ch)[^\]]+\]$', part.strip(), re.IGNORECASE):
            current_section = part.strip().lower() \
                .replace(' ', '_').replace('-', '_') \
                .replace('[', '<').replace(']', '>')
            i += 1
            continue

        # Extract [tab] blocks from this part
        tab_blocks = re.findall(r'\[tab\](.*?)\[/tab\]', part, re.IGNORECASE | re.DOTALL)
        section_chords = []
        for block in tab_blocks:
            section_chords.extend(_parse_tab_block(block))

        # Deduplicate preserving order
        seen = set()
        unique = []
        for c in section_chords:
            if c not in seen:
                unique.append(c)
                seen.add(c)

        if unique:
            result_parts.append(f"{current_section} " + " ".join(unique))

        i += 1

    return " ".join(result_parts)


def clean_ug_content(content):
    import re
    # Exclude [ch], [/ch], [tab], [/tab]
    section_pattern = r'(\[(?!ch\b)(?!/ch\])(?!tab\])(?!/tab\])[^\]]+\])'
    parts = re.split(section_pattern, content, flags=re.IGNORECASE)
    
    formatted_parts = []
    
    first_text = parts[0]
    first_chords = re.findall(r'\[ch(?: [^\]]*)?\](.*?)\[/ch\]', first_text)
    if first_chords:
        formatted_parts.append("<intro> " + " ".join(first_chords))
        
    for i in range(1, len(parts), 2):
        if i >= len(parts):
            break
        section_name = parts[i].strip()
        # Clean section name, e.g. [Verse 1] -> <verse_1>
        clean_section = section_name.lower().replace(" ", "_").replace("-", "_").replace("[", "<").replace("]", ">")
        
        section_text = parts[i+1] if (i+1) < len(parts) else ""
        chords = re.findall(r'\[ch(?: [^\]]*)?\](.*?)\[/ch\]', section_text)
        if chords:
            formatted_parts.append(f"{clean_section} " + " ".join(chords))
            
    return " ".join(formatted_parts)


def extract_lyrics_with_chords(content):
    """
    Parse a UG raw tab content string and return a structured list of sections
    with interleaved chord+lyric lines, suitable for rendering a chord chart.

    UG tabs use several formats (often mixed in the same tab):

      A) [tab] block — chord line ABOVE lyric line (most common on UG chords tabs):
            [tab]               [ch]Em7[/ch]                 [ch]Bm7[/ch]
            It's gonna take more than prayers to change this place[/tab]

      B) Inline — chords embedded in the lyric line:
            [ch]Am[/ch]I walked [ch]C[/ch]alone through [ch]G[/ch]the rain

      C) Chord-only lines (Intro / Outro / pure chord rows):
            [ch]Em7[/ch]  [ch]Bm7[/ch]  [ch]Em7[/ch]  [ch]Bm7[/ch]

    Returns a list of section dicts:
      [{"section": "Verse 1", "lines": [{"lyric": "...", "chords": [{"word_idx": N, "chord": "X"}]}, ...]}, ...]
    Returns None if no lyrics are found.
    """
    import re

    if not content:
        return None



    CHORD_TAG = re.compile(r'\[ch(?:\s[^\]]*)?](.*?)\[/ch\]', re.IGNORECASE)
    SECTION_RE = re.compile(
        r'(\[(?!ch\b)(?!/ch\b)(?!tab\b)(?!/tab\b)[^\]]+\])',
        re.IGNORECASE
    )
    TAB_BLOCK_RE = re.compile(r'\[tab\](.*?)\[/tab\]', re.IGNORECASE | re.DOTALL)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _col_of_chord(line_text, chord_start_char):
        """Count the number of visible (non-tag) characters before chord_start_char."""
        col = 0
        k = 0
        while k < chord_start_char:
            m = CHORD_TAG.match(line_text, k)
            if m:
                k = m.end()  # skip the whole [ch]..[/ch] without counting
            else:
                col += 1
                k += 1
        return col

    def _chord_entries_from_line(chord_line):
        """Extract list of {col, chord} from a chord-only line."""
        entries = []
        for m in CHORD_TAG.finditer(chord_line):
            col = _col_of_chord(chord_line, m.start())
            entries.append({"col": col, "chord": m.group(1).strip()})
        return entries

    def _map_chords_to_words(chord_entries, lyric):
        """Map column positions to word indices in lyric."""
        if not lyric.strip():
            return [{"word_idx": 0, "chord": e["chord"]} for e in chord_entries]
        words = lyric.split()
        word_cols = []
        col = 0
        for w in words:
            word_cols.append(col)
            col += len(w) + 1
        mapped = []
        for ce in chord_entries:
            widx = 0
            for wi, wc in enumerate(word_cols):
                if wc <= ce["col"]:
                    widx = wi
            mapped.append({"word_idx": widx, "chord": ce["chord"]})
        return mapped

    def _parse_tab_block(block_inner):
        """
        Parse the interior of a [tab]...[/tab] block.
        The block contains one or two lines:
          Line 0 (chord line): spaces + [ch]chord[/ch] tags
          Line 1 (lyric line): the sung text (may be absent for chord-only blocks)
        Returns a list of {lyric, chords} dicts (usually just one).
        """
        lines = [l for l in block_inner.splitlines()]
        # strip empty lines but keep structure
        non_empty = [(i, l) for i, l in enumerate(lines) if l.strip()]
        if not non_empty:
            return []

        results = []

        i = 0
        while i < len(non_empty):
            idx, line = non_empty[i]
            stripped = line.strip()

            chords_on_this = CHORD_TAG.findall(stripped)
            text_without_chords = CHORD_TAG.sub('', stripped)
            lyric_text = re.sub(r'\s{2,}', ' ', text_without_chords).strip()

            if not chords_on_this:
                # Pure lyric line
                if lyric_text:
                    results.append({"lyric": lyric_text, "chords": []})
                i += 1
                continue

            if lyric_text:
                # INLINE format: chords and lyrics mixed on same line
                plain = ''
                chord_positions = []
                k = 0
                while k < len(stripped):
                    m = CHORD_TAG.match(stripped, k)
                    if m:
                        chord_positions.append({"char_pos": len(plain), "chord": m.group(1).strip()})
                        k = m.end()
                    else:
                        plain += stripped[k]
                        k += 1
                lyric_plain = plain.strip()
                words = lyric_plain.split()
                word_start_positions = []
                cursor = 0
                for w in words:
                    p = lyric_plain.find(w, cursor)
                    word_start_positions.append(p)
                    cursor = p + len(w)
                mapped = []
                for cp in chord_positions:
                    widx = 0
                    for wi, wp in enumerate(word_start_positions):
                        if wp <= cp["char_pos"]:
                            widx = wi
                    mapped.append({"word_idx": widx, "chord": cp["chord"]})
                if lyric_plain:
                    results.append({"lyric": lyric_plain, "chords": mapped})
                elif mapped:
                    results.append({"lyric": "", "chords": mapped})
                i += 1

            else:
                # TWO-LINE format: this line is chord-only, NEXT line is the lyric
                chord_entries = _chord_entries_from_line(line)  # use original (with spacing)

                # Look for next non-empty line
                lyric_line = ''
                if i + 1 < len(non_empty):
                    next_idx, next_line = non_empty[i + 1]
                    next_stripped = next_line.strip()
                    next_chords = CHORD_TAG.findall(next_stripped)
                    next_text = re.sub(r'\s{2,}', ' ', CHORD_TAG.sub('', next_stripped)).strip()

                    if next_text and not next_chords:
                        # Pure lyric line — consume it
                        lyric_line = next_text
                        i += 1
                    elif next_text and next_chords:
                        # Mixed inline line — consume it differently
                        lyric_line = next_text
                        i += 1

                mapped = _map_chords_to_words(chord_entries, lyric_line)
                results.append({"lyric": lyric_line, "chords": mapped})
                i += 1

        return results

    def _parse_plain_block(text, section_dict):
        """
        Parse text that is NOT inside a [tab] block.
        Handles: chord-only lines, inline chord+lyric lines, pure lyric lines,
        and classic two-line (chords above / lyrics below) outside of [tab].
        """
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if not stripped:
                i += 1
                continue

            chords_on_line = CHORD_TAG.findall(stripped)
            text_without_chords = CHORD_TAG.sub('', stripped)
            lyric_text = re.sub(r'\s{2,}', ' ', text_without_chords).strip()

            if not chords_on_line:
                if lyric_text:
                    section_dict["lines"].append({"lyric": lyric_text, "chords": []})
                i += 1
                continue

            if lyric_text:
                # INLINE
                plain = ''
                chord_positions = []
                k = 0
                while k < len(stripped):
                    m = CHORD_TAG.match(stripped, k)
                    if m:
                        chord_positions.append({"char_pos": len(plain), "chord": m.group(1).strip()})
                        k = m.end()
                    else:
                        plain += stripped[k]
                        k += 1
                lyric_plain = plain.strip()
                words = lyric_plain.split()
                wpos = []
                cursor = 0
                for w in words:
                    p = lyric_plain.find(w, cursor)
                    wpos.append(p)
                    cursor = p + len(w)
                mapped = []
                for cp in chord_positions:
                    widx = 0
                    for wi, wp in enumerate(wpos):
                        if wp <= cp["char_pos"]:
                            widx = wi
                    mapped.append({"word_idx": widx, "chord": cp["chord"]})
                if lyric_plain:
                    section_dict["lines"].append({"lyric": lyric_plain, "chords": mapped})
                elif mapped:
                    section_dict["lines"].append({"lyric": "", "chords": mapped})
                i += 1
            else:
                # Chord-only line — look ahead for lyric
                chord_entries = _chord_entries_from_line(lines[i])
                lyric_line = ''
                j = i + 1
                while j < len(lines):
                    nxt = lines[j].strip()
                    if nxt and not CHORD_TAG.search(nxt):
                        lyric_line = nxt
                        i = j
                        break
                    elif nxt:
                        break
                    j += 1
                mapped = _map_chords_to_words(chord_entries, lyric_line)
                section_dict["lines"].append({"lyric": lyric_line, "chords": mapped})
                i += 1

    # ── Main parsing ─────────────────────────────────────────────────────────
    # Strategy:
    #  1. Split by section headers [Verse 1], [Chorus], etc.
    #  2. Within each section, extract [tab]...[/tab] blocks first,
    #     then parse the remaining plain text.

    sections = []
    pending_section = {"section": "Intro", "lines": []}

    # Split by section headers
    parts = SECTION_RE.split(content)

    for part in parts:
        if SECTION_RE.fullmatch(part.strip()):
            if pending_section["lines"]:
                sections.append(pending_section)
            pending_section = {"section": part.strip().strip('[]'), "lines": []}
            continue

        # Within this section part, extract [tab] blocks first
        # Replace each [tab]...[/tab] with a sentinel so we can split around them
        remaining = part
        while True:
            tab_match = TAB_BLOCK_RE.search(remaining)
            if not tab_match:
                break
            # Parse the plain text before the [tab] block
            before = remaining[:tab_match.start()]
            if before.strip():
                _parse_plain_block(before, pending_section)
            # Parse the [tab] block itself
            tab_lines = _parse_tab_block(tab_match.group(1))
            pending_section["lines"].extend(tab_lines)
            remaining = remaining[tab_match.end():]

        # Parse any remaining plain text after the last [tab] block
        if remaining.strip():
            _parse_plain_block(remaining, pending_section)

    if pending_section["lines"]:
        sections.append(pending_section)

    # Filter out tab notation and prose lines from the parsed sections
    TAB_PATTERN = re.compile(r'(^\s*[eBGDAE]\s*\|.*[-—]{2,})|(\|[-—]{3,}\|)|(\b[eBGDAE]\|[-—])|([-—]{5,})', re.MULTILINE)
    PROSE_WORDS = re.compile(r'\b(preface|fretboard|first guitar|second guitar|bump up that reverb|usable chords)\b', re.IGNORECASE)
    
    cleaned_sections = []
    for sec in sections:
        valid_lines = []
        for line in sec["lines"]:
            lyric = line["lyric"]
            if lyric and (TAB_PATTERN.search(lyric) or PROSE_WORDS.search(lyric)):
                continue
            valid_lines.append(line)
        if valid_lines:
            sec["lines"] = valid_lines
            cleaned_sections.append(sec)
    sections = cleaned_sections

    # Return None if no actual lyrics (only chord-only entries)
    all_lyric_lines = [
        line for sec in sections for line in sec["lines"]
        if line["lyric"].strip()
    ]
    if not all_lyric_lines:
        return None

    # Quality gate: at least 20% of lyric lines must have chord annotations.
    # If fewer lines have chords, the content is likely explanatory prose rather
    # than a real chord chart, and rendering it would corrupt the UI display.
    lines_with_chords = sum(1 for line in all_lyric_lines if line["chords"])
    chord_density = lines_with_chords / len(all_lyric_lines)
    if chord_density < 0.20:
        return None

    return sections if sections else None


SEMITONES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
NOTE_MAP = {
    'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#',
    'Cb': 'B', 'Fb': 'E', 'B#': 'C', 'E#': 'F',
    'C': 'C', 'D': 'D', 'E': 'E', 'F': 'F', 'G': 'G', 'A': 'A', 'B': 'B',
    'C#': 'C#', 'D#': 'D#', 'F#': 'F#', 'G#': 'G#', 'A#': 'A#'
}
FLAT_NAMES = {
    'C#': 'Db', 'D#': 'Eb', 'F#': 'Gb', 'G#': 'Ab', 'A#': 'Bb'
}

def clean_and_extract_chords(text):
    if not text:
        return []
    import re
    # 1. Strip section tags like [Intro], [Verse 1], [Between verses], [Middle 8], <verse_1>, etc.
    t = re.sub(r'\[(?!ch\b)(?!/ch\])[^\]]*\]', ' ', text)
    t = re.sub(r'<[^>]+>', ' ', t)
    
    # 2. Extract chord tokens
    chord_pattern = r'\b[A-G][#b]?(?:[Mm]aj|[Mm]in|[Dd]im|[Aa]ug|[Ss]us|[Aa]dd|m|M|[0-9]|\-|\+|\#|b|o|\u0394)*(?:/[A-G][#b]?)?(?!\w)'
    matches = re.findall(chord_pattern, t)
    
    filtered = []
    stop_words = {'intro', 'verse', 'chorus', 'bridge', 'outro', 'solo', 'pre', 'instrumental', 'tab', 'ch', 'verso', 'estribillo', 'puente', 'middle', 'between', 'verses', 'in', 'to', 'is', 'it', 'at', 'on', 'or', 'an', 'be', 'do', 'so'}
    for m in matches:
        if m.lower() in stop_words:
            continue
        if len(m) > 1 or m in "ABCDEFG":
            filtered.append(m)
    return filtered

def parse_chord_root_and_quality(chord):
    import re
    chord = chord.split('/')[0].strip()
    match = re.match(r'^([A-G][#b]?)(.*)$', chord)
    if not match:
        return None, None, None
    root = match.group(1)
    suffix = match.group(2)
    
    quality = 'major'
    s_low = suffix.lower()
    if 'min' in s_low or ('m' in s_low and not 'maj' in s_low):
        quality = 'minor'
    elif 'dim' in s_low or 'o' in s_low:
        quality = 'dim'
    elif 'aug' in s_low or '+' in s_low:
        quality = 'aug'
        
    return root, quality, suffix

def get_roman_numeral(key_root, key_mode, chord_name):
    import re
    root, quality, suffix = parse_chord_root_and_quality(chord_name)
    if not root:
        return chord_name
        
    r1 = NOTE_MAP.get(key_root, key_root)
    r2 = NOTE_MAP.get(root, root)
    if r1 not in SEMITONES or r2 not in SEMITONES:
        return chord_name
        
    idx1 = SEMITONES.index(r1)
    idx2 = SEMITONES.index(r2)
    diff = (idx2 - idx1) % 12
    
    roman = ""
    is_minor_key = 'minor' in key_mode.lower() or 'min' in key_mode.lower() or key_mode.lower().strip() == 'm'
    
    if is_minor_key:
        if diff == 0:
            roman = 'i' if quality == 'minor' else 'I'
        elif diff == 1:
            roman = 'bII'
        elif diff == 2:
            roman = 'ii°' if quality == 'dim' else ('ii' if quality == 'minor' else 'II')
        elif diff == 3:
            roman = 'III' if quality == 'major' else 'iii'
        elif diff == 4:
            roman = 'III' if quality == 'major' else 'iii'
        elif diff == 5:
            roman = 'iv' if quality == 'minor' else 'IV'
        elif diff == 6:
            roman = 'bV'
        elif diff == 7:
            roman = 'v' if quality == 'minor' else 'V'
        elif diff == 8:
            roman = 'VI' if quality == 'major' else 'vi'
        elif diff == 9:
            roman = 'vi°' if quality == 'dim' else 'VI'
        elif diff == 10:
            roman = 'VII' if quality == 'major' else 'vii'
        elif diff == 11:
            roman = 'vii°' if quality == 'dim' else 'VII'
    else:
        if diff == 0:
            roman = 'I' if quality == 'major' else 'i'
        elif diff == 1:
            roman = 'bII'
        elif diff == 2:
            roman = 'ii' if quality == 'minor' else 'II'
        elif diff == 3:
            roman = 'bIII'
        elif diff == 4:
            roman = 'iii' if quality == 'minor' else 'III'
        elif diff == 5:
            roman = 'IV' if quality == 'major' else 'iv'
        elif diff == 6:
            roman = 'bV'
        elif diff == 7:
            roman = 'V' if quality == 'major' else 'v'
        elif diff == 8:
            roman = 'bVI'
        elif diff == 9:
            roman = 'vi' if quality == 'minor' else 'VI'
        elif diff == 10:
            roman = 'bVII'
        elif diff == 11:
            roman = 'vii°' if quality == 'dim' else 'vii'
            
    clean_suffix = suffix
    if quality == 'minor':
        clean_suffix = re.sub(r'^(m|min)', '', suffix)
        
    return f"{roman}{clean_suffix}"

def parse_tonality(tonality_str):
    import re
    if not tonality_str:
        return None, None
    tonality_str = tonality_str.strip()
    match = re.match(r'^([A-G][#b]?)(?:\s+(.*)|(.*))?$', tonality_str)
    if not match:
        return None, None
        
    root = match.group(1)
    mode_part = match.group(2) or match.group(3) or ""
    mode_part = mode_part.strip().lower()
    
    mode = "Major"
    if mode_part in ['m', 'min', 'minor', 'minor key', 'menor']:
        mode = "Minor"
        
    return root, mode

def detect_key_from_chords(chord_list):
    if not chord_list:
        return "C Major"
        
    flat_count = sum(1 for c in chord_list if 'b' in c and not c.startswith('B'))
    sharp_count = sum(1 for c in chord_list if '#' in c)
    prefer_flats = flat_count > sharp_count

    parsed = []
    for c in chord_list:
        r, q, s = parse_chord_root_and_quality(c)
        if r:
            canon_root = NOTE_MAP.get(r, r)
            if canon_root in SEMITONES:
                parsed.append((canon_root, q))
                
    if not parsed:
        return "C Major"
        
    best_key = "C Major"
    best_score = -9999
    
    transitions = []
    for i in range(len(parsed) - 1):
        transitions.append((parsed[i], parsed[i+1]))
        
    for root in SEMITONES:
        for mode in ["Major", "Minor"]:
            score = 0
            idx1 = SEMITONES.index(root)
            
            # 1. Diatonic scoring
            for c_root, c_quality in parsed:
                idx2 = SEMITONES.index(c_root)
                diff = (idx2 - idx1) % 12
                
                if mode == "Major":
                    if diff == 0 and c_quality == "major": score += 3.5
                    elif diff == 2 and c_quality == "minor": score += 2.0
                    elif diff == 4 and c_quality == "minor": score += 2.0
                    elif diff == 5 and c_quality == "major": score += 2.5
                    elif diff == 7 and c_quality == "major": score += 3.0
                    elif diff == 9 and c_quality == "minor": score += 2.0
                    elif diff == 11 and c_quality in ["dim", "minor"]: score += 1.0
                    else:
                        score -= 2.5
                else: # Minor
                    if diff == 0 and c_quality == "minor": score += 3.5
                    elif diff == 2 and c_quality in ["dim", "minor"]: score += 1.5
                    elif diff == 3 and c_quality == "major": score += 2.0
                    elif diff == 5 and c_quality in ["minor", "major"]: score += 2.0
                    elif diff == 7 and c_quality in ["minor", "major"]: score += 2.5
                    elif diff == 8 and c_quality == "major": score += 2.0
                    elif diff == 10 and c_quality == "major": score += 2.0
                    elif diff == 11 and c_quality in ["dim", "major"]: score += 1.5
                    else:
                        score -= 2.5

            # 2. Cadence & progression bonuses
            for (c1_root, c1_qual), (c2_root, c2_qual) in transitions:
                d1 = (SEMITONES.index(c1_root) - idx1) % 12
                d2 = (SEMITONES.index(c2_root) - idx1) % 12
                
                if mode == "Major":
                    if d1 == 7 and d2 == 0 and c2_qual == "major": score += 4.0 # V -> I
                    elif d1 == 5 and d2 == 0 and c2_qual == "major": score += 3.0 # IV -> I
                    elif d1 == 0 and d2 == 7: score += 2.0 # I -> V
                    elif d1 == 0 and d2 == 5: score += 2.0 # I -> IV
                    elif d1 == 5 and d2 == 7: score += 2.5 # IV -> V
                    elif d1 == 2 and d2 == 7: score += 2.5 # ii -> V
                else:
                    if d1 == 10 and d2 == 0 and c2_qual == "minor": score += 4.5 # VII -> i (Aeolian)
                    elif d1 == 7 and d2 == 0 and c2_qual == "minor": score += 4.5 # V/v -> i
                    elif d1 == 5 and d2 == 0 and c2_qual == "minor": score += 3.0 # iv -> i
                    elif d1 == 8 and d2 == 10 and c1_qual == "major" and c2_qual == "major": score += 3.0 # VI -> VII
                    elif d1 == 8 and d2 == 5: score += 2.0 # VI -> iv
                    elif d1 == 0 and d2 == 8: score += 1.5 # i -> VI

            # 3. First and last chord
            first_diff = (SEMITONES.index(parsed[0][0]) - idx1) % 12
            last_diff = (SEMITONES.index(parsed[-1][0]) - idx1) % 12
            if mode == "Major":
                if first_diff == 0 and parsed[0][1] == "major": score += 2.5
                if last_diff == 0 and parsed[-1][1] == "major": score += 3.0
            else:
                if first_diff == 0 and parsed[0][1] == "minor": score += 2.5
                if last_diff == 0 and parsed[-1][1] == "minor": score += 3.0

            if score > best_score:
                best_score = score
                display_root = FLAT_NAMES.get(root, root) if prefer_flats else root
                best_key = f"{display_root} {mode}"
                
    return best_key

def infer_progression(chord_string, tonality):
    if not tonality or not chord_string:
        return ""
        
    key_root, key_mode = parse_tonality(tonality)
    if not key_root:
        return ""
        
    chords = clean_and_extract_chords(chord_string)
    romans = []
    for c in chords:
        r = get_roman_numeral(key_root, key_mode, c)
        if r and r not in romans:
            romans.append(r)
            
    return " - ".join(romans[:6])

def infer_emotional_style(chord_string, tonality):
    """
    Sistema de inferencia de estilo emocional basado en teoría musical:
      1. Modo de la tónica (Mayor/Menor)
      2. Color tonal de la tonalidad específica
      3. Patrones de progresión armónica (números romanos)
      4. Vocabulario de tipos de acordes (dim, aug, maj7, sus, etc.)
      5. Densidad armónica (nº de acordes únicos)
      6. Préstamo modal (mezcla mayor/menor)
    Devuelve hasta 3 etiquetas ordenadas por peso.
    """
    import re

    # ─── Etiquetas disponibles con sus puntuaciones acumuladas ───────────────
    scores = {
        "Oscura":       0,
        "Melancólica":  0,
        "Nostálgica":   0,
        "Íntima":       0,
        "Soñadora":     0,
        "Cinematográfica": 0,
        "Épica":        0,
        "Elegante":     0,
        "Moderna":      0,
        "Alegre":       0,
        "Enérgica":     0,
        "Orgánica":     0,
        "Tensa":        0,
        "Flotante":     0,
        "Cálida":       0,
    }

    if not tonality:
        scores["Melancólica"] += 3
        top = sorted(scores, key=lambda k: scores[k], reverse=True)
        return ", ".join(t for t in top[:2] if scores[t] > 0) or "Melancólica"

    is_minor = bool(re.search(r'\b(m|min|minor)\b', tonality, re.IGNORECASE))

    # ─── 1. COLOR TONAL DE LA TONALIDAD ESPECÍFICA ────────────────────────────
    # Basado en la tradición de Chladni/Schubart y análisis moderno
    key_color_minor = {
        "A":  ["Íntima", "Melancólica"],           # La menor — el "centro" emocional
        "D":  ["Oscura", "Melancólica"],            # Re menor — grave y lúgubre
        "E":  ["Oscura", "Épica"],                  # Mi menor — profunda, wagneriana
        "B":  ["Tensa", "Oscura"],                  # Si menor — inquieta
        "F#": ["Melancólica", "Soñadora"],          # Fa# menor — romanticismo frío
        "C#": ["Cinematográfica", "Tensa"],         # Do# menor — dramática
        "G#": ["Soñadora", "Flotante"],             # Sol# menor — etérea
        "D#": ["Melancólica", "Soñadora"],          # Re# menor — profunda y soñadora
        "A#": ["Nostálgica", "Cálida"],             # La# menor
        "C":  ["Oscura", "Íntima"],                 # Do menor — grave, beethoveniana
        "G":  ["Nostálgica", "Orgánica"],           # Sol menor — folk oscuro
        "F":  ["Melancólica", "Cinematográfica"],   # Fa menor — introspectiva
        "Bb": ["Nostálgica", "Cálida"],             # Si♭ menor — jazz oscuro
        "Eb": ["Melancólica", "Soñadora"],          # Mi♭ menor — grandiosa y melancólica
        "Ab": ["Soñadora", "Flotante"],             # La♭ menor
        "Db": ["Cinematográfica", "Tensa"],         # Re♭ menor
        "Gb": ["Melancólica", "Soñadora"],          # Sol♭ menor
    }
    key_color_major = {
        "C":  ["Alegre", "Orgánica"],               # Do mayor — pura, natural
        "G":  ["Alegre", "Enérgica"],               # Sol mayor — folk brillante
        "D":  ["Elegante", "Alegre"],               # Re mayor — triunfal
        "A":  ["Cálida", "Alegre"],                 # La mayor — soleada
        "E":  ["Brillante", "Enérgica"],            # Mi mayor — eufórica
        "B":  ["Moderna", "Elegante"],              # Si mayor — sofisticada
        "F#": ["Soñadora", "Elegante"],             # Fa# mayor — flotante-lujosa
        "C#": ["Soñadora", "Melancólica"],          # Do# mayor
        "G#": ["Soñadora", "Cálida"],               # Sol# mayor
        "D#": ["Elegante", "Cinematográfica"],      # Re# mayor
        "A#": ["Cálida", "Elegante"],               # La# mayor
        "F":  ["Cálida", "Íntima"],                 # Fa mayor — tierna
        "Bb": ["Cálida", "Elegante"],               # Si♭ mayor — jazz cálido
        "Eb": ["Elegante", "Cinematográfica"],      # Mi♭ mayor — grandiosa
        "Ab": ["Soñadora", "Cálida"],               # La♭ mayor — romántica
        "Db": ["Soñadora", "Melancólica"],          # Re♭ mayor — languidez
        "Gb": ["Soñadora", "Elegante"],             # Sol♭ mayor
    }

    key_root = re.match(r'^([A-G][#b]?)', tonality)
    key_root = key_root.group(1) if key_root else None
    if key_root:
        color_map = key_color_minor if is_minor else key_color_major
        for label in color_map.get(key_root, []):
            if label in scores:
                scores[label] += 2

    # ─── 2. MODO MAYOR/MENOR — base de 3 pts ─────────────────────────────────
    if is_minor:
        scores["Melancólica"] += 3
        scores["Oscura"]      += 2
    else:
        scores["Alegre"]      += 3
        scores["Cálida"]      += 1

    # ─── 3. EXTRAER ACORDES ──────────────────────────────────────────────────
    chords = clean_and_extract_chords(chord_string)
    chords_lower = [c.lower() for c in chords]
    unique_chords = list(dict.fromkeys(chords_lower))

    # ─── 4. VOCABULARIO DE TIPOS DE ACORDES ──────────────────────────────────
    has_maj7  = any('maj7' in c or 'maj9' in c for c in chords_lower)
    has_add9  = any('add9' in c or 'add2' in c for c in chords_lower)
    has_dim   = any('dim' in c or 'o' == c[-1:] for c in chords_lower)
    has_aug   = any('aug' in c or '+' in c for c in chords_lower)
    has_sus   = any('sus' in c for c in chords_lower)
    has_7sus  = any('7sus' in c for c in chords_lower)
    has_m7    = any(re.search(r'm7|min7', c) for c in chords_lower)
    has_dom7  = any(re.search(r'(?<![ma])7(?!sus)', c) for c in chords_lower)
    has_9_11  = any(re.search(r'(?<!add)[9]|11|13', c) for c in chords_lower)
    has_power = any(re.search(r'5(?![a-z])', c) for c in chords_lower)

    if has_maj7:
        scores["Soñadora"]   += 3
        scores["Elegante"]   += 2
        scores["Moderna"]    += 1
    if has_add9:
        scores["Soñadora"]   += 2
        scores["Flotante"]   += 2
    if has_dim:
        scores["Tensa"]      += 3
        scores["Cinematográfica"] += 2
        scores["Oscura"]     += 1
    if has_aug:
        scores["Tensa"]      += 2
        scores["Flotante"]   += 2
        scores["Cinematográfica"] += 1
    if has_7sus or has_sus:
        scores["Flotante"]   += 3
        scores["Moderna"]    += 2
    if has_m7:
        scores["Íntima"]     += 2
        scores["Melancólica"] += 1
        scores["Moderna"]    += 1
    if has_dom7:
        scores["Cálida"]     += 2
        scores["Enérgica"]   += 1
    if has_9_11:
        scores["Elegante"]   += 2
        scores["Moderna"]    += 2
        scores["Soñadora"]   += 1
    if has_power:
        scores["Enérgica"]   += 3
        scores["Oscura"]     += 1

    # ─── 5. DENSIDAD ARMÓNICA ─────────────────────────────────────────────────
    n_unique = len(unique_chords)
    if n_unique >= 6:
        scores["Moderna"]    += 2
        scores["Cinematográfica"] += 1
    elif n_unique <= 3:
        scores["Orgánica"]   += 2
        scores["Íntima"]     += 1

    # ─── 6. PATRONES DE PROGRESIÓN ROMANA ────────────────────────────────────
    # Inferimos los romanos de la progresión registrada
    progression = infer_progression(chord_string, tonality) if chord_string and tonality else ""
    prog_upper = progression.upper()

    # Patrones épicos/cinematográficos
    if re.search(r'\bI\b.*\bVII\b|\bVI\b.*\bIII\b|\bIII\b.*\bVII\b', prog_upper):
        scores["Épica"]          += 3
        scores["Cinematográfica"] += 2
    # Pop emocional (I-V-vi-IV o variantes)
    if re.search(r'\bI\b.*\bV\b.*\bVI\b.*\bIV\b', prog_upper):
        scores["Alegre"]         += 2
        scores["Nostálgica"]     += 2
    # Oscuro menor natural (i-iv-v o i-VI-III-VII)
    if re.search(r'\bI\b.*\bIV\b.*\bV\b', prog_upper) and is_minor:
        scores["Oscura"]         += 3
    if re.search(r'\bI\b.*\bVI\b.*\bIII\b.*\bVII\b', prog_upper) and is_minor:
        scores["Épica"]          += 2
        scores["Oscura"]         += 1
    # Descenso cromatico (i-VII-VI-V —flamenco/drama)
    if re.search(r'\bI\b.*\bVII\b.*\bVI\b.*\bV\b', prog_upper):
        scores["Tensa"]          += 3
        scores["Cinematográfica"] += 2
        scores["Oscura"]         += 1
    # Jazz (ii-V-I)
    if re.search(r'\bII\b.*\bV\b.*\bI\b', prog_upper):
        scores["Elegante"]       += 3
        scores["Cálida"]         += 1
    # Plagal (IV-I) — religioso/organic
    if re.search(r'\bIV\b.*\bI\b(?!\bV)', prog_upper):
        scores["Orgánica"]       += 2
        scores["Cálida"]         += 1
    # Loop modal (sin V) — estático/meditativo
    if 'V' not in prog_upper and n_unique >= 3:
        scores["Flotante"]       += 2
        scores["Soñadora"]       += 1

    # ─── 7. PRÉSTAMO MODAL ───────────────────────────────────────────────────
    # Detectar acordes de modo opuesto al tónico
    if chord_string and tonality:
        chord_roots = set()
        mode_mix = False
        for c in chords:
            r, q, _ = parse_chord_root_and_quality(c)
            if r and q:
                chord_roots.add((r, q))
        minor_chords = sum(1 for _, q in chord_roots if q == 'minor')
        major_chords = sum(1 for _, q in chord_roots if q == 'major')
        if minor_chords > 0 and major_chords > 0:
            ratio = min(minor_chords, major_chords) / max(minor_chords, major_chords)
            if ratio > 0.3:
                scores["Cinematográfica"] += 3
                scores["Moderna"]         += 2
                scores["Nostálgica"]      += 1

    # ─── SELECCIÓN FINAL ─────────────────────────────────────────────────────
    # Ordenar por score y devolver hasta 3 etiquetas con score > 0
    ranked = sorted(
        [(label, sc) for label, sc in scores.items() if sc > 0],
        key=lambda x: x[1],
        reverse=True
    )

    top_labels = [label for label, _ in ranked[:3]]

    if not top_labels:
        return "Melancólica" if is_minor else "Alegre"

    return ", ".join(top_labels)

def normalize_text_for_match(s):
    """Normalize text for comparing song titles and artist names reliably."""
    if not s:
        return ""
    import unicodedata
    import re
    # Strip diacritics / accents
    s = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('utf-8')
    # Replace symbols and conjunctions with 'and'
    s = re.sub(r'\s*&\s*', ' and ', s)
    s = re.sub(r'\s*\+\s*', ' and ', s)
    # Remove smart quotes and apostrophes
    s = re.sub(r'[\u2018\u2019\u0060\u00B4\']', '', s)
    # Remove punctuation
    s = re.sub(r'[^a-zA-Z0-9]', '', s.lower())
    return s

def clean_ug_search_term(text):
    """Clean a search term for Ultimate Guitar search engine."""
    if not text:
        return ""
    import unicodedata
    import re
    # Remove parenthetical / bracket info like (Remastered 2021), (feat. XYZ), (Live...), etc.
    cleaned = re.sub(
        r'\s*[\(\[\{][^\)\]\}]*(?:feat\.|ft\.|featuring|remaster|live|acoustic|deluxe|version|edit|bonus|official|mono|stereo|anniversary|radio)[^\)\]\}]*[\)\]\}]',
        '',
        text,
        flags=re.IGNORECASE
    )
    # Remove trailing dash suffixes like ' - Remastered 2011', ' - Live at Wembley', ' - Single Version', ' - 12" Version'
    cleaned = re.sub(
        r'\s*-\s*(?:\d{4}\s+)?(?:remaster.*|live.*|acoustic.*|radio edit.*|deluxe.*|bonus track.*|\d+[\"\']?\s+version.*)$',
        '',
        cleaned,
        flags=re.IGNORECASE
    )
    # Replace & and + with 'and' for UG's search engine
    cleaned = re.sub(r'\s*&\s*', ' and ', cleaned)
    cleaned = re.sub(r'\s*\+\s*', ' and ', cleaned)
    # Normalize unicode / diacritics
    cleaned = unicodedata.normalize('NFKD', cleaned).encode('ASCII', 'ignore').decode('utf-8')
    # Remove quotes
    cleaned = re.sub(r'[\u2018\u2019\u201C\u201D\"\']', '', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()

def build_ug_queries(artist, title):
    """Generate search query candidates in priority order to maximize UG match rate."""
    import re
    import unicodedata
    queries = []
    clean_a = clean_ug_search_term(artist)
    clean_t = clean_ug_search_term(title)

    # 1. Cleaned artist + cleaned title (primary & most effective)
    if clean_a and clean_t:
        queries.append(f"{clean_a} {clean_t}")
    elif clean_t:
        queries.append(clean_t)

    # 2. Artist & title with '&' normalized to 'and' and accents stripped (keeps any other title words)
    art_and = re.sub(r'\s*&\s*', ' and ', artist or '')
    tit_and = re.sub(r'\s*&\s*', ' and ', title or '')
    tit_and_norm = unicodedata.normalize('NFKD', tit_and).encode('ASCII', 'ignore').decode('utf-8').strip()
    art_and_norm = unicodedata.normalize('NFKD', art_and).encode('ASCII', 'ignore').decode('utf-8').strip()
    if art_and_norm and tit_and_norm:
        q2 = f"{art_and_norm} {tit_and_norm}"
        if q2 not in queries:
            queries.append(q2)

    # 3. Cleaned title alone (fallback if artist name differs on UG)
    if clean_t and clean_t not in queries:
        queries.append(clean_t)

    # 4. Raw query as last fallback
    raw_q = f"{artist} {title}".strip()
    if raw_q not in queries:
        queries.append(raw_q)

    return queries

def match_ug_song(target_artist, target_title, cand_artist, cand_title):
    """Match candidate song and artist against targets with fuzzy and token fallback."""
    norm_t_a = normalize_text_for_match(target_artist)
    norm_t_t = normalize_text_for_match(target_title)
    norm_c_a = normalize_text_for_match(cand_artist)
    norm_c_t = normalize_text_for_match(cand_title)
    norm_clean_t_t = normalize_text_for_match(clean_ug_search_term(target_title))

    # Artist match: exact, substring, or fuzzy
    art_match = False
    if not norm_t_a:
        art_match = True
    elif (norm_t_a in norm_c_a) or (norm_c_a in norm_t_a):
        art_match = True
    elif norm_t_a.startswith('the') and norm_t_a[3:] in norm_c_a:
        art_match = True
    elif norm_c_a.startswith('the') and norm_c_a[3:] in norm_t_a:
        art_match = True
    else:
        try:
            from rapidfuzz import fuzz
            if fuzz.ratio(norm_t_a, norm_c_a) >= 80:
                art_match = True
        except Exception:
            pass

    # Title match: exact, substring, clean substring, or fuzzy
    tit_match = False
    if not norm_t_t:
        tit_match = True
    elif norm_t_t == norm_c_t:
        tit_match = True
    elif (norm_t_t in norm_c_t) or (norm_c_t in norm_t_t):
        short_len = min(len(norm_t_t), len(norm_c_t))
        long_len = max(len(norm_t_t), len(norm_c_t))
        if short_len >= 5 or (short_len / long_len) >= 0.5:
            tit_match = True
        elif norm_c_t.startswith(norm_t_t) or norm_t_t.startswith(norm_c_t):
            tit_match = True
    elif norm_clean_t_t and ((norm_clean_t_t in norm_c_t) or (norm_c_t in norm_clean_t_t)):
        short_len = min(len(norm_clean_t_t), len(norm_c_t))
        long_len = max(len(norm_clean_t_t), len(norm_c_t))
        if short_len >= 5 or (short_len / long_len) >= 0.5:
            tit_match = True
        elif norm_c_t.startswith(norm_clean_t_t) or norm_clean_t_t.startswith(norm_c_t):
            tit_match = True
    else:
        try:
            from rapidfuzz import fuzz
            if fuzz.token_sort_ratio(target_title, cand_title) >= 80:
                tit_match = True
            elif norm_clean_t_t and fuzz.ratio(norm_clean_t_t, norm_c_t) >= 80:
                tit_match = True
        except Exception:
            pass

    return art_match and tit_match

def map_native_difficulty(difficulty_raw):
    """
    Mapea la dificultad nativa de Ultimate Guitar / tablatura a los niveles del sistema:
    'Baja', 'Media', 'Alta' o None si no está definida o reconocida.
    """
    if not difficulty_raw or not isinstance(difficulty_raw, str):
        return None
    d = difficulty_raw.strip().lower()
    if not d or d in ["none", "null", "undefined", "unknown", "—", "-"]:
        return None
    if any(k in d for k in ["beginner", "novice", "easy", "baja", "fácil", "facil", "principiante"]):
        return "Baja"
    if any(k in d for k in ["intermediate", "medium", "media", "intermedio", "intermedia"]):
        return "Media"
    if any(k in d for k in ["advanced", "alta", "avanzado", "avanzada", "hard", "difícil", "dificil"]):
        return "Alta"
    return None

def _ug_pro_lyrics_to_chords_format(raw):
    """The Official/Pro lyrics wrap every syllable in [syllable ...] tags and give chords an app id; strip both so
    the regular chord-sheet parser can read them."""
    import re
    raw = re.sub(r'\[/?syllable[^\]]*\]', '', raw or '')
    return re.sub(r'\[ch\s[^\]]*\]', '[ch]', raw)


def _ug_analyse_tab(artist, title, res, cleaned_chords, lyrics_with_chords, native_difficulty, label, tab_url, source):
    """One selectable UG version: its chords plus the harmonic metadata derived from them."""
    import re
    try:
        from rapidfuzz import fuzz
        confidence = round(fuzz.token_sort_ratio(f"{artist} {title}", f"{res.get('artist_name', artist)} {res.get('song_name', title)}") / 100.0, 2)
    except Exception:
        confidence = 0.95
    raw_chords_list = re.findall(r'\b[A-G][#b]?(?:[a-zA-Z0-9#b\-\+]*(?:/[A-G][#b]?)?)(?!\w)', cleaned_chords)
    filtered = [c for c in raw_chords_list if c.lower() not in ['intro', 'verse', 'chorus', 'bridge', 'outro', 'solo', 'pre', 'interlude']]
    tonality = detect_key_from_chords(filtered)
    return {
        "artist": res.get("artist_name", artist),
        "title": res.get("song_name", title),
        "chord": cleaned_chords,
        "tonality": tonality,
        "progression": infer_progression(cleaned_chords, tonality),
        "complex": map_native_difficulty(native_difficulty) or infer_complexity(cleaned_chords, tonality),
        "style": infer_emotional_style(cleaned_chords, tonality),
        "confidence": confidence,
        "source": source,
        "lyrics_with_chords": lyrics_with_chords,
        "has_lyrics": bool(lyrics_with_chords),
        "version_label": label,
        "rating": float(res.get("rating") or 0),
        "votes": int(res.get("votes") or 0),
        "tab_url": tab_url,
    }


def _ug_collect_candidates(results, artist, title, headers, cj, extract_tab_id):
    """Every usable version of the song on UG (the Official one and the community chord sheets), best first.
    A version with lyrics beats one without; then the most popular wins. The caller picks the first one and the
    UI lets the user choose another, showing which have lyrics."""
    import json
    import re
    import html as html_lib
    import requests
    from concurrent.futures import ThreadPoolExecutor

    def popularity(r):
        rating = float(r.get("rating") or 0)
        votes = int(r.get("votes") or 0)
        return rating * (votes ** 0.5) if votes > 0 else rating * 0.1

    def kind(r):
        t = (r.get("type") or "").lower()
        mt = (r.get("marketing_type") or "").lower()
        if t in ("official", "pro", "guitar pro") or mt in ("official", "tabpro"):
            return "official"
        if t == "chords" or (r.get("type_name") or "").lower() == "chords":
            return "chords"
        return "other"

    official = [r for r in results if kind(r) == "official"]
    chords = sorted([r for r in results if kind(r) == "chords" and r.get("tab_url")], key=popularity, reverse=True)
    if not chords:
        chords = sorted([r for r in results if kind(r) == "other" and r.get("tab_url") and not r.get("marketing_type")
                         and (r.get("type") or "").lower() not in ("power",)], key=popularity, reverse=True)

    def load_official(r):
        tab_id = extract_tab_id(r.get("tab_url", "")) or str(r.get("tab_id") or "")
        if not tab_id:
            return None
        pro = fetch_ug_pro_meta(tab_id, artist, title)
        if not (pro and pro.get("cleaned", "").strip()):
            return None
        lyrics = extract_lyrics_with_chords(_ug_pro_lyrics_to_chords_format(pro.get("lyrics_raw", "")))
        return _ug_analyse_tab(artist, title, r, pro["cleaned"], lyrics, r.get("difficulty") or r.get("ug_difficulty") or "",
                               "Oficial", r.get("tab_url") if str(r.get("tab_url", "")).startswith("https://tabs.") else "", "Ultimate Guitar (Official)")

    def load_community(r):
        try:
            tab_res = requests.get(r["tab_url"], headers=headers, cookies=cj, timeout=10)
            if tab_res.status_code != 200:
                return None
            m = re.search(r'class="js-store"[^>]*data-content="([^"]+)"', tab_res.text) or \
                re.search(r'data-content="([^"]+)"[^>]*class="js-store"', tab_res.text)
            if not m:
                return None
            page = json.loads(html_lib.unescape(m.group(1))).get("store", {}).get("page", {}).get("data", {})
            info, view = page.get("tab", {}), page.get("tab_view", {})
            raw = view.get("wiki_tab", {}).get("content", "")
            if not raw:
                return None
            cleaned = clean_ug_content(raw)
            tab_type = (info.get("type") or info.get("type_name") or r.get("type") or "").lower()
            if not (cleaned and cleaned.strip()) and "tab" in tab_type and "chord" not in tab_type:
                cleaned = tab_to_chords(raw)
            if not (cleaned and cleaned.strip()):
                return None
            lyrics = None
            if ("chord" in tab_type or tab_type == "") and "[ch]" in raw.lower():
                lyrics = extract_lyrics_with_chords(raw)
            version = r.get("version")
            label = (r.get("type") or "Acordes") + (f" v{version}" if version else "")
            native = view.get("ug_difficulty") or info.get("difficulty") or r.get("difficulty") or ""
            return _ug_analyse_tab(artist, title, r, cleaned, lyrics, native, label, r["tab_url"], "Ultimate Guitar")
        except Exception:
            return None

    jobs = []
    if official:
        official.sort(key=lambda r: (str(r.get("tab_url", "")).startswith("https://tabs."), float(r.get("rating") or 0)), reverse=True)
        jobs.append((load_official, official[0]))
    jobs += [(load_community, r) for r in chords[:5]]
    if not jobs:
        return []
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        loaded = list(pool.map(lambda j: j[0](j[1]), jobs))
    found = [c for c in loaded if c]
    found.sort(key=lambda c: (c["has_lyrics"], (c["rating"] * (c["votes"] ** 0.5)) if c["votes"] else c["rating"] * 0.1), reverse=True)
    return found



def fetch_ug_chords(artist, title):
    import urllib.parse
    import requests
    import json
    import re
    import html as html_lib

    cj = None
    try:
        import browser_cookie3
        cj = browser_cookie3.chrome(domain_name='ultimate-guitar.com')
    except Exception:
        try:
            cj = browser_cookie3.load(domain_name='ultimate-guitar.com')
        except Exception:
            pass

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    }

    queries = build_ug_queries(artist, title)

    for query in queries:
        try:
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://www.ultimate-guitar.com/search.php?search_type=title&value={encoded_query}&order=rating_desc"

            # Search Ultimate Guitar. Its fuzzy ranking can push the right song to page 2 or 3
            # (e.g. "I Wish You Were A Girl" is buried under "Wish You Were Here"), so keep paging until it shows up.
            results = []
            for page in range(1, 4):
                page_url = search_url if page == 1 else f"{search_url}&page={page}"
                res = requests.get(page_url, headers=headers, cookies=cj, timeout=10)
                if res.status_code != 200:
                    break

                match = re.search(r'class="js-store"[^>]*data-content="([^"]+)"', res.text)
                if not match:
                    match = re.search(r'data-content="([^"]+)"[^>]*class="js-store"', res.text)
                if not match:
                    break

                decoded_json = html_lib.unescape(match.group(1))
                parsed_data = json.loads(decoded_json)

                page_data = parsed_data.get("store", {}).get("page", {}).get("data", {})
                all_results = page_data.get("results", [])
                if not all_results:
                    break

                # Filter results using robust matching
                results = [
                    r for r in all_results
                    if match_ug_song(artist, title, r.get("artist_name", ""), r.get("song_name", ""))
                ]
                if results:
                    break

            if not results:
                continue

            def extract_tab_id(url):
                """Extract numeric tab ID from /tab/...-ID or pro/?...tab_id=ID URLs."""
                m = re.search(r'-(\d+)$', url.split('?')[0])
                if m:
                    return m.group(1)
                m = re.search(r'[?&]tab_id=(\d+)', url)
                if m:
                    return m.group(1)
                return None

            candidates = _ug_collect_candidates(results, artist, title, headers, cj, extract_tab_id)
            if not candidates:
                continue

            top_cand = dict(candidates[0])
            top_cand["found"] = True
            if len(candidates) > 1:
                top_cand["candidates"] = candidates
            return top_cand
        except Exception as e:
            print(f"Error fetching from UG for query '{query}': {e}")
            continue

    return None



def fetch_ug_pro_meta(tab_id, artist, title):
    """
    Fetches chord content from the Ultimate Guitar pro/meta API for Official/Pro/Guitar Pro tabs.
    Uses Chrome session cookies for authenticated access (requires UG Pro+ subscription).
    Returns a dict with 'lyrics' (raw chord+lyric text) and 'tonality', or None on failure.
    """
    import requests, json, re, html as html_lib

    try:
        cj = None
        try:
            import browser_cookie3
            cj = browser_cookie3.chrome(domain_name='ultimate-guitar.com')
        except Exception:
            try:
                cj = browser_cookie3.load(domain_name='ultimate-guitar.com')
            except Exception:
                pass

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": f"https://tabs.ultimate-guitar.com/tab/motorama/alps-official-{tab_id}",
        }

        url = f"https://api-web.ultimate-guitar.com/v1/tab/pro/meta?id={tab_id}"
        res = requests.get(url, headers=headers, cookies=cj, timeout=10)
        if res.status_code != 200:
            return None

        data = res.json()
        raw_lyrics = data.get("lyrics", "")
        if not raw_lyrics:
            return None

        tonality = data.get("meta", {}).get("tuning", "")

        # Extract chord names from [ch app="..."]CHORD[/ch] tags
        # and section markers like [Intro], [Verse 1], etc.
        def clean_pro_lyrics(text):
            # Pro/Official metadata format in UG has section tags like [Intro], [Verse 1], [Chorus]
            # and chord tags like [ch app="..."]CHORD[/ch] or [ch]CHORD[/ch].
            section_pattern = r'(\[(?!ch\b)(?!/ch\])(?!tab\])(?!/tab\])(?!syllable\b)(?!/syllable\])[^\]]+\])'
            parts = re.split(section_pattern, text, flags=re.IGNORECASE)
            
            formatted_parts = []
            first_text = parts[0]
            first_chords = re.findall(r'\[ch(?: [^\]]*)?\](.*?)\[/ch\]', first_text)
            if first_chords:
                formatted_parts.append('<intro> ' + ' '.join(first_chords))

            for i in range(1, len(parts), 2):
                if i >= len(parts):
                    break
                sec_name = parts[i].strip()
                clean_sec = sec_name.lower().replace(' ', '_').replace('-', '_').replace('[', '<').replace(']', '>')
                sec_content = parts[i+1] if (i+1) < len(parts) else ''
                chords = re.findall(r'\[ch(?: [^\]]*)?\](.*?)\[/ch\]', sec_content)
                if chords:
                    formatted_parts.append(f'{clean_sec} ' + ' '.join(chords))

            if formatted_parts:
                return ' '.join(formatted_parts)

            # Fallback if no [ch] tags found:
            chord_pat = re.compile(r'\b[A-G][#b]?(?:[a-zA-Z0-9#b\-\+]*(?:/[A-G][#b]?)?)(?!\w)')
            clean_txt = re.sub(r'\[syllable[^\]]*\]', '', text)
            clean_txt = re.sub(r'\[/syllable\]', '', clean_txt)
            clean_txt = re.sub(r'\[/?tab\]', '', clean_txt)
            lines = [l.strip() for l in clean_txt.splitlines() if l.strip()]
            res_parts = []
            for line in lines:
                if line.startswith('[') and line.endswith(']'):
                    tag = line.strip('[]').lower().replace(' ', '_').replace('-', '_')
                    res_parts.append(f'<{tag}>')
                else:
                    found = chord_pat.findall(line)
                    if found:
                        res_parts.append(' '.join(found))
            return ' '.join(res_parts)

        cleaned = clean_pro_lyrics(raw_lyrics)
        ug_tonality = data.get("meta", {}).get("tuning", "")
        # Get the declared tonality from pro/meta if possible
        tab_tonality = ""
        # It's not directly exposed; we'll detect from chords
        
        return {
            "lyrics_raw": raw_lyrics,
            "cleaned": cleaned,
            "tonality_hint": ug_tonality,
            "tab_id": tab_id,
            "artist": artist,
            "title": title,
        }
    except Exception as e:
        print(f"fetch_ug_pro_meta error: {e}")
        return None

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


# ── Chord sheet import from a PDF (chords printed above the lyrics) ─────────────
_PDF_CHORD_RE = re.compile(
    r'^[A-G][#b]?(?:maj|Maj|MAJ|min|Min|dim|aug|sus|add|[mM0-9#b+\-°øΔ()])*(?:/[A-G][#b]?)?$')
_PDF_SECTION_RE = re.compile(
    r'^\[?\s*(intro|verse|chorus|pre[\s-]?chorus|bridge|outro|solo|interlude|instrumental|refrain|hook|'
    r'estribillo|puente|estrofa|verso|coro)\s*\d*\s*(?:\(.*?\))?\s*\]?\s*:?$', re.IGNORECASE)

def normalize_pdf_chord(chord):
    """Chord sheets write major sevenths as M7/Maj7/Δ; this app spells them maj7 (also maj9, maj13...)."""
    m = re.match(r'^([A-G][#b]?)(.*?)(/[A-G][#b]?)?$', chord)
    if not m:
        return chord
    root, suffix, bass = m.group(1), m.group(2), m.group(3) or ""
    suffix = re.sub(r'Δ\d*', 'maj7', suffix)
    suffix = re.sub(r'(?i:maj)', 'maj', suffix)
    suffix = re.sub(r'M(?![a-z])', 'maj', suffix)
    suffix = re.sub(r'(?i:min)', 'm', suffix)
    return root + suffix + bass

def _pdf_rows(pdf_bytes):
    """Words of every page grouped into visual rows: [{page, top, words:[{x0,x1,text,font,size}]}]."""
    import io
    import pdfplumber
    rows = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pi, page in enumerate(pdf.pages):
            words = page.extract_words(extra_attrs=["fontname", "size"], x_tolerance=2)
            words.sort(key=lambda w: (w["top"], w["x0"]))
            current = None
            for w in words:
                item = {"x0": w["x0"], "x1": w["x1"], "text": w["text"], "font": w["fontname"], "size": w["size"]}
                if current and current["page"] == pi and abs(w["top"] - current["top"]) <= 3:
                    current["words"].append(item)
                else:
                    current = {"page": pi, "top": w["top"], "words": [item]}
                    rows.append(current)
            for r in rows:
                r["words"].sort(key=lambda x: x["x0"])
    return rows

def parse_chord_pdf(pdf_bytes, sel_artist="", sel_title=""):
    """Reads a chord PDF and returns a suggestion shaped like the Ultimate Guitar ones, or None."""
    from collections import Counter
    import statistics

    rows = _pdf_rows(pdf_bytes)
    if not rows:
        return None

    for r in rows:
        r["text"] = " ".join(w["text"] for w in r["words"])

    # 1. Which rows are chord rows: every token looks like a chord and (when the sheet uses a distinct
    #    font for chords) is set in the chord font
    cand = [all(_PDF_CHORD_RE.match(w["text"]) for w in r["words"]) for r in rows]
    chord_fonts = Counter(w["font"] for r, c in zip(rows, cand) if c for w in r["words"])
    lyric_fonts = Counter(w["font"] for r, c in zip(rows, cand) if not c for w in r["words"])
    chord_font = chord_fonts.most_common(1)[0][0] if chord_fonts else None
    lyric_font = lyric_fonts.most_common(1)[0][0] if lyric_fonts else None
    use_font = chord_font is not None and chord_font != lyric_font
    for r, c in zip(rows, cand):
        r["is_chord"] = c and (not use_font or all(w["font"] == chord_font for w in r["words"]))

    if not any(r["is_chord"] for r in rows):
        return None

    # 2. Header (title / BPM / key) above the first chord row, and stray page numbers
    meta = {"bpm": None, "key": None, "title_line": None}
    first_chord = next(i for i, r in enumerate(rows) if r["is_chord"])
    keep = []
    for i, r in enumerate(rows):
        if re.fullmatch(r"\d{1,3}", r["text"].strip()):
            continue
        if i < first_chord and r["page"] == 0:
            bpm = re.search(r"\bBPM\s*[:\-]?\s*(\d{2,3})", r["text"], re.IGNORECASE)
            key = re.search(r"\bKey\s*[:\-]?\s*([A-G][#b]?)\s*(m(?:in(?:or)?)?|maj(?:or)?)?\b", r["text"], re.IGNORECASE)
            if bpm or key:
                if bpm:
                    meta["bpm"] = int(bpm.group(1))
                if key:
                    meta["key"] = (key.group(1), (key.group(2) or "").lower())
                continue
            if meta["title_line"] is None and " - " in r["text"] and len(r["text"]) <= 90:
                meta["title_line"] = r["text"]
                continue
        keep.append(r)
    rows = keep

    # 3. Pair each chord row with the lyric row right below it (when it is close enough to belong to it)
    def is_lyric(r):
        return not r["is_chord"] and not _PDF_SECTION_RE.match(r["text"].strip())

    pair_gaps = [rows[i + 1]["top"] - rows[i]["top"] for i in range(len(rows) - 1)
                 if rows[i]["is_chord"] and is_lyric(rows[i + 1]) and rows[i + 1]["page"] == rows[i]["page"]]
    max_pair_gap = 1.35 * statistics.median(pair_gaps) if pair_gaps else 0

    after_lyric_gaps = [rows[i + 1]["top"] - rows[i]["top"] for i in range(len(rows) - 1)
                        if is_lyric(rows[i]) and rows[i + 1]["page"] == rows[i]["page"]]
    has_headings = any(_PDF_SECTION_RE.match(r["text"].strip()) and not r["is_chord"] for r in rows)
    paragraph_gap = 1.6 * statistics.median(after_lyric_gaps) if len(after_lyric_gaps) >= 6 else None
    if paragraph_gap is not None and not any(g > paragraph_gap for g in after_lyric_gaps):
        paragraph_gap = None   # evenly spaced sheet: no paragraphs to split on

    # how far a chord row usually sits below the row above it (used at the top of a page, where there is none)
    above_gaps = [rows[i]["top"] - rows[i - 1]["top"] for i in range(1, len(rows))
                  if rows[i]["is_chord"] and rows[i - 1]["page"] == rows[i]["page"]]
    typical_above = statistics.median(above_gaps) if above_gaps else None

    def belongs_to_lyric_below(idx):
        """Chord row idx belongs to the lyric row after it when they sit close together: tighter than
        the usual chord→lyric spacing allows, or at least closer than the row above is to this chord row."""
        a, b = rows[idx], rows[idx + 1] if idx + 1 < len(rows) else None
        if b is None or not is_lyric(b) or b["page"] != a["page"]:
            return False
        gap = b["top"] - a["top"]
        if gap <= max_pair_gap:
            return True
        above = a["top"] - rows[idx - 1]["top"] if idx > 0 and rows[idx - 1]["page"] == a["page"] else typical_above
        return above is not None and gap < above

    def word_index_for(chord_word, lyric_words):
        size = chord_word["size"] or 10
        near = [i for i, w in enumerate(lyric_words) if w["x0"] - 0.45 * size <= chord_word["x0"] <= w["x1"]]
        if near:
            return min(near, key=lambda i: abs(lyric_words[i]["x0"] - chord_word["x0"]))
        return min(range(len(lyric_words)), key=lambda i: abs(lyric_words[i]["x0"] - chord_word["x0"]))

    def chord_tag(text):
        return f"[ch]{normalize_pdf_chord(text)}[/ch]"

    # 4. Rebuild the sheet as Ultimate-Guitar-style markup and reuse the existing parsers
    out = []
    part = 0
    heading_pending = not has_headings   # no printed headings: open with a single section instead of "Intro"
    prev = None
    i = 0
    while i < len(rows):
        r = rows[i]
        text = r["text"].strip()
        if not r["is_chord"] and _PDF_SECTION_RE.match(text):
            out.append(f"[{text.strip('[]: ').title()}]")
            heading_pending = False
            prev = r
            i += 1
            continue
        if not has_headings and paragraph_gap and prev is not None and prev["page"] == r["page"] \
                and is_lyric(prev) and r["top"] - prev["top"] > paragraph_gap:
            part += 1
            out.append(f"[Parte {part + 1}]")
            heading_pending = False
        if heading_pending:
            out.append("[Song]" if paragraph_gap is None else "[Parte 1]")
            heading_pending = False
        if r["is_chord"]:
            # Several chord rows in a row (the sheet puts each chord line on its own row). Only the last
            # one sits right above a lyric; the earlier ones are lead-in chords for that same lyric line
            k = i
            while k + 1 < len(rows) and rows[k + 1]["is_chord"]:
                k += 1
            pairs_below = belongs_to_lyric_below(k)
            lead_rows = rows[i:k] if pairs_below else rows[i:k + 1]
            lead_words = [w for row in lead_rows for w in row["words"]]
            attach = pairs_below and len(lead_rows) <= 3 and len(lead_words) <= 8
            if lead_rows and not attach:
                # too many to squeeze onto one lyric line: show them as plain chord lines
                for n in range(0, len(lead_words), 16):
                    out.append("[tab]" + "  ".join(chord_tag(w["text"]) for w in lead_words[n:n + 16]) + "[/tab]")
                prev = lead_rows[-1]
                if not pairs_below:
                    i = k + 1
                    continue
                lead_words = []
            r = rows[k]
            i = k
            if belongs_to_lyric_below(i):
                nxt = rows[i + 1]
                lyric_words = nxt["words"]
                cols, c = [], 0
                for w in lyric_words:
                    cols.append(c)
                    c += len(w["text"]) + 1
                line, spaces = "", 0
                for cw in lead_words + r["words"]:
                    col = 0 if cw in lead_words else cols[word_index_for(cw, lyric_words)]
                    pad = max(0, col - spaces)
                    line += " " * pad + chord_tag(cw["text"])
                    spaces += pad
                lyric = " ".join(w["text"] for w in lyric_words).replace("[", "(").replace("]", ")").replace("\u2019", "'")
                out.append(f"[tab]{line}\n{lyric}[/tab]")
                prev = nxt
                i += 2
                continue
            out.append("[tab]" + "  ".join(chord_tag(w["text"]) for w in r["words"]) + "[/tab]")
        else:
            out.append(text.replace("[", "(").replace("]", ")").replace("\u2019", "'"))
        prev = r
        i += 1

    raw = "\n".join(out)
    chord_string = clean_ug_content(raw)
    if not chord_string.strip():
        return None
    lyrics = extract_lyrics_with_chords(raw)

    # 5. Metadata: key from the header when printed, otherwise detected from the chords
    chords_list = clean_and_extract_chords(chord_string)
    if meta["key"]:
        root, mode = meta["key"]
        tonality = f"{root[0].upper()}{root[1:]} {'Minor' if mode.startswith('m') and not mode.startswith('maj') else 'Major'}"
    else:
        tonality = detect_key_from_chords(chords_list)

    artist, title = (sel_artist, sel_title)
    if meta["title_line"]:
        left, right = meta["title_line"].split(" - ", 1)
        artist, title = left.strip(), right.strip()
    try:
        from rapidfuzz import fuzz
        confidence = round(fuzz.token_sort_ratio(f"{sel_artist} {sel_title}", f"{artist} {title}") / 100.0, 2) \
            if sel_artist and sel_title and meta["title_line"] else 1.0
    except Exception:
        confidence = 1.0

    return {
        "found": True,
        "artist": artist,
        "title": title,
        "chord": chord_string,
        "tonality": tonality,
        "progression": infer_progression(chord_string, tonality),
        "complex": infer_complexity(chord_string, tonality),
        "style": infer_emotional_style(chord_string, tonality),
        "confidence": confidence,
        "source": "PDF",
        "lyrics_with_chords": lyrics,
        "bpm": meta["bpm"],
    }

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

def infer_complexity(chord_string, tonality=None):
    if not chord_string:
        return "Baja"
        
    filtered = clean_and_extract_chords(chord_string)
    unique_chords = list(set(filtered))
    
    if not unique_chords:
        return "Baja"
        
    import re
    # 1. Acordes alterados / complejos (tensiones alteradas, disminuidos, aumentados, m7b5, extensiones 11/13):
    is_complex_chord = lambda c: bool(re.search(r'(dim|aug|m7b5|7b5|7\#5|7b9|7\#9|11|13|\balt\b|[A-G][#b]?alt|°|ø|\+)', c, re.IGNORECASE))
    has_complex = any(is_complex_chord(c) for c in unique_chords)
    
    # 2. Acordes intermedios (7ªs, maj7, 9ªs, suspendidos, add, 6ªs, slash chords/inversiones):
    is_intermediate_chord = lambda c: bool(re.search(r'(maj7|maj9|m7|min7|m9|7|9|sus|add|6|\/)', c, re.IGNORECASE))
    has_intermediate = any(is_intermediate_chord(c) for c in unique_chords)
    
    num_unique = len(unique_chords)
    
    # Alta: 8+ acordes únicos, o acordes complejos con 5+ acordes, o 7+ acordes con extensiones
    if num_unique >= 8 or (has_complex and num_unique >= 5) or (has_intermediate and num_unique >= 7):
        return "Alta"
    # Media-Alta: acordes complejos con 3-4 acordes, o 6 acordes con extensiones intermedias, o 6+ acordes distintos
    elif (has_complex and num_unique >= 3) or (has_intermediate and num_unique >= 6) or num_unique >= 6:
        return "Media-Alta"
    # Media: 4-5 acordes con extensiones intermedias (maj7, sus, add, 7, slash chords) o 5 acordes básicos
    elif (has_intermediate and num_unique >= 4) or num_unique >= 5:
        return "Media"
    # Baja: 1-4 acordes básicos (progresiones estándar) o 1-3 tríadas con extensiones ligeras
    else:
        return "Baja"

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




def strip_latex(text):
    """Models sometimes wrap chords in LaTeX ($Dm^7$, $C^{maj7}$): turn them back into plain text (Dm7, Cmaj7)."""
    def plain(m):
        inner = m.group(1)
        inner = inner.replace("\\sharp", "#").replace("\\flat", "b").replace("\\natural", "")
        inner = re.sub(r"[\^_]\{([^}]*)\}", r"\1", inner)
        inner = re.sub(r"[\^_](\w+)", r"\1", inner)
        return re.sub(r"[{}\\]", "", inner)
    return re.sub(r"\$([^$\n]+)\$", plain, text or "")

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
            
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return jsonify({"error": "No se ha configurado la GEMINI_API_KEY en el servidor."}), 500

        prompt = f"""Eres un experto en teoría musical, armonía funcional y guitarrista profesional.
Necesito que escribas una guía de improvisación para la canción "{title}" de "{artist}".
La tonalidad es: {tonality}
La progresión de acordes es: {progression}

Genera la respuesta en formato Markdown con esta estructura exacta (pero sin título principal):
1. **La escala más segura y que siempre funciona**: Menciona la escala principal, sus notas y por qué funciona.
2. **Versión más rock/pop y fácil de tocar**: Menciona la pentatónica correspondiente, sus notas y para qué sirve.
3. **Enfoques por secciones (más avanzado y con más color)**: Crea una tabla Markdown con las columnas: Acorde, Escala recomendada, Notas principales, Comentario. Desglosa acorde por acorde o grupos de acordes.

FORMATO DE TEXTO: escribe los acordes y grados en texto plano (Dm7, Cmaj7, G11, iv7, VII11, IIImaj7). NUNCA uses LaTeX ni símbolos de dólar ($), ni superíndices con ^ ni llaves.

REGLAS OBLIGATORIAS para la columna "Escala recomendada" de la tabla:
- Acorde dominante 7 (ej: A7, E7 como I7 o IV7): usa "X Mixolidio" (o la Dórica de la tonalidad como alternativa). NUNCA uses Lidia ni Mayor/Jónica para acordes dominantes 7.
- Acorde dominante con tensiones alteradas (ej: V7#9, V7b9, V7b5, V7alt): usa "X Alterada".
- Acorde menor 7 (ej: Am7, Dm7): usa "X Dórico" o "X Eólico".
- Acorde mayor 7 (ej: Cmaj7, Fmaj7): usa "X Jónica" o "X Lidia".
- Turnarounds o secuencias de varios acordes: usa "X Blues + Cromatismos" o "X Escala Blues".
- Acorde sus o sus4: usa "X Mixolidio".
- SIEMPRE indica la raíz correcta de la escala en la columna "Escala recomendada" (ej: "B Alterada", "E Mixolidio", "A Mixolidio").
- Cada fila de la tabla DEBE tener el formato "NOTA ESCALA" en la columna de escala (ej: "E Mixolidio", "B Alterada", "E Blues + Cromatismos").

Los nombres de escala VÁLIDOS son SOLO estos (usa estos nombres exactos):
Mixolidio, Dórico, Alterada, Blues + Cromatismos, Escala Blues, Lidia, Mayor / Jónica, Menor, Frigia, Frigia Dominante, Pentatónica Mayor, Pentatónica Menor, Menor Armónica, Menor Melódica, Eólica, Lócria.

El tono debe ser didáctico, directo y en español. NO uses un título general al principio de la respuesta.
"""
        import requests
        # Gemini's free tier is enough for one-off guides; Claude is only used for development
        candidate_models = ["gemini-3-flash-preview", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-flash-latest"]
        guide_text = None
        errors = []
        transient_codes = (429, 500, 503)
        attempts_per_model = 3

        for model_name in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            for attempt in range(attempts_per_model):
                try:
                    resp = requests.post(url, json=payload, headers={"x-goog-api-key": api_key}, timeout=120)
                    resp_json = resp.json()
                except Exception as req_err:
                    errors.append(f"{model_name}: {req_err}")
                    break
                if resp.status_code == 200 and resp_json.get("candidates"):
                    parts = resp_json["candidates"][0].get("content", {}).get("parts", [])
                    guide_text = "".join(p.get("text", "") for p in parts).strip() or None
                    if guide_text:
                        break
                    errors.append(f"{model_name}: respuesta sin texto (finishReason={resp_json['candidates'][0].get('finishReason')})")
                    break
                errors.append(f"{model_name}: {resp.status_code} {resp_json.get('error', {}).get('message', resp_json)}")
                # Demand spikes are temporary: back off and retry the same model before falling through
                if resp.status_code in transient_codes and attempt < attempts_per_model - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                break
            if guide_text:
                break

        if not guide_text:
            overloaded = any(("503" in e or "429" in e) for e in errors)
            hint = " Gemini está saturado ahora mismo; inténtalo de nuevo en un minuto." if overloaded else ""
            return jsonify({"error": f"Error de Gemini API.{hint} Detalle: {errors[-1] if errors else 'desconocido'}"}), 503 if overloaded else 500

        return jsonify({"success": True, "improvisation": strip_latex(guide_text)})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Song tempo: stored in the Songs sheet ("bpm" column), looked up on Deezer when missing ──
def _parse_bpm(raw):
    try:
        bpm = round(float(str(raw).replace(",", ".").strip()))
        return bpm if 20 <= bpm <= 300 else None
    except (TypeError, ValueError):
        return None

def _norm_text(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()

def _lookup_bpm(artist, title):
    """Deezer's tempo for the best matching track, folded into a playable 60–160 range."""
    query = requests.get("https://api.deezer.com/search", params={"q": f"{artist} {title}"}, timeout=10).json()
    want_artist = _norm_text(artist)
    for hit in query.get("data", [])[:6]:
        if want_artist not in _norm_text(hit.get("artist", {}).get("name", "")):
            continue
        track = requests.get(f"https://api.deezer.com/track/{hit['id']}", timeout=10).json()
        bpm = float(track.get("bpm") or 0)
        if bpm > 0:
            # Detectors often report double time (e.g. 171 for an 86 BPM song)
            while bpm > 160:
                bpm /= 2
            while bpm < 60:
                bpm *= 2
            return round(bpm)
    return None

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

# ── Alternative YouTube video for a song whose current video won't play ──────────
_YT_BAD_WORDS = ("live", "cover", "remix", "karaoke", "tutorial", "lesson", "sped up", "slowed", "nightcore",
                 "8d", "reaction", "mashup", "tribute", "instrumental", "reverb", "how to")
_YT_MILD_BAD_WORDS = ("take", "demo", "alternate", "session", "rehearsal", "outtake", "version", "mono")

def _search_youtube(query):
    """Video results of a YouTube search (no API key): [{id, title, channel, length}]."""
    resp = requests.get(
        "https://www.youtube.com/results", params={"search_query": query, "hl": "en"},
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
                 "Accept-Language": "en-US,en;q=0.9"},
        cookies={"CONSENT": "YES+1"}, timeout=15)
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", resp.text, re.S)
    if not m:
        return []
    found = []
    def walk(node):
        if isinstance(node, dict):
            v = node.get("videoRenderer")
            if v and v.get("videoId"):
                found.append({
                    "id": v["videoId"],
                    "title": "".join(r.get("text", "") for r in v.get("title", {}).get("runs", [])),
                    "channel": "".join(r.get("text", "") for r in v.get("ownerText", {}).get("runs", [])),
                    "length": v.get("lengthText", {}).get("simpleText", ""),
                })
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(json.loads(m.group(1)))
    return found

def _score_video(video, artist, title):
    """Higher is a better stand-in for the studio recording; None when it is clearly another song."""
    t = _norm_text(re.sub(r"\(.*?\)|\[.*?\]", "", title))
    a = _norm_text(artist)
    title_n, chan_n = _norm_text(video["title"]), _norm_text(video["channel"])
    if not t or t not in title_n:
        return None
    score = 0
    if a and (a in chan_n or chan_n in a):
        score += 4
    elif a and a in title_n:
        score += 1
    if chan_n.endswith(" topic"):
        score -= 3   # auto-generated catalogue tracks are the ones that tend to need a signed-in session
    if "official audio" in title_n or "official video" in title_n or "official music video" in title_n:
        score += 3
    elif "audio" in title_n or "official" in title_n:
        score += 1
    padded = f" {title_n} "
    score -= 4 * sum(1 for w in _YT_BAD_WORDS if f" {w} " in padded)
    score -= 2 * sum(1 for w in _YT_MILD_BAD_WORDS if f" {w} " in padded)
    return score

def _is_embeddable(video_id):
    try:
        r = requests.get("https://www.youtube.com/oembed",
                         params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}, timeout=8)
        return r.status_code == 200
    except Exception:
        return False

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

# ── Keep the YouTube Music playlist in step with a replaced video ───────────────
YT_SCOPES = ["https://www.googleapis.com/auth/youtube"]
YT_TOKEN_PATH = os.path.join(WEB_CONFIG_DIR, "youtube_token.json")
YT_API_LINK = "https://console.cloud.google.com/apis/library/youtube.googleapis.com"

class YouTubeAuthRequired(Exception):
    pass

def get_youtube_service(interactive=False):
    """YouTube Data API client for the user's account (separate token: it needs a wider scope than Sheets)."""
    creds = None
    if os.path.exists(YT_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(YT_TOKEN_PATH, YT_SCOPES)
    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not interactive:
            raise YouTubeAuthRequired()
        flow = InstalledAppFlow.from_client_secrets_file(os.path.join(WEB_CONFIG_DIR, "client_secret.json"), YT_SCOPES)
        creds = flow.run_local_server(port=0)
    with open(YT_TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def _insert_playlist_item(yt, snippet):
    """Add a video to a playlist at snippet["position"]; playlists that aren't sorted manually reject a
    position, so those get the video appended (their order comes from their own sort setting)."""
    try:
        yt.playlistItems().insert(part="snippet", body={"snippet": snippet}).execute()
    except HttpError as err:
        if "manualSortRequired" not in str(err) or "position" not in snippet:
            raise
        snippet = {k: v for k, v in snippet.items() if k != "position"}
        yt.playlistItems().insert(part="snippet", body={"snippet": snippet}).execute()

def replace_video_in_playlists(yt, old_id, new_id, hint=""):
    """Swap old_id for new_id (same position) in the user's playlists. The playlists named like `hint` go first
    and, when one of them has the video, the others are left alone. Returns the titles that were changed."""
    playlists, token = [], None
    while True:
        page = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token).execute()
        playlists += page.get("items", [])
        token = page.get("nextPageToken")
        if not token:
            break
    hint_n = _norm_text(re.sub(r"\(.*?\)", "", hint))
    def matches_hint(p):
        t = _norm_text(p["snippet"]["title"])
        return bool(hint_n) and (t.startswith(hint_n) or hint_n.startswith(t))
    groups = [[p for p in playlists if matches_hint(p)], [p for p in playlists if not matches_hint(p)]]

    for group in groups:
        changed = []
        for p in group:
            items = yt.playlistItems().list(part="snippet", playlistId=p["id"], videoId=old_id, maxResults=50).execute().get("items", [])
            for it in items:
                snippet = {"playlistId": p["id"], "resourceId": {"kind": "youtube#video", "videoId": new_id}}
                if it["snippet"].get("position") is not None:
                    snippet["position"] = it["snippet"]["position"]
                # add the new one first so a failure never leaves the playlist without the song
                _insert_playlist_item(yt, snippet)
                yt.playlistItems().delete(id=it["id"]).execute()
                if p["snippet"]["title"] not in changed:
                    changed.append(p["snippet"]["title"])
        if changed:
            return changed
    return []

def _all_playlists(yt):
    playlists, token = [], None
    while True:
        page = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token).execute()
        playlists += page.get("items", [])
        token = page.get("nextPageToken")
        if not token:
            return playlists

def sync_song_in_playlists(yt, artist, title, video_id, hint=""):
    """Make the playlist entry for this song point at video_id: finds the entry by title/artist (the old
    video id is not needed) and swaps it in place. Returns (changed_titles, already_ok)."""
    song_n = _norm_text(re.sub(r"\(.*?\)|\[.*?\]", "", title))
    artist_n = _norm_text(artist)
    hint_n = _norm_text(re.sub(r"\(.*?\)", "", hint))
    playlists = _all_playlists(yt)
    def matches_hint(p):
        t = _norm_text(p["snippet"]["title"])
        return bool(hint_n) and (t.startswith(hint_n) or hint_n.startswith(t))
    already_ok = False
    for group in ([p for p in playlists if matches_hint(p)], [p for p in playlists if not matches_hint(p)]):
        changed = []
        for p in group:
            items, token = [], None
            while True:
                page = yt.playlistItems().list(part="snippet", playlistId=p["id"], maxResults=50, pageToken=token).execute()
                items += page.get("items", [])
                token = page.get("nextPageToken")
                if not token:
                    break
            for it in items:
                sn = it["snippet"]
                item_title = _norm_text(sn.get("title", ""))
                owner = _norm_text(sn.get("videoOwnerChannelTitle", ""))
                if song_n not in item_title or not (artist_n in owner or artist_n in item_title):
                    continue
                if sn["resourceId"]["videoId"] == video_id:
                    already_ok = True
                    continue
                snippet = {"playlistId": p["id"], "resourceId": {"kind": "youtube#video", "videoId": video_id}}
                if sn.get("position") is not None:
                    snippet["position"] = sn["position"]
                _insert_playlist_item(yt, snippet)
                yt.playlistItems().delete(id=it["id"]).execute()
                if p["snippet"]["title"] not in changed:
                    changed.append(p["snippet"]["title"])
        if changed:
            return changed, already_ok
    return [], already_ok

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
