import re
import urllib.parse
import html
import json
import requests

def main():
    artist = "Sufjan Stevens"
    title = "Mystery of Love"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    query = f"{artist} {title}"
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.ultimate-guitar.com/search.php?search_type=title&value={encoded_query}"
    
    print(f"Direct Searching UG search.php: {url}")
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        print(f"HTTP Status: {response.status_code}")
        if response.status_code != 200:
            print("Failed to fetch.")
            return
            
        # Extract js-store content
        match = re.search(r'class="js-store"[^>]*data-content="([^"]+)"', response.text)
        if not match:
            match = re.search(r'data-content="([^"]+)"[^>]*class="js-store"', response.text)
        if not match:
            match = re.search(r'data-content="([^"]+)"', response.text)
            
        if not match:
            print("Could not find js-store data-content in HTML.")
            return
            
        json_str = html.unescape(match.group(1))
        data = json.loads(json_str)
        
        # Helper to find "results" in the parsed JSON recursively
        def find_results(d):
            if isinstance(d, dict):
                if "results" in d and isinstance(d["results"], list):
                    return d["results"]
                for k, v in d.items():
                    res = find_results(v)
                    if res is not None:
                        return res
            elif isinstance(d, list):
                for item in d:
                    res = find_results(item)
                    if res is not None:
                        return res
            return None
            
        results = find_results(data)
        
        if not results:
            print("No results found in data content structure.")
            # Let's inspect some top keys of the data dictionary to debug
            print(f"Top keys: {list(data.keys())}")
            return
            
        print(f"Found {len(results)} search results in JSON:")
        for idx, r in enumerate(results, 1):
            if not isinstance(r, dict):
                continue
            tab_url = r.get("tab_url")
            type_name = r.get("type")
            artist_name = r.get("artist_name")
            song_name = r.get("song_name")
            
            # Print if it has tab_url
            if tab_url:
                print(f"  [{idx}] {artist_name} - {song_name} | Type: {type_name}")
                print(f"      URL: {tab_url}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
