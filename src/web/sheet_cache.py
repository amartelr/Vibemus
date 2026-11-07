"""Cache of generated chord sheets (data/generated_sheets.json), so asking for the same sheet again
does not spend a new Gemini call. Keys are hashes of the full prompt; values are the sheet text."""
import json
import os
import threading

from .paths import BASE_DIR

CACHE_FILE = os.path.join(BASE_DIR, "data", "generated_sheets.json")
_lock = threading.Lock()


def _load():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get(key):
    with _lock:
        return _load().get(key)


def put(key, text):
    with _lock:
        data = _load()
        data[key] = text
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
