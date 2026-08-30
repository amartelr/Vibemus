import unittest
from unittest.mock import MagicMock, patch
from src.core.manager import Manager
from src.services.sheets_service import SheetsService

class TestArtistMultiple(unittest.TestCase):
    def setUp(self):
        self.mock_sheets = MagicMock()
        self.mock_yt = MagicMock()
        self.mock_lastfm = MagicMock()
        self.mock_mb = MagicMock()
        self.manager = Manager(self.mock_yt, self.mock_sheets, self.mock_lastfm, self.mock_mb)

    def test_save_artists_includes_multiple_column(self):
        service = SheetsService.__new__(SheetsService)
        service._artists_cache = []
        mock_ws = MagicMock()
        service._get_worksheet = MagicMock(return_value=mock_ws)
        service._execute_with_retry = lambda fn, *args, **kwargs: fn(*args, **kwargs)

        sample_artists = [
            {
                "Artist Name": "Simon & Garfunkel",
                "Artist ID": "123",
                "Song Count": 5,
                "Last Checked": "30/08/2026",
                "Status": "Done",
                "Genre": "Folk Rock",
                "Playlist": "Oldies",
                "Multiple": "FALSE"
            },
            {
                "Artist Name": "Drake, 21 Savage",
                "Artist ID": "",
                "Song Count": 0,
                "Last Checked": "30/08/2026",
                "Status": "Archived",
                "Genre": "",
                "Playlist": "",
                "Multiple": "TRUE"
            },
            {
                "Artist Name": "Radiohead",
                "Artist ID": "456",
                "Song Count": 10,
                "Last Checked": "30/08/2026",
                "Status": "Done",
                "Genre": "Rock",
                "Playlist": "Rock",
                "Multiple": False
            }
        ]

        service.save_artists(sample_artists)
        
        mock_ws.update.assert_called_once()
        args, kwargs = mock_ws.update.call_args
        values = kwargs.get('values') or args[1]
        
        # Check header
        self.assertEqual(values[0], ["Artist Name", "Artist ID", "Song Count", "Last Checked", "Status", "Genre", "Playlist", "Multiple"])
        # Check row 1
        self.assertEqual(values[1], ["Simon & Garfunkel", "123", 5, "30/08/2026", "Done", "Folk Rock", "Oldies", "FALSE"])
        # Check row 2
        self.assertEqual(values[2], ["Drake, 21 Savage", "", 0, "30/08/2026", "Archived", "", "", "TRUE"])
        # Check row 3 (boolean False normalized to 'FALSE')
        self.assertEqual(values[3], ["Radiohead", "456", 10, "30/08/2026", "Done", "Rock", "Rock", "FALSE"])

    def test_audit_fused_artists_skips_already_marked(self):
        artists = [
            {"Artist Name": "Simon & Garfunkel", "Status": "Done", "Multiple": "FALSE"},
            {"Artist Name": "Drake, 21 Savage", "Status": "Archived", "Multiple": "TRUE"},
            {"Artist Name": "Radiohead", "Status": "Done", "Multiple": ""}
        ]

        # Since all collab-like names already have Multiple set (FALSE or TRUE) and Radiohead has no collab pattern,
        # input should NOT be called.
        with patch('builtins.input') as mock_input:
            result = self.manager.audit_fused_artists(artists)
            mock_input.assert_not_called()
            self.assertEqual(len(result), 3)

    def test_audit_fused_artists_prompts_unmarked_collab(self):
        artists = [
            {"Artist Name": "David Bowie & Queen", "Status": "Done", "Multiple": ""}
        ]

        # Simulate user choosing 'i' (Multiple)
        with patch('builtins.input', return_value='i'):
            result = self.manager.audit_fused_artists(artists)
            self.assertEqual(result[0]['Multiple'], 'TRUE')
            self.assertEqual(result[0]['Status'], 'Archived')

        # Simulate user choosing 's' (Single)
        artists2 = [
            {"Artist Name": "Earth, Wind & Fire", "Status": "Done", "Multiple": ""}
        ]
        with patch('builtins.input', return_value='s'):
            result2 = self.manager.audit_fused_artists(artists2)
            self.assertEqual(result2[0]['Multiple'], 'FALSE')
            self.assertEqual(result2[0]['Status'], 'Done')

    def test_split_artist_names_respects_multiple_flag(self):
        artist_map = {
            self.manager._normalize("Simon & Garfunkel"): {"Artist Name": "Simon & Garfunkel", "Multiple": "FALSE"},
            self.manager._normalize("Drake, 21 Savage"): {"Artist Name": "Drake, 21 Savage", "Multiple": "TRUE"},
            self.manager._normalize("Drake"): {"Artist Name": "Drake", "Multiple": "FALSE"},
            self.manager._normalize("21 Savage"): {"Artist Name": "21 Savage", "Multiple": "FALSE"}
        }

        # 1. Single band with & should NOT split
        res_single = self.manager._split_artist_names("Simon & Garfunkel", artist_map)
        self.assertEqual(res_single, ["Simon & Garfunkel"])

        # 2. Multi combo with Multiple: TRUE should split into parts
        res_multi = self.manager._split_artist_names("Drake, 21 Savage", artist_map)
        self.assertEqual(res_multi, ["Drake", "21 Savage"])

        # 3. Unregistered combo should split by default
        res_unregistered = self.manager._split_artist_names("Coldplay & BTS", artist_map)
        self.assertEqual(res_unregistered, ["Coldplay", "BTS"])

if __name__ == "__main__":
    unittest.main()
