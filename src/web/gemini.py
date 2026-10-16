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


def generate_guide(artist, title, tonality, progression):
    """Markdown guide text. Raises GeminiError (overloaded=True on 429/503) or RuntimeError if no key."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("No se ha configurado la GEMINI_API_KEY en el servidor.")
    prompt = build_prompt(artist, title, tonality, progression)
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
        raise GeminiError(f"Error de Gemini API.{hint} Detalle: {errors[-1] if errors else 'desconocido'}", overloaded)
    return strip_latex(guide_text)
