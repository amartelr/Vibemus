from src.services.sheets_service import SheetsService

def main():
    sheets = SheetsService()
    songs = sheets.get_songs_records()
    garage_songs = [s for s in songs if s.get('Playlist') == 'Garage']
    print(f"Garage songs: {len(garage_songs)}")
    garage_no_chord = [s for s in garage_songs if not str(s.get('Chord', '')).strip()]
    print(f"Garage songs needing chords: {len(garage_no_chord)}")

if __name__ == "__main__":
    main()
