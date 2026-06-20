import sys
import os
sys.path.append(os.getcwd())

from src.services.sheets_service import SheetsService

def main():
    sheets = SheetsService()
    songs = sheets.get_songs_records()
    garage_songs = [s for s in songs if s.get('Playlist') == 'Garage']
    print(f"Total Garage songs: {len(garage_songs)}")
    
    analyzed_songs = [s for s in garage_songs if str(s.get('Tonality', '')).strip()]
    print(f"Garage songs with harmonic analysis: {len(analyzed_songs)}")
    
    print("\nHarmonic analysis results in Google Sheet (Top 10):")
    for idx, s in enumerate(analyzed_songs[:10], 1):
        print(f"{idx}. {s.get('Artist')} - {s.get('Title')}")
        print(f"   Tonality:    {s.get('Tonality')}")
        print(f"   Progression: {s.get('Progression')}")
        print(f"   Complexity:  {s.get('Complex')}")
        print(f"   Style:       {s.get('Style')}\n")

if __name__ == "__main__":
    main()
