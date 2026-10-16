"""Chord sheet import from a PDF (chords printed above the lyrics)."""
import re


from .tabs import clean_ug_content, extract_lyrics_with_chords
from .harmony import (clean_and_extract_chords, detect_key_from_chords, infer_complexity,
                      infer_emotional_style, infer_progression)


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
