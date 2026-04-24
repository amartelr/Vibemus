import requests

def check_short(video_id):
    url = f"https://www.youtube.com/shorts/{video_id}"
    try:
        # We use a custom User-Agent to avoid being blocked and check the final URL
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.head(url, headers=headers, allow_redirects=True, timeout=5)
        print(f"ID: {video_id} -> Final URL: {response.url}")
        return "/shorts/" in response.url
    except Exception as e:
        print(f"Error checking {video_id}: {e}")
        return False

test_ids = ["oRjO2YFDnSw", "rKAWIhN766A", "dQw4w9WgXcQ"]
for vid in test_ids:
    is_s = check_short(vid)
    print(f"Is Short: {is_s}\n")
