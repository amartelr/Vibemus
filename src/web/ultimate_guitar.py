"""Ultimate Guitar search, matching and chord/lyrics extraction."""


from .harmony import detect_key_from_chords, infer_complexity, infer_emotional_style, infer_progression
from .tabs import clean_ug_content, extract_lyrics_with_chords, tab_to_chords


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
