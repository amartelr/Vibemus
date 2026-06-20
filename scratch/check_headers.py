import sys
import os
sys.path.append(os.getcwd())

from src.services.sheets_service import SheetsService

def main():
    sheets = SheetsService()
    
    songs_ws = sheets._get_worksheet("Songs")
    songs_headers = songs_ws.row_values(1)
    
    archived_ws = sheets._get_worksheet("Archived")
    archived_headers = archived_ws.row_values(1)
    
    print("Songs headers:", songs_headers)
    print("Archived headers:", archived_headers)
    
    if songs_headers != archived_headers:
        print("\n[WARNING] Headers do NOT match!")
        print(f"Songs columns count: {len(songs_headers)}")
        print(f"Archived columns count: {len(archived_headers)}")
        
        # Identify differences
        songs_set = set(songs_headers)
        archived_set = set(archived_headers)
        
        only_in_songs = songs_set - archived_set
        only_in_archived = archived_set - songs_set
        
        if only_in_songs:
            print(f"Only in Songs: {only_in_songs}")
        if only_in_archived:
            print(f"Only in Archived: {only_in_archived}")
    else:
        print("\n[SUCCESS] Headers match perfectly!")

if __name__ == "__main__":
    main()
