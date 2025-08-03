import os
import discord
from discord.ext import commands, tasks
from discord import app_commands, FFmpegPCMAudio
from downloader import download_song
from spotify_utils import get_tracks_from_playlist, get_playlist_stats
from datetime import datetime, timedelta
import asyncio
import sys

DOWNLOAD_FOLDER = "songs"
# Note: songs folder should already exist

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Secure credentials loading - multiple methods
def get_credentials():
    """
    Try multiple methods to get credentials securely:
    1. Environment variables
    2. Command line arguments
    3. Secure input prompts
    """
    import getpass
    
    credentials = {}
    
    # Try to get Discord token
    discord_token = os.getenv("DISCORD_TOKEN")
    if not discord_token and len(sys.argv) > 1:
        discord_token = sys.argv[1]
    if not discord_token:
        print("Discord token not found in environment variables.")
        discord_token = getpass.getpass("Please enter your Discord bot token: ")
    
    credentials['discord_token'] = discord_token
    
    # Try to get Spotify credentials
    spotify_client_id = os.getenv("SPOTIFY_CLIENT_ID")
    spotify_client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    
    if not spotify_client_id and len(sys.argv) > 2:
        spotify_client_id = sys.argv[2]
    if not spotify_client_secret and len(sys.argv) > 3:
        spotify_client_secret = sys.argv[3]
        
    if not spotify_client_id:
        print("Spotify Client ID not found in environment variables.")
        spotify_client_id = getpass.getpass("Please enter your Spotify Client ID: ")
    
    if not spotify_client_secret:
        print("Spotify Client Secret not found in environment variables.")
        spotify_client_secret = getpass.getpass("Please enter your Spotify Client Secret: ")
    
    credentials['spotify_client_id'] = spotify_client_id
    credentials['spotify_client_secret'] = spotify_client_secret
    
    return credentials

# Get all credentials using secure method
CREDENTIALS = get_credentials()

# Validate required credentials
if not CREDENTIALS['discord_token']:
    print("❌ No Discord token provided. Bot cannot start.")
    sys.exit(1)

if not CREDENTIALS['spotify_client_id'] or not CREDENTIALS['spotify_client_secret']:
    print("❌ Spotify credentials missing. Bot cannot access Spotify features.")
    sys.exit(1)

# Set environment variables for spotify_utils module
os.environ['SPOTIFY_CLIENT_ID'] = CREDENTIALS['spotify_client_id']
os.environ['SPOTIFY_CLIENT_SECRET'] = CREDENTIALS['spotify_client_secret']

bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree
song_queue = asyncio.Queue()
current_voice_client = None
now_playing = None
is_playing = False
processing_queue = False  # Simple flag to prevent multiple queue processing


@bot.event
async def on_ready():
    await tree.sync()
    cleanup_old_files.start()
    print(f"✅ Logged in as {bot.user}")


async def play_next_song(interaction):
    global now_playing, is_playing, current_voice_client, processing_queue

    # Prevent multiple simultaneous calls
    if processing_queue:
        print("⚠️ Already processing queue, ignoring duplicate call")
        return
    
    if song_queue.empty():
        now_playing = None
        is_playing = False
        print("🎵 Queue empty, stopping playback")
        return

    # Don't set processing_queue here - wait until we actually start processing
    
    try:
        query = await song_queue.get()
        print(f"🎵 Got from queue: {query}")
        
        # NOW set the processing flag
        processing_queue = True
        
        # Ensure voice client is connected FIRST
        if not current_voice_client or not current_voice_client.is_connected():
            if interaction.user.voice and interaction.user.voice.channel:
                print(f"🔌 Connecting to voice channel: {interaction.user.voice.channel.name}")
                current_voice_client = await interaction.user.voice.channel.connect()
            else:
                print("❌ User not in voice channel")
                processing_queue = False
                return

        # Download the song
        print(f"⬇️ Starting download: {query}")
        mp3_path = download_song(query)
        print(f"📁 Download result: {mp3_path}")
        
        if not mp3_path:
            print(f"❌ Download failed (None returned): {query}")
            processing_queue = False
            await play_next_song(interaction)
            return
            
        if not os.path.exists(mp3_path):
            print(f"❌ File doesn't exist: {mp3_path}")
            processing_queue = False
            await play_next_song(interaction)
            return

        file_size = os.path.getsize(mp3_path)
        print(f"✅ File ready: {mp3_path} ({file_size} bytes)")
        
        if file_size < 1000:  # Less than 1KB is probably an error
            print(f"❌ File too small, probably corrupted: {file_size} bytes")
            processing_queue = False
            await play_next_song(interaction)
            return

        # Check if voice client is still connected
        if not current_voice_client or not current_voice_client.is_connected():
            print("❌ Voice client disconnected during download")
            processing_queue = False
            return

        # Stop any currently playing audio
        if current_voice_client.is_playing():
            print("⏹️ Stopping current audio")
            current_voice_client.stop()

        now_playing = query
        is_playing = True
        
        print(f"🎵 Starting playback: {query}")
        
        # Simplified FFmpeg options for debugging
        ffmpeg_options = {
            'options': '-vn'
        }
        
        def after_playing(error):
            global is_playing, processing_queue
            print(f"🔄 after_playing called for: {query}")
            
            if error:
                print(f"❌ Playback error: {error}")
            else:
                print(f"✅ Finished playing: {query}")
            
            is_playing = False
            processing_queue = False
            
            # Schedule next song with a small delay
            def schedule_next():
                asyncio.run_coroutine_threadsafe(play_next_song(interaction), bot.loop)
            
            # Use bot's loop to schedule the next song
            bot.loop.call_later(0.5, schedule_next)

        try:
            # Create audio source
            audio_source = FFmpegPCMAudio(mp3_path, **ffmpeg_options)
            print(f"🎧 Audio source created for: {query}")
            
            # Start playing
            current_voice_client.play(audio_source, after=after_playing)
            print(f"▶️ Playback started: {query}")
            
            # Send message to Discord
            try:
                if hasattr(interaction, 'followup'):
                    await interaction.followup.send(f"🎵 Now playing: **{query}**")
                elif hasattr(interaction, 'channel') and interaction.channel:
                    await interaction.channel.send(f"🎵 Now playing: **{query}**")
            except Exception as msg_error:
                print(f"⚠️ Could not send message: {msg_error}")
                
        except Exception as play_error:
            print(f"❌ Error starting playback: {play_error}")
            is_playing = False
            processing_queue = False
            await play_next_song(interaction)
            
    except Exception as e:
        print(f"❌ Major error in play_next_song: {e}")
        import traceback
        traceback.print_exc()
        processing_queue = False
        is_playing = False


@tree.command(name="play", description="Play a song from YouTube or Spotify")
@app_commands.describe(query="Name of the song or Spotify track")
async def play(interaction: discord.Interaction, query: str):
    global current_voice_client, is_playing

    await interaction.response.defer()
    user = interaction.user

    if not user.voice or not user.voice.channel:
        await interaction.followup.send("❌ Join a voice channel first.")
        return

    # Connect to voice channel if not connected
    if not current_voice_client or not current_voice_client.is_connected():
        try:
            current_voice_client = await user.voice.channel.connect()
            print(f"✅ Connected to {user.voice.channel.name}")
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to connect to voice channel: {e}")
            return

    # Add to queue
    await song_queue.put(query)
    queue_size = song_queue.qsize()
    
    if queue_size == 1 and not is_playing:
        await interaction.followup.send(f"🎵 Playing: **{query}**")
        await play_next_song(interaction)
    else:
        await interaction.followup.send(f"🎵 Queued: **{query}** (Position: {queue_size})")


@tree.command(name="playlist", description="Queue all songs in a Spotify playlist")
@app_commands.describe(url="Full Spotify playlist URL")
async def playlist(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    user = interaction.user

    if not user.voice or not user.voice.channel:
        await interaction.followup.send("❌ Join a voice channel first.")
        return

    try:
        tracks = get_tracks_from_playlist(url)
        if not tracks:
            await interaction.followup.send("❌ No tracks found in playlist.")
            return

        # Add all tracks to queue WITHOUT downloading them yet
        for track in tracks:
            await song_queue.put(track)

        await interaction.followup.send(f"✅ Queued {len(tracks)} songs from playlist. Starting playback...")

        global current_voice_client, is_playing
        
        # Connect if not connected
        if not current_voice_client or not current_voice_client.is_connected():
            current_voice_client = await user.voice.channel.connect()

        # Start playing if nothing is playing (downloads will happen one by one)
        if not is_playing:
            await play_next_song(interaction)
            
    except Exception as e:
        await interaction.followup.send(f"❌ Error loading playlist: {e}")


@tree.command(name="pause", description="Pause the current song")
async def pause(interaction: discord.Interaction):
    if current_voice_client and current_voice_client.is_playing():
        current_voice_client.pause()
        await interaction.response.send_message("⏸️ Paused.")
    else:
        await interaction.response.send_message("⚠️ Nothing is playing.")


@tree.command(name="resume", description="Resume the paused song")
async def resume(interaction: discord.Interaction):
    if current_voice_client and current_voice_client.is_paused():
        current_voice_client.resume()
        await interaction.response.send_message("▶️ Resumed.")
    else:
        await interaction.response.send_message("⚠️ Nothing is paused.")


@tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction):
    if current_voice_client and (current_voice_client.is_playing() or current_voice_client.is_paused()):
        current_voice_client.stop()  # This will trigger the after callback
        await interaction.response.send_message("⏭️ Skipped.")
    else:
        await interaction.response.send_message("⚠️ Nothing to skip.")


@tree.command(name="stop", description="Stop playing and clear the queue")
async def stop(interaction: discord.Interaction):
    global is_playing, now_playing, processing_queue
    
    # Clear the queue
    while not song_queue.empty():
        try:
            song_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    
    if current_voice_client:
        if current_voice_client.is_playing() or current_voice_client.is_paused():
            current_voice_client.stop()
        
    is_playing = False
    now_playing = None
    processing_queue = False
    await interaction.response.send_message("⏹️ Stopped and cleared queue.")


@tree.command(name="disconnect", description="Disconnect from voice channel")
async def disconnect(interaction: discord.Interaction):
    global current_voice_client, is_playing, now_playing, processing_queue
    
    if current_voice_client:
        await current_voice_client.disconnect()
        current_voice_client = None
        is_playing = False
        now_playing = None
        processing_queue = False
        
        # Clear queue
        while not song_queue.empty():
            try:
                song_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
                
        await interaction.response.send_message("👋 Disconnected from voice channel.")
    else:
        await interaction.response.send_message("⚠️ Not connected to a voice channel.")


@tree.command(name="queue", description="Show the current queue")
async def show_queue(interaction: discord.Interaction):
    if song_queue.empty() and not now_playing:
        await interaction.response.send_message("🎵 Queue is empty.")
        return
    
    queue_list = []
    temp_queue = []
    
    # Get items from queue without removing them
    while not song_queue.empty():
        try:
            item = song_queue.get_nowait()
            temp_queue.append(item)
            queue_list.append(item)
        except asyncio.QueueEmpty:
            break
    
    # Put items back in queue
    for item in temp_queue:
        await song_queue.put(item)
    
    message = "🎵 **Current Queue:**\n"
    if now_playing:
        message += f"**Now Playing:** {now_playing}\n\n"
    
    if queue_list:
        message += "**Up Next:**\n"
        for i, song in enumerate(queue_list[:10], 1):  # Show max 10 songs
            message += f"{i}. {song}\n"
        
        if len(queue_list) > 10:
            message += f"... and {len(queue_list) - 10} more songs"
    else:
        message += "No songs in queue."
    
    await interaction.response.send_message(message)


@tree.command(name="stats", description="View statistics of a Spotify playlist")
@app_commands.describe(url="Spotify playlist URL")
async def stats(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    try:
        stats = get_playlist_stats(url)
        await interaction.followup.send(
            f"🎧 **Playlist Stats**:\n"
            f"**{stats['name']}**\n"
            f"- Total Songs: {stats['total']}\n"
            f"- Total Duration: {stats['duration_min']} min\n"
            f"- Top Artists: {', '.join(stats['artists'][:5])}{'...' if len(stats['artists']) > 5 else ''}"
        )
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")


@tasks.loop(hours=24)
async def cleanup_old_files():
    now = datetime.now()
    for filename in os.listdir(DOWNLOAD_FOLDER):
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        if os.path.isfile(file_path):
            modified = datetime.fromtimestamp(os.path.getmtime(file_path))
            if now - modified > timedelta(days=30):
                os.remove(file_path)
                print(f"🧹 Deleted old file: {filename}")


# Error handler for voice client
@bot.event
async def on_voice_state_update(member, before, after):
    global current_voice_client
    
    # If bot is alone in voice channel, disconnect
    if current_voice_client and current_voice_client.channel:
        if len(current_voice_client.channel.members) == 1:  # Only bot left
            await current_voice_client.disconnect()
            current_voice_client = None
            print("🤖 Bot left empty voice channel")


if __name__ == "__main__":
    try:
        bot.run(CREDENTIALS['discord_token'])
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        sys.exit(1)