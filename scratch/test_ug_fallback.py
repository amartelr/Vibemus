import sys
import os
sys.path.append(os.getcwd())

from src.services.chord_service import ChordService

def main():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🎸 TESTING ULTIMATE GUITAR CHORD RESOLUTION & SCRAPER")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    service = ChordService()
    
    # Test cases: Artist and Title
    test_cases = [
        {"artist": "Pink Floyd", "title": "Wish You Were Here"},
        {"artist": "Radiohead", "title": "Creep"},
        {"artist": "The Red Pears", "title": "Flowers"}
    ]
    
    for case in test_cases:
        artist = case["artist"]
        title = case["title"]
        print(f"\n🔍 Searching Ultimate Guitar URL for '{artist} - {title}'...")
        
        ug_url = service.search_ultimate_guitar_url(artist, title)
        
        if ug_url:
            print(f"  ✨ Found Ultimate Guitar URL: {ug_url}")
            print(f"  📥 Scraping chords from URL...")
            chords = service.scrape_ultimate_guitar_chords(ug_url)
            
            if chords:
                print(f"  🎉 Chords retrieved successfully! ({len(chords.split())} chords found)")
                # Print a preview of first 15 chords
                preview = " ".join(chords.split()[:15])
                print(f"  📝 Preview: {preview} ...")
                
                # Check structure
                if " " in chords and len(chords) > 0:
                    print("  ✅ Structure check: Chords are space-separated strings as expected!")
                else:
                    print("  ❌ Structure check: Chords are not formatted correctly.")
            else:
                print("  ❌ Failed to extract/parse chords from the page.")
        else:
            print("  ❌ No Ultimate Guitar page found for this song.")
            
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

if __name__ == "__main__":
    main()
