
import sys
import os
from unittest.mock import MagicMock

# Mocking services to test Manager._fetch_song_year
sys.path.append(os.path.abspath('.'))
from src.core.manager import Manager
from src.config import Config

yt = MagicMock()
sheets = MagicMock()
lfm = MagicMock()
mb = MagicMock()

manager = Manager(yt, sheets, lfm, mb)

# Example: Elliott Smith - Say Yes (videoId: oHH4RV5mxfY)
# We can't really run the real YT API here easily without credentials,
# but I can see how it's implemented.
print("Checking _fetch_song_year implementation...")
