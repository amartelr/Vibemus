import sys
from src.services.chord_service import ChordService

def test_song(artist, title):
    print("\n" + "━"*60)
    print(f"🎵 RESOLVING CHORDS FOR: {artist} - {title}")
    print("━"*60)
    
    service = ChordService()
    
    # 1. Search for Spotify IDs
    print(f"🔍 Step 1: Searching for Spotify IDs via Yahoo/DDG...")
    spotify_ids = service.search_spotify_ids(artist, title)
    if not spotify_ids:
        print("❌ No Spotify IDs found.")
        return
        
    print(f"✅ Found Spotify ID(s): {spotify_ids}")
    
    # 2. Lookup in Chordonomicon database
    print(f"\n⚡ Step 2: Querying Chordonomicon Database for resolved IDs...")
    import sqlite3
    conn = sqlite3.connect(service.db_path)
    cursor = conn.cursor()
    
    found = False
    for song_id in spotify_ids:
        cursor.execute("SELECT chords FROM chord_progression WHERE spotify_song_id = ?", (song_id,))
        row = cursor.fetchone()
        if row and row[0]:
            print(f"🎉 Success! Chords found in database (Spotify ID: {song_id}):")
            print(f"\033[92m{row[0]}\033[0m")
            found = True
            break
            
    if not found:
        print("❌ No chord progressions found in Chordonomicon for these Spotify IDs.")
        
    conn.close()
    print("━"*60 + "\n")

if __name__ == "__main__":
    # You can change these to test any song you'd like!
    artist = "Pink Floyd"
    title = "Wish You Were Here"
    if len(sys.argv) > 2:
        artist = sys.argv[1]
        title = sys.argv[2]
    test_song(artist, title)
