import browser_cookie3
import requests

try:
    cj = browser_cookie3.chrome()
    url = "https://www.last.fm/es/music/+recommended"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    r = requests.get(url, cookies=cj, headers=headers)
    with open("lastfm_rec.html", "w") as f:
        f.write(r.text)
except Exception as e:
    print(e)
