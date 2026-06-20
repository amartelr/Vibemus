from src.services.chord_service import ChordService

def test():
    service = ChordService()
    
    songs = [
        ("Radiohead", "Creep"),
        ("Nirvana", "Smells Like Teen Spirit"),
        ("Pink Floyd", "Wish You Were Here"),
        ("Planning for Burial", "I Want To Die A Beautiful Death")
    ]
    
    for artist, title in songs:
        print("\n" + "="*40)
        print(f"Testing: {artist} - {title}")
        chords = service.get_chords(artist, title)
        if chords:
            print(f"✅ Success! Chords: {chords[:150]}...")
        else:
            print(f"❌ Failed to get chords.")

if __name__ == "__main__":
    test()
