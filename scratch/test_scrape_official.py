import requests
import re
import html
import json
import urllib.parse

artist = "Sufjan Stevens"
title = "Mystery of Love"
query = f"{artist} {title}"
encoded_query = urllib.parse.quote(query)
url = f"https://www.ultimate-guitar.com/search.php?search_type=title&value={encoded_query}"

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

response = requests.get(url, headers=headers)
match = re.search(r'class="js-store"[^>]*data-content="([^"]+)"', response.text)
if match:
    json_str = html.unescape(match.group(1))
    data = json.loads(json_str)
    
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
    if results:
        print(f"Total results: {len(results)}")
        # Print a few example items completely
        for i in range(min(5, len(results))):
            print(f"\nItem {i+1}:")
            print(json.dumps(results[i], indent=2))
    else:
        print("No results found in data.")
else:
    print("js-store not found.")
