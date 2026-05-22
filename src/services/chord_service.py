import os
import re
import csv
import json
import html
import sqlite3
import urllib.parse
import threading
import requests
from ..config import Config

class ChordService:
    """Service to resolve harmonic progressions (chords) for songs using Chordonomicon and DDG."""

    def __init__(self):
        self.csv_path = Config.CHORDONOMICON_CSV_FILE
        self.db_path = Config.CHORDONOMICON_DB_FILE
        self.cache_path = os.path.join(Config.DATA_DIR, "chord_cache.json")
        self.download_url = "https://huggingface.co/datasets/ailsntua/Chordonomicon/resolve/main/chordonomicon_v2.csv"
        
        self.cache = self._load_cache()
        self._lock = threading.RLock()
        self._call_count = 0
        self._save_interval = 5

    def _load_cache(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load chord cache: {e}")
                return {}
        return {}

    def save_cache(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            try:
                with open(self.cache_path, "w", encoding="utf-8") as f:
                    json.dump(self.cache, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Warning: Could not save chord cache: {e}")

    def _cache_key(self, artist, title):
        return f"{str(artist).lower().strip()}||{str(title).lower().strip()}"

    def ensure_database(self):
        """Ensures that the SQLite database is populated from the Chordonomicon dataset."""
        if os.path.exists(self.db_path):
            return

        print("\n=== Initializing Chordonomicon Database ===")
        # 1. Download CSV if missing
        if not os.path.exists(self.csv_path):
            print(f"Chordonomicon CSV not found. Downloading from Hugging Face...")
            os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
            try:
                response = requests.get(self.download_url, stream=True, timeout=30)
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                block_size = 1024 * 1024  # 1 MB chunks
                downloaded = 0
                
                with open(self.csv_path, "wb") as f:
                    for chunk in response.iter_content(block_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                print(f"\rDownloading dataset: [{percent:5.1f}%] ({downloaded / (1024*1024):.1f}MB / {total_size / (1024*1024):.1f}MB)", end="", flush=True)
                            else:
                                print(f"\rDownloading dataset: {downloaded / (1024*1024):.1f}MB...", end="", flush=True)
                print("\nDownload completed successfully!")
            except Exception as e:
                if os.path.exists(self.csv_path):
                    os.remove(self.csv_path)
                raise RuntimeError(f"Failed to download Chordonomicon dataset: {e}")

        # 2. Build SQLite DB
        print("Indexing Chordonomicon dataset into SQLite database...")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chord_progression (
                spotify_song_id TEXT PRIMARY KEY,
                chords TEXT
            )
        """)
        
        # Read CSV and batch insert into SQLite
        try:
            with open(self.csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                
                # Check columns to ensure we have the correct field names
                fieldnames = reader.fieldnames
                if not fieldnames or "spotify_song_id" not in fieldnames or "chords" not in fieldnames:
                    raise KeyError(f"Missing required columns in CSV. Found: {fieldnames}")
                
                batch = []
                batch_size = 50000
                count = 0
                
                for row in reader:
                    song_id = row.get("spotify_song_id")
                    chords = row.get("chords")
                    if song_id and chords:
                        batch.append((song_id.strip(), chords.strip()))
                        
                    if len(batch) >= batch_size:
                        cursor.executemany(
                            "INSERT OR IGNORE INTO chord_progression (spotify_song_id, chords) VALUES (?, ?)", 
                            batch
                        )
                        count += len(batch)
                        print(f"Indexed {count} songs...", flush=True)
                        batch = []
                
                if batch:
                    cursor.executemany(
                        "INSERT OR IGNORE INTO chord_progression (spotify_song_id, chords) VALUES (?, ?)", 
                        batch
                    )
                    count += len(batch)
                
                # Create index for rapid lookup
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_spotify_id ON chord_progression(spotify_song_id)")
                conn.commit()
                print(f"Successfully indexed {count} songs in SQLite database.")
                
        except Exception as e:
            conn.close()
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            raise RuntimeError(f"Failed to index Chordonomicon CSV into SQLite: {e}")
        finally:
            conn.close()

    def search_spotify_ids(self, artist: str, title: str) -> list:
        """Searches Yahoo and DuckDuckGo for spotify track links matching artist and title."""
        spotify_ids = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        # Strategy 1: Yahoo Search (Consistently returns 200)
        # We try 3 query configurations of decreasing specificity
        yahoo_queries = [
            f'site:open.spotify.com/track "{artist}" "{title}"',
            f'spotify track "{artist}" "{title}"',
            f'spotify track {artist} {title}'
        ]

        for i, q in enumerate(yahoo_queries):
            encoded_query = urllib.parse.quote_plus(q)
            url = f"https://search.yahoo.com/search?p={encoded_query}"
            try:
                import time
                time.sleep(1.0)
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    decoded_content = urllib.parse.unquote(response.text)
                    matches = re.findall(r"spotify\.com/track/([a-zA-Z0-9]{22})", decoded_content)
                    if matches:
                        for track_id in matches:
                            if track_id not in spotify_ids:
                                spotify_ids.append(track_id)
                        print(f"    ✨ Yahoo resolved {len(spotify_ids)} Spotify track ID(s) on query variation {i}")
                        break
            except Exception as e:
                print(f"    Warning: Yahoo query '{q}' failed: {e}")

        # Strategy 2: DuckDuckGo Fallback (in case Yahoo yields nothing)
        if not spotify_ids:
            ddg_queries = [
                f'site:open.spotify.com/track "{artist}" "{title}"',
                f"site:open.spotify.com/track {artist} {title}"
            ]
            for i, q in enumerate(ddg_queries):
                encoded_query = urllib.parse.quote_plus(q)
                url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
                try:
                    import time
                    time.sleep(1.0)
                    response = requests.get(url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        decoded_content = urllib.parse.unquote(response.text)
                        matches = re.findall(r"spotify\.com/track/([a-zA-Z0-9]{22})", decoded_content)
                        if matches:
                            for track_id in matches:
                                if track_id not in spotify_ids:
                                    spotify_ids.append(track_id)
                            print(f"    ✨ DuckDuckGo fallback resolved {len(spotify_ids)} Spotify track ID(s)")
                            break
                except Exception as e:
                    pass

        return spotify_ids

    def search_ultimate_guitar_url(self, artist: str, title: str, interactive: bool = False) -> str:
        """Searches Ultimate Guitar directly, with fallbacks to Yahoo and DuckDuckGo."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        # 1. Try Direct Search on Ultimate Guitar first
        direct_matches = []
        try:
            query = f"{artist} {title}"
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.ultimate-guitar.com/search.php?search_type=title&value={encoded_query}"
            
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                match = re.search(r'class="js-store"[^>]*data-content="([^"]+)"', response.text)
                if not match:
                    match = re.search(r'data-content="([^"]+)"[^>]*class="js-store"', response.text)
                if not match:
                    match = re.search(r'data-content="([^"]+)"', response.text)
                
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
                        for r in results:
                            if not isinstance(r, dict):
                                continue
                            tab_url = r.get("tab_url")
                            if not tab_url or not tab_url.startswith("http"):
                                continue
                            
                            direct_matches.append({
                                "tab_url": tab_url,
                                "type": r.get("type", "Unknown"),
                                "rating": r.get("rating", 0.0),
                                "votes": r.get("votes", 0),
                                "difficulty": r.get("difficulty", ""),
                                "version": r.get("version", 1),
                                "version_description": r.get("version_description", ""),
                                "tonality_name": r.get("tonality_name", "")
                            })
        except Exception as e:
            print(f"    Warning: Direct Ultimate Guitar search failed: {e}")

        # If we got direct matches, handle them!
        if direct_matches:
            # Deduplicate by tab_url
            seen_urls = set()
            unique_direct = []
            for item in direct_matches:
                if item["tab_url"] not in seen_urls:
                    seen_urls.add(item["tab_url"])
                    unique_direct.append(item)
            
            if interactive:
                print(f"\n🤔 Multiple chord sheets found on Ultimate Guitar for '{artist} - {title}':")
                for idx, item in enumerate(unique_direct, 1):
                    # Style labels with colors
                    t = item["type"]
                    if t == "Chords":
                        type_label = "\033[1;92m(Chords)\033[0m"
                    elif "Tabs" in t or "Tab" in t:
                        type_label = "\033[1;94m(Tab)\033[0m"
                    elif t == "Official":
                        type_label = "\033[1;93m(Official)\033[0m"
                    else:
                        type_label = f"\033[1;90m({t})\033[0m"
                        
                    meta_parts = []
                    if item["version"] > 1:
                        meta_parts.append(f"v{item['version']}")
                    if item["rating"] > 0:
                        meta_parts.append(f"{item['rating']:.2f} ★")
                    if item["votes"] > 0:
                        meta_parts.append(f"{item['votes']} votes")
                    if item["tonality_name"]:
                        meta_parts.append(f"Key: {item['tonality_name']}")
                    if item["difficulty"]:
                        meta_parts.append(f"Diff: {item['difficulty']}")
                        
                    meta_str = " | ".join(meta_parts)
                    meta_suffix = f" [{meta_str}]" if meta_parts else ""
                    
                    print(f"  [{idx}] {item['tab_url']} {type_label}{meta_suffix}")
                    if item["version_description"]:
                        print(f"      \033[3mDesc: {item['version_description']}\033[0m")
                
                try:
                    choice = input(f"\nSelect an option [1-{len(unique_direct)}] (default 1): ").strip()
                    if not choice:
                        selected_url = unique_direct[0]["tab_url"]
                    else:
                        idx = int(choice) - 1
                        if 0 <= idx < len(unique_direct):
                            selected_url = unique_direct[idx]["tab_url"]
                        else:
                            print("⚠️ Invalid choice. Defaulting to option [1].")
                            selected_url = unique_direct[0]["tab_url"]
                except Exception:
                    selected_url = unique_direct[0]["tab_url"]
                return selected_url
            else:
                # Automatic mode: Filter to type "Chords", sort by votes desc
                chords_only = [item for item in unique_direct if item["type"] == "Chords"]
                if chords_only:
                    chords_only.sort(key=lambda x: (x["votes"], x["rating"]), reverse=True)
                    return chords_only[0]["tab_url"]
                
                chords_in_url = [item for item in unique_direct if "chords" in item["tab_url"].lower()]
                if chords_in_url:
                    return chords_in_url[0]["tab_url"]
                
                return unique_direct[0]["tab_url"]

        # 2. Fallback to Yahoo + DuckDuckGo search engines if direct search yielded nothing
        print("  🔍 Direct search yielded 0 results. Falling back to search engine queries...")
        queries = [
            f'ultimate guitar chords "{artist}" "{title}"',
            f'ultimate guitar tab "{artist}" "{title}"',
            f'site:tabs.ultimate-guitar.com/tab/ "{artist}" "{title}"',
            f'ultimate guitar {artist} {title} chords',
            f'site:tabs.ultimate-guitar.com/tab/ {artist} {title}'
        ]
        
        all_unique_matches = []
        
        # 1. Yahoo Search
        for i, q in enumerate(queries):
            encoded_query = urllib.parse.quote_plus(q)
            url = f"https://search.yahoo.com/search?p={encoded_query}"
            try:
                import time
                time.sleep(0.5)
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    decoded_content = urllib.parse.unquote(response.text)
                    matches = re.findall(r"(?:tabs|www)?\.ultimate-guitar\.com/tab/([a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+)", decoded_content)
                    for m in matches:
                        full_match_url = f"https://tabs.ultimate-guitar.com/tab/{m}"
                        if full_match_url not in all_unique_matches:
                            all_unique_matches.append(full_match_url)
            except Exception as e:
                print(f"    Warning: Yahoo Ultimate Guitar search failed for '{q}': {e}")
                
        # 2. DuckDuckGo Fallback
        if not all_unique_matches or len(all_unique_matches) < 3:
            for q in queries[:3]:
                encoded_query = urllib.parse.quote_plus(q)
                url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
                try:
                    import time
                    time.sleep(0.5)
                    response = requests.get(url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        decoded_content = urllib.parse.unquote(response.text)
                        matches = re.findall(r"(?:tabs|www)?\.ultimate-guitar\.com/tab/([a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+)", decoded_content)
                        for m in matches:
                            full_match_url = f"https://tabs.ultimate-guitar.com/tab/{m}"
                            if full_match_url not in all_unique_matches:
                                all_unique_matches.append(full_match_url)
                except Exception:
                    pass
                    
        if not all_unique_matches:
            return ""
            
        if len(all_unique_matches) == 1:
            return all_unique_matches[0]
            
        if interactive:
            print(f"\n🤔 Multiple chord sheets found on Ultimate Guitar for '{artist} - {title}':")
            for idx, url in enumerate(all_unique_matches, 1):
                label = "\033[1;92m(Chords)\033[0m" if "chords" in url else "(Tab/Other)"
                print(f"  [{idx}] {url} {label}")
            
            try:
                choice = input(f"\nSelect an option [1-{len(all_unique_matches)}] (default 1): ").strip()
                if not choice:
                    selected_url = all_unique_matches[0]
                else:
                    idx = int(choice) - 1
                    if 0 <= idx < len(all_unique_matches):
                        selected_url = all_unique_matches[idx]
                    else:
                        print("⚠️ Invalid choice. Defaulting to option [1].")
                        selected_url = all_unique_matches[0]
            except Exception:
                selected_url = all_unique_matches[0]
            return selected_url
        else:
            chords_urls = [url for url in all_unique_matches if "chords" in url]
            if chords_urls:
                return chords_urls[0]
            return all_unique_matches[0]

    def scrape_ultimate_guitar_chords(self, url: str) -> str:
        """Fetches the Ultimate Guitar page and parses the chords using React state hydration class js-store."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"    Warning: Ultimate Guitar returned HTTP {response.status_code}")
                return ""
                
            # Extract content from js-store data-content
            match = re.search(r'class="js-store"[^>]*data-content="([^"]+)"', response.text)
            if not match:
                match = re.search(r'data-content="([^"]+)"[^>]*class="js-store"', response.text)
            if not match:
                match = re.search(r'data-content="([^"]+)"', response.text)
                
            if not match:
                print("    Warning: Could not find js-store data-content in UG HTML")
                return ""
                
            json_str = html.unescape(match.group(1))
            data = json.loads(json_str)
            
            # Helper to find target content recursively
            def find_chords_content(d):
                if isinstance(d, dict):
                    if "content" in d and isinstance(d["content"], str) and "[ch]" in d["content"]:
                        return d["content"]
                    for k, v in d.items():
                        res = find_chords_content(v)
                        if res:
                            return res
                elif isinstance(d, list):
                    for item in d:
                        res = find_chords_content(item)
                        if res:
                            return res
                return None
                
            chords_content = find_chords_content(data)
            
            if not chords_content:
                # Direct lookup fallbacks
                try:
                    chords_content = data['store']['page']['data']['tab_view']['wiki_tab']['content']
                except KeyError:
                    try:
                        chords_content = data['page']['data']['tab_view']['wiki_tab']['content']
                    except KeyError:
                        print("    Warning: Could not find content in UG store JSON")
                        return ""
            
            if not chords_content:
                return ""
                
            # Find all chords marked with [ch]Chord[/ch]
            chords = re.findall(r"\[ch\](.*?)\[/ch\]", chords_content)
            if not chords:
                return ""
                
            # Filter empty values and strip whitespace
            cleaned_chords = [c.strip() for c in chords if c.strip()]
            
            # Return space-separated chords
            return " ".join(cleaned_chords)
        except Exception as e:
            print(f"    Warning: Error scraping UG URL '{url}': {e}")
            return ""

    def get_chords(self, artist: str, title: str, bypass_negative_cache: bool = False, interactive: bool = False, allow_ug: bool = True) -> str:
        """Resolves chord progression for a song by fetching its Spotify IDs and querying SQLite, with Ultimate Guitar fallback."""
        key = self._cache_key(artist, title)
        
        # Check cache first
        with self._lock:
            if key in self.cache:
                cached_val = self.cache[key]
                if not (bypass_negative_cache and cached_val == ""):
                    return cached_val
  
        # Ensure database and index exist
        try:
            self.ensure_database()
        except Exception as e:
            print(f"Error preparing Chordonomicon DB: {e}")
            return ""
 
        # Search for Spotify IDs in Chordonomicon
        print(f"  🔍 Searching chords in Chordonomicon for '{artist} - {title}'...")
        spotify_ids = self.search_spotify_ids(artist, title)
        
        chords_found = ""
        if spotify_ids:
            # Query SQLite for the first matching ID
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                for song_id in spotify_ids:
                    cursor.execute("SELECT chords FROM chord_progression WHERE spotify_song_id = ?", (song_id,))
                    row = cursor.fetchone()
                    if row and row[0]:
                        chords_found = row[0]
                        print(f"  ✨ Found chords in Chordonomicon (Spotify ID: {song_id})")
                        break
            except Exception as e:
                print(f"  Warning: Database lookup failed: {e}")
            finally:
                conn.close()
        
        # Ultimate Guitar Fallback
        if not chords_found:
            print(f"  ❌ No chords found in Chordonomicon for '{artist} - {title}'")
            if allow_ug:
                print(f"  🔍 Searching Ultimate Guitar for '{artist} - {title}'...")
                ug_url = self.search_ultimate_guitar_url(artist, title, interactive=interactive)
                if ug_url:
                    print(f"  ✨ Found Ultimate Guitar URL: {ug_url}")
                    chords_found = self.scrape_ultimate_guitar_chords(ug_url)
                    if chords_found:
                        print(f"  🎉 Successfully retrieved chords from Ultimate Guitar!")
                    else:
                        print(f"  ❌ Failed to parse chords from Ultimate Guitar URL.")
                else:
                    print(f"  ❌ No Ultimate Guitar page found.")
            else:
                print(f"  ℹ️ Ultimate Guitar search disabled for batch sync.")

        # Cache results (including empty string for negative caching)
        with self._lock:
            self.cache[key] = chords_found
            self._call_count += 1
            if self._call_count % self._save_interval == 0:
                self.save_cache()
                
        return chords_found
