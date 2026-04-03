import os
import sys
import re

# Add src to path
sys.path.append(os.getcwd())

from src.config import Config
from src.services.yt_service import YTMusicService
from src.services.sheets_service import SheetsService

def migrate():
    yt = YTMusicService()
    sheets = SheetsService()
    
    print("🚀 Starting Archiving Migration...")
    
    # 1. YouTube Playlists
    print("\n📦 1. YouTube Music Playlists")
    playlists = yt.get_library_playlists()
    for pl in playlists:
        title = pl.get('title', '')
        if title.endswith(' $'):
            new_title = title.replace(' $', ' (0-2021)')
            pid = pl.get('playlistId')
            print(f"  Renaming YT: '{title}' -> '{new_title}'")
            yt.edit_playlist(pid, title=new_title)
    
    # 2. Google Sheets
    print("\n📊 2. Google Sheets Update")
    
    # Songs
    songs = sheets.get_songs_records()
    songs_changed = False
    for s in songs:
        pl = s.get('Playlist', '')
        if pl.endswith(' $'):
            s['Playlist'] = pl.replace(' $', ' (0-2021)')
            songs_changed = True
    
    if songs_changed:
        print(f"  Updating 'Songs' sheet ({len(songs)} total records)...")
        sheets.overwrite_songs(songs)
        print("  ✓ 'Songs' sheet updated.")
    
    # Archived
    archived = sheets.get_archived_records()
    archived_changed = False
    for s in archived:
        pl = s.get('Playlist', '')
        if pl.endswith(' $'):
            s['Playlist'] = pl.replace(' $', ' (0-2021)')
            archived_changed = True
    
    if archived_changed:
        print(f"  Updating 'Archived' sheet ({len(archived)} total records)...")
        sheets.overwrite_archived(archived)
        print("  ✓ 'Archived' sheet updated.")

    # Artists (also check the default playlist of artists)
    artists = sheets.get_artists()
    artists_changed = False
    for a in artists:
        pl = a.get('Playlist', '')
        if pl.endswith(' $'):
            a['Playlist'] = pl.replace(' $', ' (0-2021)')
            artists_changed = True
    
    if artists_changed:
        print(f"  Updating 'Artists' sheet ({len(artists)} total records)...")
        sheets.save_artists(artists)
        print("  ✓ 'Artists' sheet updated.")

    print("\n✅ Migration Finished!")

if __name__ == "__main__":
    migrate()
