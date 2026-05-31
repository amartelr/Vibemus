import re

# Regex to parse a chord token
# Format: RootNote Quality / BassNote
# RootNote: [A-G][sb]?
# Quality: any alphanumeric chars and symbols except slash, optional
# BassNote: optional slash followed by [A-G][sb]?
CHORD_REGEX = re.compile(r'^([A-G][sb]?)([^/]*)(?:/([A-G][sb]?))?$', re.IGNORECASE)

PITCH_CLASSES = {
    'C': 0, 'CS': 1, 'DB': 1,
    'D': 2, 'DS': 3, 'EB': 3,
    'E': 4, 'ES': 5, 'FB': 4,
    'F': 5, 'FS': 6, 'GB': 6,
    'G': 7, 'GS': 8, 'AB': 8,
    'A': 9, 'AS': 10, 'BB': 10,
    'B': 11, 'BS': 0, 'CB': 11
}

MAJOR_KEY_NAMES = {
    0: "C Major", 1: "C# Major", 2: "D Major", 3: "Eb Major", 4: "E Major",
    5: "F Major", 6: "F# Major", 7: "G Major", 8: "Ab Major", 9: "A Major",
    10: "Bb Major", 11: "B Major"
}

MINOR_KEY_NAMES = {
    0: "C Minor", 1: "C# Minor", 2: "D Minor", 3: "Eb Minor", 4: "E Minor",
    5: "F Minor", 6: "F# Minor", 7: "G Minor", 8: "G# Minor", 9: "A Minor",
    10: "Bb Minor", 11: "B Minor"
}

# Empirical pitch profile weights for key finding
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

# Roman Numeral bases per semitone offset
ROMAN_BASES_MAJOR = {
    0: 'I',   1: 'bII', 2: 'II',  3: 'bIII', 4: 'III', 5: 'IV',
    6: '#IV', 7: 'V',   8: 'bVI', 9: 'VI',   10: 'bVII', 11: 'VII'
}
ROMAN_BASES_MINOR = {
    0: 'I',   1: 'bII', 2: 'II',  3: 'III',  4: '#III', 5: 'IV',
    6: '#IV', 7: 'V',   8: 'VI',  9: '#VI',  10: 'VII', 11: '#VII'
}

DIATONIC_MAJOR_INTERVALS = {0, 2, 4, 5, 7, 9, 11}
DIATONIC_MINOR_INTERVALS = {0, 2, 3, 5, 7, 8, 10}

class ChordAnalyzer:
    """Service to parse, analyze, and enrich song chord progressions."""

    @staticmethod
    def clean_and_parse_chords(chords_str: str) -> list[dict]:
        """Cleans tags and splits chord string into structured dictionary tokens."""
        if not chords_str:
            return []
        
        # Remove any section tags like <intro_1>, <verse_2>, etc.
        cleaned = re.sub(r'<[^>]+>', ' ', chords_str)
        tokens = cleaned.split()
        
        parsed = []
        for tok in tokens:
            m = CHORD_REGEX.match(tok)
            if not m:
                continue
                
            root_str, quality_suffix, bass_str = m.groups()
            
            root_pc = PITCH_CLASSES.get(root_str.upper())
            if root_pc is None:
                continue
                
            bass_pc = PITCH_CLASSES.get(bass_str.upper()) if bass_str else None
            
            # Basic quality categorisation
            qs = quality_suffix.lower()
            if 'dim' in qs or 'o' in qs:
                quality = 'diminished'
            elif 'aug' in qs or '+' in qs:
                quality = 'augmented'
            elif 'min' in qs or ('m' in qs and 'maj' not in qs and 'dim' not in qs):
                quality = 'minor'
            else:
                quality = 'major'
                
            parsed.append({
                'root_pc': root_pc,
                'quality': quality,
                'bass_pc': bass_pc,
                'suffix': quality_suffix,
                'original': tok
            })
            
        return parsed

    @staticmethod
    def build_song_profile(parsed_chords: list[dict]) -> list[float]:
        """Builds a 12-dimensional pitch occurrence profile vector for the song."""
        profile = [0.0] * 12
        for chord in parsed_chords:
            root = chord['root_pc']
            qual = chord['quality']
            bass = chord['bass_pc']
            
            # Root note gets the highest weight
            profile[root] += 3.0
            
            # Bass note gets strong weight
            if bass is not None:
                profile[bass] += 2.0
                
            # Triad constituent tones
            if qual == 'minor':
                profile[(root + 3) % 12] += 1.0
                profile[(root + 7) % 12] += 1.0
            elif qual == 'diminished':
                profile[(root + 3) % 12] += 1.0
                profile[(root + 6) % 12] += 1.0
            elif qual == 'augmented':
                profile[(root + 4) % 12] += 1.0
                profile[(root + 8) % 12] += 1.0
            else:  # major / default
                profile[(root + 4) % 12] += 1.0
                profile[(root + 7) % 12] += 1.0
                
        return profile

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """Calculates cosine similarity between two vectors."""
        dot = sum(a * b for a, b in zip(v1, v2))
        mag1 = sum(a * a for a in v1) ** 0.5
        mag2 = sum(b * b for b in v2) ** 0.5
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)

    @classmethod
    def detect_tonality(cls, parsed_chords: list[dict]) -> tuple[int, str, str]:
        """Detects key tonic (0-11), key quality ('major' or 'minor'), and the key name."""
        if not parsed_chords:
            return 0, 'major', 'C Major'
            
        song_profile = cls.build_song_profile(parsed_chords)
        
        best_similarity = -1.0
        best_tonic = 0
        best_quality = 'major'
        
        for tonic in range(12):
            # Test Major profile shifted by tonic
            maj_profile = [MAJOR_PROFILE[(i - tonic) % 12] for i in range(12)]
            sim_maj = cls.cosine_similarity(song_profile, maj_profile)
            if sim_maj > best_similarity:
                best_similarity = sim_maj
                best_tonic = tonic
                best_quality = 'major'
                
            # Test Minor profile shifted by tonic
            min_profile = [MINOR_PROFILE[(i - tonic) % 12] for i in range(12)]
            sim_min = cls.cosine_similarity(song_profile, min_profile)
            if sim_min > best_similarity:
                best_similarity = sim_min
                best_tonic = tonic
                best_quality = 'minor'
                
        # Get key name string
        if best_quality == 'minor':
            key_name = MINOR_KEY_NAMES[best_tonic]
        else:
            key_name = MAJOR_KEY_NAMES[best_tonic]
            
        return best_tonic, best_quality, key_name

    @staticmethod
    def to_roman_numeral(chord_root_pc: int, chord_quality: str, key_tonic_pc: int, key_quality: str, suffix: str) -> str:
        """Converts an absolute chord root to a Roman Numeral string based on key."""
        interval = (chord_root_pc - key_tonic_pc) % 12
        if key_quality == 'minor':
            base = ROMAN_BASES_MINOR[interval]
        else:
            base = ROMAN_BASES_MAJOR[interval]
            
        # Separate accidental and Roman letters
        accidental = ''
        roman_part = base
        if base.startswith('b') or base.startswith('#'):
            accidental = base[0]
            roman_part = base[1:]
            
        # Casing rules: lowercase for minor/diminished, uppercase for major/augmented
        if chord_quality in ('minor', 'diminished'):
            roman_part = roman_part.lower()
            
        roman = accidental + roman_part
        
        # Diminished sign
        if chord_quality == 'diminished':
            roman += '°'
            
        # Clean suffix extension
        s = suffix.lower()
        if 'maj7' in s:
            roman += 'maj7'
        elif '7sus4' in s:
            roman += '7sus4'
        elif 'sus4' in s:
            roman += 'sus4'
        elif '7' in s:
            roman += '7'
        elif '9' in s:
            roman += '9'
            
        return roman

    @classmethod
    def get_roman_progression(cls, parsed_chords: list[dict], key_tonic_pc: int, key_quality: str) -> str:
        """Generates a collapsed Roman numeral progression string."""
        if not parsed_chords:
            return ""
            
        collapsed = []
        for c in parsed_chords:
            roman = cls.to_roman_numeral(c['root_pc'], c['quality'], key_tonic_pc, key_quality, c['suffix'])
            if not collapsed or collapsed[-1] != roman:
                collapsed.append(roman)
                
        # Limit progression representation to first 12 changes, with ... if longer
        if len(collapsed) > 12:
            return " - ".join(collapsed[:12]) + " - ..."
            
        return " - ".join(collapsed)

    @staticmethod
    def calculate_complexity(parsed_chords: list[dict], key_tonic_pc: int, key_quality: str) -> str:
        """Calculates harmonic complexity ('Baja', 'Media', 'Media-Alta', 'Alta')."""
        if not parsed_chords:
            return "Baja"
            
        unique_chords = set()
        for c in parsed_chords:
            unique_chords.add((c['root_pc'], c['quality']))
            
        num_unique = len(unique_chords)
        score = 0.0
        
        # 1. Variety count
        if num_unique <= 2:
            score += 1.0
        elif num_unique == 3:
            score += 2.0
        elif num_unique in (4, 5):
            score += 3.5
        elif num_unique in (6, 7):
            score += 5.0
        else:
            score += 6.5
            
        # 2. Extensions & slashes
        for c in parsed_chords:
            s = c['suffix'].lower()
            if any(ext in s for ext in ('7', 'maj7', 'min7', 'm7')):
                score += 0.3
            if any(ext in s for ext in ('9', '11', '13')):
                score += 0.6
            if any(ext in s for ext in ('sus4', 'sus2', 'add9', '7sus4')):
                score += 0.5
            if c['bass_pc'] is not None:
                score += 0.5
                
        # 3. Non-diatonic (modal interchange)
        diatonic_intervals = DIATONIC_MINOR_INTERVALS if key_quality == 'minor' else DIATONIC_MAJOR_INTERVALS
        num_non_diatonic = 0
        for root, qual in unique_chords:
            interval = (root - key_tonic_pc) % 12
            if interval not in diatonic_intervals:
                num_non_diatonic += 1
                
        score += min(num_non_diatonic * 1.5, 4.0)
        
        # 4. Length/tempo of changes
        if len(parsed_chords) > 20:
            score += 1.0
            
        # Map to levels
        if score < 3.5:
            return "Baja"
        elif score < 6.0:
            return "Media"
        elif score < 8.5:
            return "Media-Alta"
        else:
            return "Alta"

    @staticmethod
    def classify_style(parsed_chords: list[dict], key_quality: str, complexity: str) -> str:
        """Classifies song style ('Oscura', 'moderna', 'Alegre', 'simple')."""
        if not parsed_chords:
            return "simple"
            
        # Check if simple: Baja complexity, no extensions/slashes
        has_complex_elements = False
        for c in parsed_chords:
            s = c['suffix'].lower()
            if any(ext in s for ext in ('7', '9', '11', '13', 'sus4', 'sus2', 'add9')):
                has_complex_elements = True
                break
            if c['bass_pc'] is not None:
                has_complex_elements = True
                break
                
        if complexity == "Baja" and not has_complex_elements:
            return "simple"
            
        # Check for moderna: sus/add9/slashes or modern non-diatonic chords in non-Baja
        has_modern_indicators = False
        for c in parsed_chords:
            s = c['suffix'].lower()
            if any(ext in s for ext in ('sus4', 'add9', '7sus4', '9', '11', '7', 'maj7', 'min7')):
                has_modern_indicators = True
                break
            if c['bass_pc'] is not None:
                has_modern_indicators = True
                break
                
        if has_modern_indicators and complexity in ("Media", "Media-Alta", "Alta"):
            return "moderna"
            
        # Major vs Minor ratio
        num_minor = sum(1 for c in parsed_chords if c['quality'] in ('minor', 'diminished'))
        minor_ratio = num_minor / len(parsed_chords)
        
        if key_quality == 'minor' or minor_ratio > 0.5:
            return "Oscura"
            
        return "Alegre"

    @classmethod
    def analyze(cls, chords_str: str) -> dict:
        """Performs full analysis on a chord string, returning Tonality, Progression, Complex, and Style."""
        parsed = cls.clean_and_parse_chords(chords_str)
        if not parsed:
            return {
                'Tonality': '',
                'Progression': '',
                'Complex': '',
                'Style': ''
            }
            
        tonic, quality, key_name = cls.detect_tonality(parsed)
        progression = cls.get_roman_progression(parsed, tonic, quality)
        complexity = cls.calculate_complexity(parsed, tonic, quality)
        style = cls.classify_style(parsed, quality, complexity)
        
        return {
            'Tonality': key_name,
            'Progression': progression,
            'Complex': complexity,
            'Style': style
        }
