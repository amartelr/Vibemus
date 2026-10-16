"""Music theory: key detection, roman numerals, progression, emotional style and difficulty."""



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
