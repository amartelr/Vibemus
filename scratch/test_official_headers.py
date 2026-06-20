import requests

url = "https://tabs.ultimate-guitar.com/tab/sufjan-stevens/mystery-of-love-demo-official-5812265?requested=1"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

response = requests.get(url, headers=headers)
print(f"Status Code: {response.status_code}")
if "js-store" in response.text:
    print("Found js-store!")
else:
    print("js-store not found.")
