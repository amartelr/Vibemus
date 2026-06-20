from src.services.chord_service import ChordService

def test():
    service = ChordService()
    
    # "Radiohead - Creep" should exist in Chordonomicon
    # We will test ultimate-guitar only, chordonomicon only, and both.
    
    print("\n1. Testing Chordonomicon ONLY:")
    chords_ch = service.get_chords("Radiohead", "Creep", bypass_negative_cache=True, provider="chordonomicon")
    print(f"Chordonomicon: {'✅ Found' if chords_ch else '❌ Not Found'}")
    
    print("\n2. Testing Ultimate Guitar ONLY:")
    chords_ug = service.get_chords("Radiohead", "Creep", bypass_negative_cache=True, provider="ultimate-guitar")
    print(f"Ultimate Guitar: {'✅ Found' if chords_ug else '❌ Not Found'}")
    
    print("\n3. Testing BOTH:")
    chords_both = service.get_chords("Radiohead", "Creep", bypass_negative_cache=True, provider="both")
    print(f"Both: {'✅ Found' if chords_both else '❌ Not Found'}")

if __name__ == "__main__":
    test()
