import os
from yt_dlp import YoutubeDL
import hashlib

DOWNLOAD_FOLDER = "songs"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def sanitize_filename(query):
    return hashlib.md5(query.encode()).hexdigest()

def download_song(query):
    filename = sanitize_filename(query)
    base_filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    
    # Check for existing files with any extension
    possible_extensions = ['.opus', '.webm', '.m4a', '.mp3', '.ogg']
    for ext in possible_extensions:
        existing_file = base_filepath + ext
        if os.path.exists(existing_file):
            print(f"✅ File already exists: {existing_file}")
            return existing_file

    print(f"🔍 Searching for: {query}")

    # Simplified options for reliability
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': False,
        'no_warnings': False,
        'outtmpl': base_filepath + '.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'opus',
            'preferredquality': '192',  # Good quality but more reliable
        }],
        'postprocessor_args': [
            '-ar', '48000',
            '-ac', '2',
        ],
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            print(f"🔍 Extracting info for: {query}")
            info = ydl.extract_info(f"ytsearch1:{query}", download=True)
                        
            if info and 'entries' in info and len(info['entries']) > 0:
                video_title = info['entries'][0].get('title', 'Unknown')
                print(f"✅ Downloaded: {video_title}")
                
                # Check what file was actually created
                print(f"📂 Checking for files with base: {base_filepath}")
                
                # List all files in the download folder to see what was created
                try:
                    all_files = os.listdir(DOWNLOAD_FOLDER)
                    matching_files = [f for f in all_files if f.startswith(filename)]
                    print(f"📁 Files starting with {filename}: {matching_files}")
                except Exception as e:
                    print(f"❌ Error listing files: {e}")
                
                # Check for the created file with any extension
                for ext in possible_extensions:
                    final_filepath = base_filepath + ext
                    if os.path.exists(final_filepath):
                        file_size = os.path.getsize(final_filepath)
                        print(f"✅ Found file: {final_filepath} ({file_size} bytes)")
                        return final_filepath
                
                print(f"❌ No output file found after download")
                return None
            else:
                print(f"❌ No results found for: {query}")
                return None
                    
    except Exception as e:
        print(f"❌ Download error for '{query}': {str(e)}")
        import traceback
        traceback.print_exc()
        return None