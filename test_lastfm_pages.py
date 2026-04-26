import browser_cookie3
import requests
import re

try:
    cj = browser_cookie3.chrome()
    url = "https://www.last.fm/es/music/+recommended/artists?page=50"
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, cookies=cj, headers=headers)
    matches = re.findall(r'<a[^>]+class="[^"]*link-block-target[^"]*"[^>]*>([^<]+)</a>', r.text)
    artists = list(set([m.strip() for m in matches if m.strip()]))
    print(f"Page 50 artists: {len(artists)}")
    if len(artists) == 0:
        print("No artists found.")
except Exception as e:
    print(e)
