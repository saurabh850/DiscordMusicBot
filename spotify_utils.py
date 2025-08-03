import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Initialize Spotify client using environment variables
# (These will be set by the main bot file after secure credential collection)
def get_spotify_client():
    """Get Spotify client using credentials from environment variables"""
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise ValueError("Spotify credentials not found in environment variables. Make sure the main bot has set them.")
    
    return spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=client_id,
        client_secret=client_secret
    ))


def extract_playlist_id(url):
    """Extract playlist ID from various Spotify URL formats"""
    if 'playlist/' in url:
        return url.split('playlist/')[-1].split('?')[0]
    elif 'open.spotify.com' in url:
        return url.split('/')[-1].split('?')[0]
    else:
        return url  # Assume it's already a playlist ID


def get_tracks_from_playlist(url):
    """Get all tracks from a Spotify playlist (handles pagination)"""
    try:
        sp = get_spotify_client()
        playlist_id = extract_playlist_id(url)
        tracks = []
        
        # Get playlist info first
        playlist = sp.playlist(playlist_id)
        print(f"📋 Loading playlist: {playlist['name']}")
        
        # Get all tracks with pagination
        results = sp.playlist_tracks(playlist_id)
        
        while results:
            for item in results['items']:
                if item['track'] and item['track']['name']:  # Check if track exists
                    track = item['track']
                    name = track['name']
                    artist = track['artists'][0]['name'] if track['artists'] else 'Unknown Artist'
                    tracks.append(f"{name} - {artist}")
            
            # Check if there are more tracks (pagination)
            if results['next']:
                results = sp.next(results)
            else:
                break
        
        print(f"✅ Found {len(tracks)} tracks in playlist")
        return tracks
        
    except ValueError as e:
        print(f"❌ Spotify credentials error: {e}")
        return []
    except Exception as e:
        print(f"❌ Error loading Spotify playlist: {e}")
        return []


def get_playlist_stats(url):
    """Get statistics for a Spotify playlist (handles pagination)"""
    try:
        sp = get_spotify_client()
        playlist_id = extract_playlist_id(url)
        
        # Get playlist info
        playlist = sp.playlist(playlist_id)
        playlist_name = playlist['name']
        
        tracks = []
        total_duration = 0
        artists = set()
        
        # Get all tracks with pagination
        results = sp.playlist_tracks(playlist_id)
        
        while results:
            for item in results['items']:
                if item['track'] and item['track']['name']:  # Check if track exists
                    track = item['track']
                    tracks.append(track)
                    
                    # Add duration (convert from ms to minutes)
                    if track['duration_ms']:
                        total_duration += track['duration_ms']
                    
                    # Collect unique artists
                    if track['artists']:
                        artists.add(track['artists'][0]['name'])
            
            # Check if there are more tracks (pagination)
            if results['next']:
                results = sp.next(results)
            else:
                break
        
        return {
            'name': playlist_name,
            'total': len(tracks),
            'duration_min': total_duration // 60000,  # Convert ms to minutes
            'artists': list(artists)
        }
        
    except ValueError as e:
        print(f"❌ Spotify credentials error: {e}")
        return {
            'name': 'Unknown',
            'total': 0,
            'duration_min': 0,
            'artists': []
        }
    except Exception as e:
        print(f"❌ Error getting playlist stats: {e}")
        return {
            'name': 'Unknown',
            'total': 0,
            'duration_min': 0,
            'artists': []
        }