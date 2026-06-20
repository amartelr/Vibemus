import sys
import os
import json
import html
from unittest.mock import patch, MagicMock

sys.path.append(os.getcwd())
from src.services.chord_service import ChordService

# Let's construct a realistic results JSON payload containing 3 mock search results
mock_search_results = [
    {
        "id": 2224643,
        "song_name": "Mystery Of Love",
        "artist_name": "Sufjan Stevens",
        "type": "Chords",
        "votes": 1676,
        "difficulty": "novice",
        "rating": 4.88,
        "version": 1,
        "tonality_name": "G",
        "version_description": "",
        "tab_url": "https://tabs.ultimate-guitar.com/tab/sufjan-stevens/mystery-of-love-chords-2224643"
    },
    {
        "id": 5736203,
        "song_name": "Mystery Of Love Demo",
        "artist_name": "Sufjan Stevens",
        "type": "Chords",
        "votes": 12,
        "difficulty": "novice",
        "rating": 4.90,
        "version": 1,
        "tonality_name": "C",
        "version_description": "Accurate acoustic demo version",
        "tab_url": "https://tabs.ultimate-guitar.com/tab/sufjan-stevens/mystery-of-love-demo-chords-5736203"
    },
    {
        "id": 5812265,
        "song_name": "Mystery Of Love Demo",
        "artist_name": "Sufjan Stevens",
        "type": "Official",
        "votes": 5,
        "difficulty": "intermediate",
        "rating": 4.5,
        "version": 1,
        "tonality_name": "D",
        "version_description": "Interactive official pro tab",
        "tab_url": "https://tabs.ultimate-guitar.com/tab/sufjan-stevens/mystery-of-love-demo-official-5812265"
    }
]

# We nest the mock results just like Ultimate Guitar's real React store JSON structure
mock_store_json = {
    "store": {
        "page": {
            "data": {
                "results": mock_search_results
            }
        }
    }
}

mock_store_json_escaped = html.escape(json.dumps(mock_store_json))
mock_search_html = f'<html><body><div class="js-store" data-content="{mock_store_json_escaped}"></div></body></html>'

# Now we mock the page contents of the tab chords
def get_mock_tab_html(chords_text):
    content_payload = {
        "store": {
            "page": {
                "data": {
                    "tab_view": {
                        "wiki_tab": {
                            "content": chords_text
                        }
                    }
                }
            }
        }
    }
    payload_escaped = html.escape(json.dumps(content_payload))
    return f'<html><body><div class="js-store" data-content="{payload_escaped}"></div></body></html>'

mock_tab_1_html = get_mock_tab_html("[Intro]\n[ch]C[/ch] [ch]D[/ch] [ch]Em[/ch]\n[Verse 1]\n[ch]C[/ch] [ch]D[/ch] [ch]Em[/ch]")
mock_tab_2_html = get_mock_tab_html("[Intro]\n[ch]G[/ch] [ch]Am[/ch] [ch]Bm[/ch]\n[Verse 1]\n[ch]C[/ch] [ch]D[/ch] [ch]Em[/ch]")

def mock_requests_get(url, *args, **kwargs):
    response = MagicMock()
    response.status_code = 200
    if "search.php" in url:
        response.text = mock_search_html
        response.url = url
    elif "mystery-of-love-chords-2224643" in url:
        response.text = mock_tab_1_html
        response.url = url
    elif "mystery-of-love-demo-chords-5736203" in url:
        response.text = mock_tab_2_html
        response.url = url
    else:
        response.status_code = 404
        response.text = "Not Found"
    return response

@patch("requests.get", side_effect=mock_requests_get)
@patch("builtins.input", return_value="2")  # Simulate user selecting option 2 (the Demo chords)
def test_interactive_lookup(mock_input, mock_get):
    print("🚀 Starting Mock Interactive Lookup Test...")
    service = ChordService()
    
    # We call get_chords with bypass_negative_cache=True and interactive=True
    # We mock search_spotify_ids to return empty so it falls back to Ultimate Guitar search immediately
    with patch.object(service, "search_spotify_ids", return_value=[]):
        chords = service.get_chords("Sufjan Stevens", "Mystery of Love", bypass_negative_cache=True, interactive=True)
        
        print("\n🏁 Results Verification:")
        print(f"Chords obtained: {chords}")
        if chords == "G Am Bm C D Em":
            print("✅ SUCCESS! The chords resolved matched the Demo version (option 2) perfectly!")
        else:
            print("❌ FAILURE! Chords did not match expected mock output.")

@patch("requests.get", side_effect=mock_requests_get)
def test_automatic_lookup(mock_get):
    print("\n🚀 Starting Mock Automatic (Silent) Lookup Test...")
    service = ChordService()
    
    with patch.object(service, "search_spotify_ids", return_value=[]):
        chords = service.get_chords("Sufjan Stevens", "Mystery of Love", bypass_negative_cache=True, interactive=False)
        
        print("\n🏁 Results Verification:")
        print(f"Chords obtained: {chords}")
        # Option 1 (Chords v1) has 1676 votes, Option 2 (Demo Chords) has 12 votes.
        # The automatic mode should sort by votes and automatically pick Option 1.
        if chords == "C D Em C D Em":
            print("✅ SUCCESS! Automatic mode successfully selected the chords sheet with the most votes (option 1)!")
        else:
            print("❌ FAILURE! Chords did not match expected mock output.")

if __name__ == "__main__":
    test_interactive_lookup()
    test_automatic_lookup()
