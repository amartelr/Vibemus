from src.services.sheets_service import SheetsService

def main():
    sheets = SheetsService()
    songs = sheets.get_songs_records()
    print(f"Total songs in sheet: {len(songs)}")
    print("First 15 songs:")
    for idx, s in enumerate(songs[:15], 1):
        print(f"{idx}. [{s.get('Playlist')}] {s.get('Artist')} - {s.get('Title')} (Chord: '{s.get('Chord', '')}')")

if __name__ == "__main__":
    main()
