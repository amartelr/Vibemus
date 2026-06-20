import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add root folder to sys.path
sys.path.append(os.getcwd())

from src.core.manager import Manager

def test_print_artist_catalog_summary_cache_bypass_and_arch_tag():
    # Mocking services
    yt_service = MagicMock()
    sheets_service = MagicMock()
    lastfm_service = MagicMock()
    musicbrainz_service = MagicMock()
    
    # Setup mock data for sheets
    sheets_service.get_songs_records.return_value = [
        {"Playlist": "Rock", "Artist": "Radiohead", "Title": "Creep", "Video ID": "vid1"},
        {"Playlist": "Rock", "Artist": "Radiohead", "Title": "Karma Police", "Video ID": "vid2"}
    ]
    sheets_service.get_archived_records.return_value = [
        {"Playlist": "Rock $", "Artist": "Radiohead", "Title": "No Surprises", "Video ID": "vid3"}
    ]
    sheets_service.get_artists.return_value = [
        {"Artist Name": "Radiohead", "Status": "Done", "Playlist": "Rock"}
    ]
    
    manager = Manager(yt_service, sheets_service, lastfm_service, musicbrainz_service)
    
    # Call _print_artist_catalog_summary
    total, active, archived = manager._print_artist_catalog_summary("Radiohead")
    
    # Assert cache was cleared/bypassed (set to None before fetching)
    assert sheets_service.get_songs_records.call_count == 1
    assert sheets_service.get_archived_records.call_count == 1
    
    # Verify return values
    assert total == 3
    assert active == 2
    assert archived == 1

def test_sync_all_artist_releases_auto_archive():
    yt_service = MagicMock()
    sheets_service = MagicMock()
    lastfm_service = MagicMock()
    musicbrainz_service = MagicMock()
    
    # Setup mock data for sheets: Radiohead has only archived songs
    sheets_service.get_songs_records.return_value = []
    sheets_service.get_archived_records.return_value = [
        {"Playlist": "Rock $", "Artist": "Radiohead", "Title": "No Surprises", "Video ID": "vid3"}
    ]
    sheets_service.get_artists.return_value = [
        {"Artist Name": "Radiohead", "Status": "Done", "Playlist": "Rock"}
    ]
    
    manager = Manager(yt_service, sheets_service, lastfm_service, musicbrainz_service)
    
    # Mock cache loading/saving
    manager._load_releases_sync_cache = MagicMock(return_value={})
    manager._save_releases_sync_cache = MagicMock()
    
    # Should archive directly without calling input()
    manager.sync_all_artist_releases(force=True, interactive=True)
    
    # Verify status is updated to Archived directly
    sheets_service.update_artist_status.assert_called_with("Radiohead", "Archived")
    # Verify last checked updated
    sheets_service.update_artist_last_checked.assert_called_once()
    # Verify releases sync cache is saved
    manager._save_releases_sync_cache.assert_called_once()
