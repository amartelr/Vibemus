"""Music theory: key detection, roman numerals, progression, emotional style and difficulty."""



import re

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

_CHORD_PATTERN = re.compile(r'\b[A-G][#b]?(?:[Mm]aj|[Mm]in|[Dd]im|[Aa]ug|[Ss]us|[Aa]dd|m|M|[0-9]|\-|\+|\#|b|o|\u00b0|\u00f8|\u0394)*(?:/[A-G][#b]?)?(?!\w)')
_CHORD_TAG = re.compile(r'\[ch(?:\s[^\]]*)?\](.*?)\[/ch\]', re.IGNORECASE)
_SECTION_TAG = re.compile(r'\[(?!ch\b)(?!/ch\])[^\]]*\]')
_NOT_CHORD_WORDS = {'intro', 'verse', 'chorus', 'bridge', 'outro', 'solo', 'pre', 'instrumental', 'tab', 'ch', 'verso',
                    'estribillo', 'puente', 'middle', 'between', 'verses', 'in', 'to', 'is', 'it', 'at', 'on', 'or',
                    'an', 'be', 'do', 'so'}
CHORD_LINE_RATIO = 0.6   # share of the words of a line that must be chords for a lone letter (A, C, G) to count as one


def _chord_tokens(line):
    return [m for m in _CHORD_PATTERN.findall(line) if m.lower() not in _NOT_CHORD_WORDS]


def clean_and_extract_chords(text):
    """Chords of a chord sheet, in order.

    Tagged text ([ch]Am[/ch]) is trusted as it is. Free text is read line by line: a chord written as a single letter
    ("A", "C") is only taken when most of the line is chords, so the article "A" of a lyric is not a chord.
    """
    if not text:
        return []
    tagged = _CHORD_TAG.findall(text)
    if tagged:
        return [t for c in tagged for t in _chord_tokens(c.strip())[:1] if c.strip()]

    # Section tags ([Intro], [Verse 1], <verse_1>, <song>) are not chords
    t = _SECTION_TAG.sub(' ', text)
    t = re.sub(r'<[^>]+>', ' ', t)

    chords = []
    for line in t.splitlines():
        found = _chord_tokens(line)
        if not found:
            continue
        words = [w for w in line.split() if re.search(r'\w', w)]
        chord_line = len(found) >= CHORD_LINE_RATIO * len(words)
        chords.extend(m for m in found if chord_line or len(m) > 1)
    return chords

def parse_chord_root_and_quality(chord):
    import re
    chord = chord.split('/')[0].strip()
    match = re.match(r'^([A-G][#b]?)(.*)$', chord)
    if not match:
        return None, None, None
    root = match.group(1)
    suffix = match.group(2)
    
    # From the most specific quality to the most general: "dim" contains an "m", so it must be tested before minor.
    # Minor is only a suffix that STARTS with "m"/"min" (a capital "M" or "maj" is a major seventh: CM7, Cmaj7).
    s_low = suffix.lower()
    if 'dim' in s_low or s_low.startswith('o') or '°' in suffix or 'ø' in suffix:
        quality = 'dim'
    elif 'aug' in s_low or '+' in suffix:
        quality = 'aug'
    elif s_low.startswith('min') or (suffix.startswith('m') and not s_low.startswith('maj')):
        quality = 'minor'
    else:
        quality = 'major'

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
        # Natural minor plus the leading tone (same scale as KEY_MINOR_SCALE). Semitones that are not in that scale
        # (3 vs 4, 8 vs 9, 10 vs 11 share a degree number) keep their own sign so two roots never give the same numeral.
        major_q = quality == 'major'
        if diff == 0:
            roman = 'i' if quality == 'minor' else 'I'
        elif diff == 1:
            roman = 'bII'
        elif diff == 2:
            roman = 'ii°' if quality == 'dim' else ('ii' if quality == 'minor' else 'II')
        elif diff == 3:
            roman = 'III' if major_q else 'iii'
        elif diff == 4:
            roman = '#III' if major_q else '#iii'
        elif diff == 5:
            roman = 'iv' if quality == 'minor' else 'IV'
        elif diff == 6:
            roman = 'bV'
        elif diff == 7:
            roman = 'v' if quality == 'minor' else 'V'
        elif diff == 8:
            roman = 'VI' if major_q else 'vi'
        elif diff == 9:
            roman = 'vi°' if quality == 'dim' else ('#VI' if major_q else '#vi')
        elif diff == 10:
            roman = 'VII' if major_q else 'vii'
        elif diff == 11:
            roman = 'vii°' if quality == 'dim' else ('#VII' if major_q else '#vii')
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
    elif quality == 'dim' and roman.endswith('\u00b0'):
        clean_suffix = re.sub(r'^(dim|o|\u00b0|\u00f8)', '', suffix, flags=re.IGNORECASE)  # the numeral already carries the °
        
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

# Weight of each chord as (semitones above the tonic, quality) in each mode. Borrowed chords that are common in
# pop/rock (bVII, iv, bVI in major; IV in minor) are mildly positive instead of penalised as foreign.
MAJOR_W = {(0, "major"): 3.5, (2, "minor"): 1.5, (4, "minor"): 0.5, (5, "major"): 2.5, (7, "major"): 2.5,
           (9, "minor"): 2.0, (11, "dim"): 0.5, (11, "minor"): 0.5,
           (10, "major"): 1.0, (5, "minor"): 0.5, (8, "major"): 0.5, (2, "major"): 0.5, (4, "major"): 0.3}
MINOR_W = {(0, "minor"): 3.5, (2, "dim"): 1.0, (2, "minor"): 0.5, (3, "major"): 2.0, (5, "minor"): 2.0, (5, "major"): 0.5,
           (7, "minor"): 1.5, (7, "major"): 2.0, (8, "major"): 2.0, (10, "major"): 2.0, (11, "dim"): 0.5}
FOREIGN = -1.5
SEVENTH_MISFIT = 1.5
FIRST_BONUS = 3.0   # songs start on the tonic more reliably than transcriptions end on it
LAST_BONUS = 2.0


KEY_MAJOR_SCALE = {0, 2, 4, 5, 7, 9, 11}
KEY_MINOR_SCALE = {0, 2, 3, 5, 7, 8, 10, 11}  # natural minor plus the leading tone


MAJOR_TRIADS = {(0, "major"), (2, "minor"), (4, "minor"), (5, "major"), (7, "major"), (9, "minor"), (11, "dim")}
MINOR_TRIADS = {(0, "minor"), (2, "dim"), (3, "major"), (5, "minor"), (7, "minor"), (7, "major"), (8, "major"), (10, "major"), (11, "dim")}


def _seventh(suffix):
    """Interval of the chord's 7th above its root (11 maj7, 10 minor/dominant 7th, 9 dim7) or None."""
    low = (suffix or "").lower()
    if "maj" in low or "\u0394" in suffix or "M7" in suffix:
        return 11 if any(n in low for n in ("7", "9", "11", "13")) or "\u0394" in suffix else None
    if "dim7" in low or "o7" in low:
        return 9
    if any(n in low for n in ("7", "9", "11", "13")):
        return 10
    return None


def _is_dominant7(quality, suffix):
    low = (suffix or "").lower()
    return quality == "major" and "7" in low and "maj" not in low


def key_scores_from_chords(chord_list):
    """Score of each of the 24 keys for a chord sequence: ({(tonic pitch class, "Major"|"Minor"): score}, prefer_flats).

    Empty when no chord can be read. detect_key_from_chords() takes the best one.

    Measured against the audio key of 146 Liked songs : the previous scoring took the IV for the
    tonic in 42 of them (I-IV vamps, bVII borrowings, I->IV read as V->I). Chord weights, symmetric cadences and the
    7th of each chord (Emaj7 cannot be the V of A) bring exact matches from 54 % to 68 %.
    """
    if not chord_list:
        return {}, False
    flat_count = sum(1 for c in chord_list if 'b' in c and not c.startswith('B'))
    sharp_count = sum(1 for c in chord_list if '#' in c)
    prefer_flats = flat_count > sharp_count

    parsed = []
    for c in chord_list:
        r, q, s = parse_chord_root_and_quality(c)
        if r and NOTE_MAP.get(r, r) in SEMITONES:
            parsed.append((SEMITONES.index(NOTE_MAP.get(r, r)), q, _is_dominant7(q, s), _seventh(s)))
    if not parsed:
        return {}, prefer_flats

    # a root also written as maj7 is a tonic-like chord: its dominant 7th is passing (I - I7 - IV), not a V7
    maj7_roots = {root for root, q, _, sev in parsed if q == "major" and sev == 11}
    # (and its b7 is a passing colour, not a tone that rules the key out)
    parsed = [(root, q, dom7 and root not in maj7_roots, None if dom7 and root in maj7_roots else sev)
              for root, q, dom7, sev in parsed]

    scores = {}
    for tonic in range(12):
        for mode, weights in (("Major", MAJOR_W), ("Minor", MINOR_W)):
            tonic_q = "major" if mode == "Major" else "minor"
            score = 0.0
            scale = KEY_MAJOR_SCALE if mode == "Major" else KEY_MINOR_SCALE
            for root, q, dom7, sev in parsed:
                d = (root - tonic) % 12
                score += weights.get((d, q if q in ("major", "minor", "dim") else "major"), FOREIGN)
                if dom7 and d == 7:
                    score += 1.0          # a dominant 7th on the fifth is strong evidence for this tonic
                elif dom7 and d == 0 and mode == "Major":
                    score -= 0.5          # tonic chords are rarely dominant 7ths (blues aside)
                if sev is not None and (d + sev) % 12 not in scale:
                    score -= SEVENTH_MISFIT   # e.g. Cmaj7 cannot be the V of F: its B is not in F major
            # Cadences: symmetric weights so that I->IV in the right key is not read as V->I in the key of the IV
            for (r1, q1, dom1, _), (r2, q2, _, _) in zip(parsed, parsed[1:]):
                d1, d2 = (r1 - tonic) % 12, (r2 - tonic) % 12
                if d2 == 0 and q2 == tonic_q:
                    if d1 == 7: score += 4.0 if dom1 else 1.5      # V7 -> I; a plain V -> I counts like IV -> I
                    elif d1 in (5, 10, 2): score += 1.5             # IV/iv, bVII, ii -> I
                elif d1 == 0 and q1 == tonic_q and d2 in (5, 7, 10, 9, 8, 3):
                    score += 1.0                                    # I -> anything diatonic
                elif mode == "Major" and d1 in (5, 2) and d2 == 7 and q2 == "major":
                    score += 2.5                                    # IV -> V, ii -> V (predominant to dominant)
            if parsed[0][0] == tonic and parsed[0][1] == tonic_q: score += FIRST_BONUS
            if parsed[-1][0] == tonic and parsed[-1][1] == tonic_q: score += LAST_BONUS
            scores[(tonic, mode)] = score
    return scores, prefer_flats


def key_name(tonic, mode, prefer_flats=False):
    """'Bb Major' from (10, 'Major') with flats, 'A# Major' without."""
    name = SEMITONES[tonic]
    return f"{FLAT_NAMES.get(name, name) if prefer_flats else name} {mode}"


def detect_key_from_chords(chord_list):
    """Most likely key of a chord sequence, e.g. "E Major" ("C Major" when no chord can be read)."""
    scores, prefer_flats = key_scores_from_chords(chord_list)
    if not scores:
        return "C Major"
    tonic, mode = max(scores, key=scores.get)      # first of the best in tonic order, Major before Minor
    return key_name(tonic, mode, prefer_flats)

def infer_progression_full(chord_string, tonality):
    """Roman numerals in playing order, repetitions kept (["I", "V", "vi", "IV", "I", "V", ...]).

    Only a chord repeated back to back counts once (the same chord written on several beats or lines). Pattern
    detection (emotional style) needs this sequence; the Progression column keeps the summary of infer_progression().
    """
    if not tonality or not chord_string:
        return []
    key_root, key_mode = parse_tonality(tonality)
    if not key_root:
        return []
    romans = []
    for c in clean_and_extract_chords(chord_string):
        r = get_roman_numeral(key_root, key_mode, c)
        if r and (not romans or romans[-1] != r):
            romans.append(r)
    return romans


def infer_progression(chord_string, tonality):
    """The first 6 distinct roman numerals, in order of first appearance, joined by " - " (what the sheet stores)."""
    distinct = list(dict.fromkeys(infer_progression_full(chord_string, tonality)))
    return " - ".join(distinct[:6])


# ── Progression patterns used by the emotional style ────────────────────────────────────────────────────────────
_DEGREE = re.compile(r'^[b#]?([IV]+|[iv]+)(\u00b0?)')


def _degree(roman):
    """Base degree of a numeral without accidental or suffix, case kept: 'bVII' -> 'VII', 'vi7' -> 'vi', 'ii°' -> 'ii°'."""
    m = _DEGREE.match(roman)
    return m.group(1) + m.group(2) if m else roman


def _has_pattern(degrees, pattern):
    """True when the pattern's degrees (each a regex, case-sensitive) appear one right after the other.

    Progression patterns are consecutive by nature (I-V-vi-IV). Allowing gaps would make every long song match every
    pattern, since the full progression repeats its chords many times.
    """
    n = len(pattern)
    return any(all(re.fullmatch(pattern[j], degrees[i + j]) for j in range(n)) for i in range(len(degrees) - n + 1))


# Each pattern is a tuple of degree regexes. Capitals are major chords, lowercase minor: vi is not VI.
_TONIC = '[Ii]'
_DOMINANT = '[Vv]'
_P_EPIC = ((_TONIC, 'VII'), ('VI', 'III'), ('III', 'VII'))
_P_POP = ('I', 'V', 'vi', 'IV')
_P_DARK_MINOR = ('i', 'iv', _DOMINANT)
_P_MINOR_EPIC = ('i', 'VI', 'III', 'VII')
_P_DESCENT = (_TONIC, 'VII', 'VI', _DOMINANT)
_P_JAZZ = ('ii°?', 'V', _TONIC)
_P_PLAGAL = ('IV', 'I')


def style_scores(chord_string, tonality):
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
        "Brillante":    0,
        "Enérgica":     0,
        "Orgánica":     0,
        "Tensa":        0,
        "Flotante":     0,
        "Cálida":       0,
    }

    if not tonality:
        scores["Melancólica"] += 3
        return scores

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
    # Sobre la progresión completa y respetando mayúsculas (vi no es VI); un grado alterado (bVII) cuenta como su número
    degrees = [_degree(r) for r in infer_progression_full(chord_string, tonality)] if chord_string and tonality else []

    # Patrones épicos/cinematográficos
    if any(_has_pattern(degrees, p) for p in _P_EPIC):
        scores["Épica"]          += 3
        scores["Cinematográfica"] += 2
    # Pop emocional (I-V-vi-IV)
    if _has_pattern(degrees, _P_POP):
        scores["Alegre"]         += 2
        scores["Nostálgica"]     += 2
    # Oscuro menor natural (i-iv-v)
    if is_minor and _has_pattern(degrees, _P_DARK_MINOR):
        scores["Oscura"]         += 3
    # i-VI-III-VII
    if is_minor and _has_pattern(degrees, _P_MINOR_EPIC):
        scores["Épica"]          += 2
        scores["Oscura"]         += 1
    # Descenso (i-VII-VI-V —flamenco/drama)
    if _has_pattern(degrees, _P_DESCENT):
        scores["Tensa"]          += 3
        scores["Cinematográfica"] += 2
        scores["Oscura"]         += 1
    # Jazz (ii-V-I)
    if _has_pattern(degrees, _P_JAZZ):
        scores["Elegante"]       += 3
        scores["Cálida"]         += 1
    # Plagal (IV-I) — religioso/organic
    if _has_pattern(degrees, _P_PLAGAL):
        scores["Orgánica"]       += 2
        scores["Cálida"]         += 1
    # Loop modal (sin acorde de dominante) — estático/meditativo
    if degrees and not any(re.fullmatch(_DOMINANT, d) for d in degrees) and n_unique >= 3:
        scores["Flotante"]       += 2
        scores["Soñadora"]       += 1

    # ─── 7. PRÉSTAMO MODAL ───────────────────────────────────────────────────
    # Acorde que no es diatónico de la tonalidad pero sí de su modo paralelo (iv en mayor, IV mayor en menor...)
    if chord_string and tonality:
        key_root, key_mode = parse_tonality(tonality)
        tonic = SEMITONES.index(NOTE_MAP[key_root]) if key_root in NOTE_MAP else None
        if tonic is not None:
            own, parallel = (MINOR_TRIADS, MAJOR_TRIADS) if key_mode == "Minor" else (MAJOR_TRIADS, MINOR_TRIADS)
            borrowed = set()
            for c in chords:
                r, q, _ = parse_chord_root_and_quality(c)
                if r in NOTE_MAP:
                    fn = ((SEMITONES.index(NOTE_MAP[r]) - tonic) % 12, q)
                    if fn in parallel and fn not in own:
                        borrowed.add(fn)
            if borrowed:
                scores["Cinematográfica"] += 3
                scores["Moderna"]         += 2
                scores["Nostálgica"]      += 1

    return scores


def infer_emotional_style(chord_string, tonality):
    """Up to 3 emotional labels, ordered by weight (2 when the tonality is unknown). See style_scores()."""
    scores = style_scores(chord_string, tonality)
    ranked = [label for label, sc in sorted(scores.items(), key=lambda x: x[1], reverse=True) if sc > 0]
    if not tonality:
        return ", ".join(ranked[:2]) or "Melancólica"
    if not ranked:
        return "Melancólica" if re.search(r'\b(m|min|minor)\b', tonality, re.IGNORECASE) else "Alegre"
    return ", ".join(ranked[:3])


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
