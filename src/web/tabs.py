"""Tablature -> chords conversion and Ultimate Guitar content cleaning."""



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
