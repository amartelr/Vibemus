import sys
import os
sys.path.append(os.getcwd())

from src.services.chord_service import ChordService

def main():
    service = ChordService()
    print("Running get_chords for Sufjan Stevens - Mystery of Love...")
    chords = service.get_chords("Sufjan Stevens", "Mystery of Love", bypass_negative_cache=True, interactive=False)
    if chords:
        print(f"✅ Success! Chords: {chords[:200]}...")
    else:
        print("❌ Failed to get chords.")

if __name__ == "__main__":
    main()
