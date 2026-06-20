import sys
import os
import unittest
from unittest.mock import patch
sys.path.append(os.getcwd())

from src.services.chord_service import ChordService

def test_interactive():
    service = ChordService()
    
    # We mock 'input' to select the first choice (which is the official/first one)
    # or the demo chords if they exist
    with patch('builtins.input', return_value='3'): # 3 is Sufjan Stevens - Mystery of Love [Chords]
        print("Running get_chords with mocked interactive choice '38'...")
        chords = service.get_chords("Sufjan Stevens", "Mystery of Love", bypass_negative_cache=True, interactive=True)
        if chords:
            print(f"\n✅ Success! Chords: {chords[:200]}...")
        else:
            print("\n❌ Failed to get chords.")

if __name__ == "__main__":
    test_interactive()
