"""Repo layout shared by the web modules, and .env loading."""
import os

from dotenv import load_dotenv

# <root>/src/web/paths.py (this file), <root>/web/ (static front-end), <root>/config/web/ (secrets)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB_DIR = os.path.join(BASE_DIR, "web")
WEB_CONFIG_DIR = os.path.join(BASE_DIR, "config", "web")
load_dotenv(os.path.join(BASE_DIR, ".env"))
