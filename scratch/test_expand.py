import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.core.manager import Manager

# Mock the services to avoid initializing real APIs for a simple unit test
class MockYT:
    def edit_playlist(self, pid, title=None):
        print(f"Mock: edit_playlist({pid}, title={title})")

class MockManager(Manager):
    def __init__(self):
        self._archiving_config = {"Rock": [[1993, 2014], [2015, 2021]]}
        self.yt = MockYT()
        
    def _save_archiving_config(self):
        print(f"Mock: _save_archiving_config -> {self._archiving_config}")
        
    def _resolve_playlist_id(self, pl_name):
        return "MOCK_PID_123"

m = MockManager()
print("Before:", m._archiving_config.get("Rock"))
target = m.get_target_playlist_by_year("Rock", 1991)
print("Returned target:", target)
print("After:", m._archiving_config.get("Rock"))
