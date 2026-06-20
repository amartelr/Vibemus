import json
from src.services.sheets_service import SheetsService
from src.core.manager import Manager

def main():
    sheets = SheetsService()
    artists_records = sheets.get_artists()
    tracked_artists = {Manager._normalize(None, a.get("Artist Name", "")) for a in artists_records}
    
    with open("data/source_cache.json", "r") as f:
        cache = json.load(f)
    
    garage_items = cache.get("Garage", [])
    print(f"Garage cache items: {len(garage_items)}")
    
    untracked = set()
    for item in garage_items:
        art_list = item.get('artists', [])
        if art_list:
            main_artist = art_list[0]['name']
            norm_art = Manager._normalize(None, main_artist)
            if norm_art not in tracked_artists:
                untracked.add(main_artist)
                
    print(f"Untracked artists in Garage cache: {list(untracked)}")

if __name__ == "__main__":
    main()
