import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET")
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
        
    except Exception as e:
        print(f"❌ Error loading Spotify playlist: {e}")
        return []


def get_playlist_stats(url):
    """Get statistics for a Spotify playlist (handles pagination)"""
    try:
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
        
    except Exception as e:
        print(f"❌ Error getting playlist stats: {e}")
        return {
            'name': 'Unknown',
            'total': 0,
            'duration_min': 0,
            'artists': []
        }