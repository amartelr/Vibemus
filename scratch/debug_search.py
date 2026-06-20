import re
import urllib.parse
import requests

def main():
    artist = "Sufjan Stevens"
    title = "Mystery of Love"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    queries = [
        f'ultimate guitar chords "{artist}" "{title}"',
        f'ultimate guitar tab "{artist}" "{title}"',
        f'site:tabs.ultimate-guitar.com/tab/ "{artist}" "{title}"',
        f'ultimate guitar {artist} {title} chords',
        f'site:tabs.ultimate-guitar.com/tab/ {artist} {title}'
    ]
    
    print("=== DEBUGGING YAHOO & DUCKDUCKGO LOOKUPS ===")
    
    for idx, q in enumerate(queries, 1):
        print(f"\nQuery {idx}: {q}")
        
        # Yahoo Search
        encoded_query = urllib.parse.quote_plus(q)
        yahoo_url = f"https://search.yahoo.com/search?p={encoded_query}"
        try:
            response = requests.get(yahoo_url, headers=headers, timeout=10)
            print(f"  Yahoo HTTP Status: {response.status_code}")
            if response.status_code == 200:
                print(f"  Yahoo HTML Length: {len(response.text)}")
                
                # Check for rate limiting / robot check
                if "cr-iframe" in response.text or "Robot" in response.text or "Captcha" in response.text:
                    print("  ⚠️ Yahoo might be showing a CAPTCHA / robot check!")
                
                # Try regex matching
                matches = re.findall(r"(?:tabs|www)?\.ultimate-guitar\.com/tab/([a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+)", response.text)
                decoded_matches = re.findall(r"(?:tabs|www)?\.ultimate-guitar\.com/tab/([a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+)", urllib.parse.unquote(response.text))
                
                print(f"  Yahoo Regex matches (raw): {matches}")
                print(f"  Yahoo Regex matches (decoded): {decoded_matches}")
        except Exception as e:
            print(f"  Yahoo Error: {e}")
            
        # DDG Search
        ddg_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        try:
            response = requests.get(ddg_url, headers=headers, timeout=10)
            print(f"  DDG HTTP Status: {response.status_code}")
            if response.status_code == 200:
                print(f"  DDG HTML Length: {len(response.text)}")
                
                if "Robot" in response.text or "Captcha" in response.text or "ddg-captcha" in response.text:
                    print("  ⚠️ DuckDuckGo might be showing a CAPTCHA / robot check!")
                    
                matches = re.findall(r"(?:tabs|www)?\.ultimate-guitar\.com/tab/([a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+)", response.text)
                decoded_matches = re.findall(r"(?:tabs|www)?\.ultimate-guitar\.com/tab/([a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+)", urllib.parse.unquote(response.text))
                
                print(f"  DDG Regex matches (raw): {matches}")
                print(f"  DDG Regex matches (decoded): {decoded_matches}")
        except Exception as e:
            print(f"  DDG Error: {e}")

if __name__ == "__main__":
    main()
