"""Improvisation guides generated with Gemini (free tier; Claude is only used for development)."""
import os
import re
import time

import requests


def strip_latex(text):
    """Models sometimes wrap chords in LaTeX ($Dm^7$, $C^{maj7}$): turn them back into plain text (Dm7, Cmaj7)."""
    def plain(m):
        inner = m.group(1)
        inner = inner.replace("\\sharp", "#").replace("\\flat", "b").replace("\\natural", "")
        inner = re.sub(r"[\^_]\{([^}]*)\}", r"\1", inner)
        inner = re.sub(r"[\^_](\w+)", r"\1", inner)
        return re.sub(r"[{}\\]", "", inner)
    return re.sub(r"\$([^$\n]+)\$", plain, text or "")


def build_prompt(artist, title, tonality, progression):
    return f"""Eres un experto en teoría musical, armonía funcional y guitarrista profesional.
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


class GeminiError(Exception):
    def __init__(self, message, overloaded=False):
        super().__init__(message)
        self.overloaded = overloaded


def _generate(prompt, temperature=None):
    """Text Gemini answers to the prompt (falls back across Flash models, retries on demand spikes).
    Raises GeminiError (overloaded=True on 429/503) or RuntimeError if no key."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("No se ha configurado la GEMINI_API_KEY en el servidor.")
    candidate_models = ["gemini-3-flash-preview", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-flash-latest"]
    text = None
    errors = []
    transient_codes = (429, 500, 503)
    attempts_per_model = 3

    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        if temperature is not None:
            payload["generationConfig"] = {"temperature": temperature}
        for attempt in range(attempts_per_model):
            try:
                resp = requests.post(url, json=payload, headers={"x-goog-api-key": api_key}, timeout=120)
                resp_json = resp.json()
            except Exception as req_err:
                errors.append(f"{model_name}: {req_err}")
                break
            if resp.status_code == 200 and resp_json.get("candidates"):
                parts = resp_json["candidates"][0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip() or None
                if text:
                    break
                errors.append(f"{model_name}: respuesta sin texto (finishReason={resp_json['candidates'][0].get('finishReason')})")
                break
            errors.append(f"{model_name}: {resp.status_code} {resp_json.get('error', {}).get('message', resp_json)}")
            # Demand spikes are temporary: back off and retry the same model before falling through
            if resp.status_code in transient_codes and attempt < attempts_per_model - 1:
                time.sleep(2 * (attempt + 1))
                continue
            break
        if text:
            break

    if not text:
        overloaded = any(("503" in e or "429" in e) for e in errors)
        hint = " Gemini está saturado ahora mismo; inténtalo de nuevo en un minuto." if overloaded else ""
        raise GeminiError(f"Error de Gemini API.{hint} Detalle: {errors[-1] if errors else 'desconocido'}", overloaded)
    return text


def generate_guide(artist, title, tonality, progression):
    """Markdown guide text. Raises GeminiError (overloaded=True on 429/503) or RuntimeError if no key."""
    return strip_latex(_generate(build_prompt(artist, title, tonality, progression)))


def build_chord_sheet_prompt(artist, title, tonality, lyrics, heard_chords):
    heard = " ".join(heard_chords) if heard_chords else "(no disponible)"
    if lyrics:
        lyrics_block = f"""LETRA (cópiala EXACTAMENTE, sin cambiar, añadir ni quitar palabras; solo reparte las líneas en secciones):
\"\"\"
{lyrics}
\"\"\""""
        lyrics_rule = "Escribe cada línea de la letra con los acordes intercalados justo antes de la sílaba donde cambian."
    else:
        lyrics_block = "LETRA: no disponible (puede ser instrumental)."
        lyrics_rule = "No hay letra: escribe cada sección como líneas solo de acordes."
    return f"""Eres un guitarrista profesional que transcribe cifrados de acordes como los de Ultimate Guitar.
Canción: "{title}" de "{artist}".
Tonalidad detectada del audio: {tonality}
Acordes detectados del audio en un fragmento de 30 s (pista orientativa, pueden fallar y no abarcan toda la canción): {heard}

{lyrics_block}

Escribe el cifrado completo de la canción tal como se toca habitualmente, respetando la tonalidad.
FORMATO OBLIGATORIO (texto plano, sin Markdown, sin explicaciones, sin bloques de código):
- Cada sección empieza en su propia línea con su nombre entre corchetes: [Intro], [Verse 1], [Pre-Chorus], [Chorus], [Verse 2], [Bridge], [Solo], [Outro].
- Cada acorde va envuelto en [ch]...[/ch] y pegado al texto, p. ej. [ch]Am[/ch]palabra otra [ch]G[/ch]palabra.
- {lyrics_rule}
- Las secciones instrumentales (Intro, Solo, Outro) son una línea de acordes: [ch]Am[/ch] [ch]F[/ch] [ch]C[/ch] [ch]G[/ch].
- Repite la sección completa cada vez que aparezca (cada estribillo con su letra y sus acordes).
- Nombres de acorde en texto plano: Am, F#m7, Cmaj7, G/B, Dsus4, E7. Nada de LaTeX ni símbolos de dólar.
- Nunca uses corchetes dentro de la letra salvo los de las secciones y los acordes.
"""


def generate_chord_sheet(artist, title, tonality, lyrics, heard_chords):
    """Chord sheet as Ultimate-Guitar-style markup ([Verse 1] sections, inline [ch]Am[/ch] chords)."""
    text = _generate(build_chord_sheet_prompt(artist, title, tonality, lyrics, heard_chords), temperature=0.2)
    text = strip_latex(text)
    text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text.strip())
    return text.strip()


def build_lyrics_alignment_prompt(artist, title, tonality, chord_text, lyrics):
    return f"""Eres un guitarrista profesional que prepara cifrados de acordes como los de Ultimate Guitar.
Canción: "{title}" de "{artist}". Tonalidad: {tonality or "desconocida"}.

ACORDES YA VALIDADOS (orden de la canción; las etiquetas como <verse_1> o <chorus> indican la sección, si las hay):
{chord_text}

LETRA (cópiala EXACTAMENTE, sin cambiar, añadir ni quitar palabras):
\"\"\"
{lyrics}
\"\"\"

Reparte esos acordes sobre la letra. NO cambies, añadas ni quites acordes: usa solo los de la lista y en ese orden.
Si la lista no trae secciones, deduce dónde empieza cada estrofa y cada estribillo por la letra y por cómo se repite la progresión.
FORMATO OBLIGATORIO (texto plano, sin Markdown, sin explicaciones, sin bloques de código):
- Cada sección empieza en su propia línea con su nombre entre corchetes: [Intro], [Verse 1], [Pre-Chorus], [Chorus], [Bridge], [Solo], [Outro].
- Cada acorde va envuelto en [ch]...[/ch] y pegado al texto, justo antes de la sílaba donde cambia, p. ej. [ch]Am[/ch]palabra otra [ch]G[/ch]palabra.
- Las partes instrumentales son una línea de acordes: [ch]Am[/ch] [ch]F[/ch] [ch]C[/ch] [ch]G[/ch].
- Repite la sección completa cada vez que aparezca (cada estribillo con su letra y sus acordes).
- Nunca uses corchetes dentro de la letra salvo los de las secciones y los acordes.
"""


def generate_lyrics_sheet(artist, title, tonality, chord_text, lyrics):
    """The song's existing chords laid over its lyrics, as Ultimate-Guitar-style markup."""
    text = _generate(build_lyrics_alignment_prompt(artist, title, tonality, chord_text, lyrics), temperature=0.1)
    text = strip_latex(text)
    return re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text.strip()).strip()
