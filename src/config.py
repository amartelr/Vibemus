import os
import json

class Config:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CONFIG_DIR = os.path.join(BASE_DIR, 'config')
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    
    # Files
    OAUTH_FILE = os.path.join(CONFIG_DIR, 'oauth.json')
    BROWSER_AUTH_FILE = os.path.join(CONFIG_DIR, 'browser.json')
    SERVICE_ACCOUNT_FILE = os.path.join(CONFIG_DIR, 'service_account.json')
    SOURCE_CACHE_FILE = os.path.join(DATA_DIR, 'source_cache.json')
    LASTFM_CACHE_FILE = os.path.join(DATA_DIR, 'lastfm_cache.json')
    MUSICBRAINZ_CACHE_FILE = os.path.join(DATA_DIR, 'musicbrainz_cache.json')
    GENRE_PREFS_FILE = os.path.join(DATA_DIR, 'genre_preferences.json')
    ARCHIVING_CONFIG_FILE = os.path.join(CONFIG_DIR, 'archiving.json')
    
    # Last.fm
    LASTFM_API_KEY = "affe9034dbe45ea2941b4697369ea607"
    LASTFM_API_SECRET = "6b9a082897806a37c4e97af9b0765f64"
    LASTFM_USERNAME = "amartelr"
    
    # MusicBrainz / AcoustID
    MUSICBRAINZ_APP = "vibemus"
    MUSICBRAINZ_VERSION = "1.0"
    MUSICBRAINZ_CONTACT = "amartelr@users.noreply.github.com"
    ACOUSTID_API_KEY = "VAcPhH9RYY"
    
    # Sheets
    SPREADSHEET_TITLE = "YouTube Music Vibemus"

    PLAYLIST_ID = "PL2_CnmTxHQ0Cnmzx13a1EL_3nrqr1wCkr" 
    SCROBBLE_THRESHOLD = 13
    UNLIKE_THRESHOLD = 10

    SOURCE_PLAYLISTS = [
        "#", "Pop", "Rock", "Garage", "Shoegaze", "Post-punk", "Emo", "Folk",
        "Español", "Crank"
    ]

    ARCHIVABLE_PLAYLISTS = ["Pop", "Rock", "Folk", "Post-punk", "Español", "Crank", "Garage"]
    
    MAX_NEW_RELEASE_SONGS = 3  # Max top songs to add from a new album release
    MAX_NEW_RELEASE_YEARS = 1  # Límite de años hacia atrás para buscar novedades
    SYNC_DELAY = 2 # Seconds between artists in batch operations

    # Local Caching
    DEEP_SYNC_CACHE_FILE = os.path.join(DATA_DIR, 'deep_sync_cache.json')
    DEEP_SYNC_CACHE_DAYS = 30
    
    @classmethod
    def validate(cls):
        missing = []
        if not os.path.exists(cls.OAUTH_FILE):
            missing.append(f"Missing YouTube Music OAuth file: {cls.OAUTH_FILE}")
        if not os.path.exists(cls.BROWSER_AUTH_FILE):
            missing.append(f"Missing YouTube Music Browser Auth file: {cls.BROWSER_AUTH_FILE}")
        if not os.path.exists(cls.SERVICE_ACCOUNT_FILE):
            missing.append(f"Missing Google Service Account file: {cls.SERVICE_ACCOUNT_FILE}")
            
        if missing:
            raise FileNotFoundError("\n".join(missing))
        return True

    @classmethod
    def ensure_directories(cls):
        os.makedirs(cls.CONFIG_DIR, exist_ok=True)
        os.makedirs(cls.DATA_DIR, exist_ok=True)
