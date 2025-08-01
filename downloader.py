import os
from yt_dlp import YoutubeDL
import hashlib

DOWNLOAD_FOLDER = "songs"  # Changed to match your bot
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def sanitize_filename(query):
    return hashlib.md5(query.encode()).hexdigest()

def download_song(query):
    filename = sanitize_filename(query)
    # Don't add .mp3 here - yt-dlp will add it during post-processing
    base_filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    final_filepath = base_filepath + ".mp3"

    # Check if already downloaded
    if os.path.exists(final_filepath):
        print(f"✅ File already exists: {final_filepath}")
        return final_filepath

    print(f"🔍 Searching for: {query}")

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',  # Prefer high quality m4a
        'quiet': False,  # Set to False for debugging
        'no_warnings': False,
        'outtmpl': base_filepath + '.%(ext)s',  # Let yt-dlp handle extension
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',  # Maximum MP3 quality
        }],
        'postprocessor_args': [
            '-ar', '48000',  # 48kHz sample rate (Discord's native rate)
            '-ac', '2',      # Stereo
            '-b:a', '320k'   # 320 kbps bitrate
        ],
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            # Search and download
            info = ydl.extract_info(f"ytsearch1:{query}", download=True)
            
            if info and 'entries' in info and len(info['entries']) > 0:
                video_title = info['entries'][0].get('title', 'Unknown')
                print(f"✅ Downloaded: {video_title}")
                
                # Return the final MP3 file path
                if os.path.exists(final_filepath):
                    return final_filepath
                else:
                    print(f"❌ MP3 file not found after download: {final_filepath}")
                    return None
            else:
                print(f"❌ No results found for: {query}")
                return None
                
    except Exception as e:
        print(f"❌ Download error for '{query}': {str(e)}")
        return None