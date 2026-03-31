from src.services.sheets_service import SheetsService

sheets = SheetsService()
songs = sheets.get_songs_records()

matches = [s for s in songs if 'adrianne lenker' in s.get('Artist', '').lower()]
print(f'Total Adrianne Lenker in sheet: {len(matches)}')
for m in matches:
    print(f"Title: {m.get('Title')} | Playlist: {m.get('Playlist')} | Video ID: {m.get('Video ID')}")
