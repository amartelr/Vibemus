from src.services.sheets_service import SheetsService

def main():
    sheets = SheetsService()
    artists = sheets.get_artists()
    print(f"Total tracked artists: {len(artists)}")
    for a in artists[:15]:
        print(f"- {a.get('Artist Name')} ({a.get('Playlist')})")

if __name__ == "__main__":
    main()
