from ytmusicapi import YTMusic
from ..config import Config

class AuthenticationError(Exception):
    pass

class YTMusicService:
    def __init__(self):
        # Browser auth has full access (read + write with real likeStatus support)
        try:
            self.yt_browser = YTMusic(Config.BROWSER_AUTH_FILE)
            # Verify browser auth is valid
            self.yt_browser.get_library_playlists(limit=1)
            # Use browser auth as the primary client for all operations
            self.yt = self.yt_browser 
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Warning: Browser auth not available or expired ({e}). Falling back to OAuth.")
            self.yt_browser = None
            
            # Fall back to OAuth for write operations if browser auth is not available
            try:
                self.yt = YTMusic(Config.OAUTH_FILE)
                self.yt.get_library_playlists(limit=1)
            except Exception as oauth_e:
                raise AuthenticationError(
                    "YouTube Music authentication failed for both Browser and OAuth.\n"
                    f"Browser error: {e}\nOAuth error: {oauth_e}"
                )

    def get_library_songs(self, limit=None):
        """
        Fetches songs from the library.
        If limit is None, fetches all (can be time consuming).
        """
        return self.yt.get_library_songs(limit=limit)

    def get_library_playlists(self):
        """Fetches all playlists in the user's library."""
        return self.yt.get_library_playlists()
        
    def get_song(self, video_id):
        """Fetches details for a specific song."""
        return self.yt.get_song(video_id)

    
    def get_artist_new_releases(self, artist_id):
        """
        Fetches the latest releases (Singles/Albums) for an artist.
        Returns a list of album/single objects.
        """
        try:
            artist = self.yt.get_artist(artist_id)
        except Exception as e:
            print(f"Error fetching artist {artist_id}: {e}")
            return []

        # distinct 'Singles', 'Albums' from the artist details
        releases = []
        if 'singles' in artist and 'results' in artist['singles']:
            releases.extend(artist['singles']['results'])
        
        if 'albums' in artist and 'results' in artist['albums']:
            releases.extend(artist['albums']['results'])
            
        return releases

    def get_album_songs(self, browse_id):
        """Returns songs from an album/single."""
        try:
            album = self.yt.get_album(browse_id)
            return album.get('tracks', [])
        except Exception as e:
            print(f"Error fetching album {browse_id}: {e}")
            return []

    def get_new_releases(self):
        """Fetches all new releases albums from the explore tab."""
        try:
            body = {"browseId": "FEmusic_new_releases_albums"}
            response = self.yt._send_request("browse", body)
            
            from ytmusicapi.parsers.explore import parse_album, parse_content_list
            tabs = response.get('contents', {}).get('singleColumnBrowseResultsRenderer', {}).get('tabs', [])
            if not tabs:
                return []
            contents = tabs[0].get('tabRenderer', {}).get('content', {}).get('sectionListRenderer', {}).get('contents', [])
            if not contents:
                return []
            
            grid_or_shelf = contents[0]
            if 'gridRenderer' in grid_or_shelf:
                items = grid_or_shelf['gridRenderer'].get('items', [])
                return parse_content_list(items, parse_album)
            elif 'musicShelfRenderer' in grid_or_shelf:
                items = grid_or_shelf['musicShelfRenderer'].get('contents', [])
                return parse_content_list(items, parse_album)
        except Exception as e:
            # print(f"Error fetching new releases: {e}")
            pass
            
        return []

    def get_album(self, browse_id):
        """Returns album details including release year."""
        return self.yt.get_album(browse_id)

    def remove_playlist_items(self, playlist_id, videos):
        """Removes items from a playlist."""
        return self.yt.remove_playlist_items(playlist_id, videos)

    def search_artist(self, name):
        """Searches for an artist by name and returns the best result."""
        results = self.yt.search(name, filter='artists')
        
        # Try to find an exact match first
        if results:
            for result in results:
                if result.get('artist', '').lower() == name.lower():
                    return result

        # Fallback to searching songs to find exact artist match (useful for collabs)
        song_results = self.yt.search(name, filter='songs')
        if song_results:
            for r in song_results:
                for a in r.get('artists', []):
                    if a.get('name', '').lower() == name.lower():
                        return {
                            'artist': a.get('name'),
                            'browseId': a.get('id')
                        }
                
        # Fallback to the first result
        if results:
            return results[0]
            
        return None

    def create_playlist(self, title, description=""):
        return self.yt.create_playlist(title, description)

    def get_playlist_items(self, playlist_id, limit=None):
        """Returns items in a playlist (OAuth auth, no likeStatus)."""
        try:
            playlist = self.yt.get_playlist(playlist_id, limit=limit)
            return playlist.get('tracks', [])
        except Exception as e:
            print(f"Error fetching playlist {playlist_id}: {e}")
            return []

    def get_playlist_items_with_status(self, playlist_id, limit=None):
        """Returns items in a playlist with accurate likeStatus via browser auth."""
        if self.yt_browser:
            try:
                playlist = self.yt_browser.get_playlist(playlist_id, limit=limit)
                return playlist.get('tracks', [])
            except Exception as e:
                print(f"  Warning: Browser auth playlist fetch failed ({e}). Falling back to OAuth.")
        return self.get_playlist_items(playlist_id, limit=limit)

    def remove_playlist_items(self, playlist_id, video_ids):
        """Removes items from a playlist."""
        if not video_ids:
            return
        return self.yt.remove_playlist_items(playlist_id, video_ids)

    def add_playlist_items(self, playlist_id, video_ids):
        """Adds songs to a playlist."""
        if not video_ids:
            return
        return self.yt.add_playlist_items(playlist_id, video_ids, duplicates=False)

    def rate_song(self, video_id, rating='INDIFFERENT'):
        """Rates a song. rating: 'LIKE', 'DISLIKE', or 'INDIFFERENT'."""
        return self.yt.rate_song(video_id, rating)

    def edit_playlist(self, playlist_id, title=None, description=None, privacyStatus=None, moveItem=None, add_to_top=None):
        """Edits a playlist's metadata or reorders its items."""
        return self.yt.edit_playlist(
            playlistId=playlist_id, 
            title=title, 
            description=description, 
            privacyStatus=privacyStatus, 
            moveItem=moveItem, 
            addToTop=add_to_top
        )

    def get_song_upload_date(self, video_id):
        """
        Fetches the upload date of a song.
        Returns ISO string (YYYY-MM-DD) or None.
        """
        try:
            song = self.yt.get_song(video_id)
            # Try microformat first
            microformat = song.get('microformat', {}).get('microformatDataRenderer', {})
            upload_date = microformat.get('uploadDate')
            
            # If not there, try videoDetails (sometimes has simpler date?)
            # Usually microformat is reliable for YYYY-MM-DD
            if upload_date:
                # Format is usually 2025-01-01...
                return upload_date.split('T')[0] 
                
            return None
        except Exception as e:
            # print(f"Error fetching date for {video_id}: {e}")
            return None
