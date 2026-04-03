import os
import sys

# Add src to sys.path
sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from src.services.yt_service import YTMusicService
from src.services.sheets_service import SheetsService
from src.services.lastfm_service import LastFMService
from src.services.musicbrainz_service import MusicBrainzService
from src.core.manager import Manager

try:
    yt = YTMusicService()
    sheets = SheetsService()
    lastfm = LastFMService()
    musicbrainz = MusicBrainzService()
    
    manager = Manager(yt, sheets, lastfm, musicbrainz)
    
    songs = manager.sheets.get_songs_records()
    in_hash = [x for x in songs if x.get('Playlist') == '#']
    print(f"Songs in '#': {len(in_hash)}")
    
    pop_songs = [x for x in songs if x.get('Playlist') == 'Pop']
    with_lastfm = [x for x in pop_songs if (x.get('Genre') or x.get('Scrobble'))]
    print(f"Pop songs: {len(pop_songs)}, with Last.fm data: {len(with_lastfm)}")
    
    print(f"Total songs in sheet: {len(songs)}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
