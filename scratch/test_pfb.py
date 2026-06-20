import urllib.parse
import re
import requests
import time
import sqlite3
import os

def test_ddg(artist, title):
    query = f'site:open.spotify.com/track "{artist}" "{title}"'
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"[DDG] Status: {response.status_code}")
        matches = re.findall(r"spotify\.com/track/([a-zA-Z0-9]{22})", response.text)
        print(f"[DDG] Matches: {matches}")
    except Exception as e:
        print(f"[DDG] Error: {e}")

def test_yahoo(artist, title):
    # Try different query formats
    queries = [
        f'site:open.spotify.com/track "{artist}" "{title}"',
        f'spotify track "{artist}" "{title}"',
        f'spotify track {artist} {title}'
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    for i, q in enumerate(queries):
        encoded_query = urllib.parse.quote_plus(q)
        url = f"https://search.yahoo.com/search?p={encoded_query}"
        try:
            time.sleep(1.0)
            response = requests.get(url, headers=headers, timeout=10)
            print(f"[Yahoo Q{i}] Status: {response.status_code}")
            decoded_content = urllib.parse.unquote(response.text)
            matches = re.findall(r"spotify\.com/track/([a-zA-Z0-9]{22})", decoded_content)
            print(f"[Yahoo Q{i}] Matches: {matches}")
            if matches:
                return matches
        except Exception as e:
            print(f"[Yahoo Q{i}] Error: {e}")
    return []

def lookup_db(track_ids):
    db_path = "data/chordonomicon.db"
    if not os.path.exists(db_path):
        print(f"[DB] Database not found at {db_path}")
        return
    print(f"[DB] Querying database at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        for tid in track_ids:
            cursor.execute("SELECT chords FROM chord_progression WHERE spotify_song_id = ?", (tid,))
            row = cursor.fetchone()
            if row:
                print(f"[DB] Found chords for {tid}:")
                print(row[0][:300] + "...")
                return
        print("[DB] No chords found for the resolved track IDs.")
    except Exception as e:
        print(f"[DB] Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    artist = "Planning for Burial"
    title = "I Want To Die A Beautiful Death"
    print(f"Testing for {artist} - {title}:")
    test_ddg(artist, title)
    track_ids = test_yahoo(artist, title)
    if track_ids:
        lookup_db(track_ids)
