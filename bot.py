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

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

def get_credentials():
    """
    Try multiple methods to get credentials securely:
    1. Environment variables
    2. Command line arguments
    3. Secure input prompts
    """
    import getpass
    
    credentials = {}
    
    discord_token = os.getenv("DISCORD_TOKEN")
    if not discord_token and len(sys.argv) > 1:
        discord_token = sys.argv[1]
    if not discord_token:
        print("Discord token not found in environment variables.")
        discord_token = getpass.getpass("Please enter your Discord bot token: ")
    
    credentials['discord_token'] = discord_token
    
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

CREDENTIALS = get_credentials()

if not CREDENTIALS['discord_token']:
    print("No Discord token provided. Bot cannot start.")
    sys.exit(1)

if not CREDENTIALS['spotify_client_id'] or not CREDENTIALS['spotify_client_secret']:
    print("Spotify credentials missing. Bot cannot access Spotify features.")
    sys.exit(1)

os.environ['SPOTIFY_CLIENT_ID'] = CREDENTIALS['spotify_client_id']
os.environ['SPOTIFY_CLIENT_SECRET'] = CREDENTIALS['spotify_client_secret']

bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree
song_queue = asyncio.Queue()
current_voice_client = None
now_playing = None
is_playing = False
processing_queue = False


@bot.event
async def on_ready():
    await tree.sync()
    cleanup_old_files.start()
    print(f"Logged in as {bot.user}")


async def get_queue_list():
    """Helper function to get current queue as a list without emptying it"""
    queue_list = []
    temp_queue = []
    
    while not song_queue.empty():
        try:
            item = song_queue.get_nowait()
            temp_queue.append(item)
            queue_list.append(item)
        except asyncio.QueueEmpty:
            break
    
    for item in temp_queue:
        await song_queue.put(item)
    
    return queue_list


async def skip_to_song(target_song, interaction):
    """Skip songs in queue until we reach the target song"""
    queue_list = await get_queue_list()
    
    # Find the target song
    target_index = -1
    
    # Try to find by exact name match first
    for i, song in enumerate(queue_list):
        if song.lower() == target_song.lower():
            target_index = i
            break
    
    # If not found, try partial match
    if target_index == -1:
        for i, song in enumerate(queue_list):
            if target_song.lower() in song.lower():
                target_index = i
                break
    
    # If still not found, try by position number
    if target_index == -1:
        try:
            pos = int(target_song) - 1
            if 0 <= pos < len(queue_list):
                target_index = pos
        except ValueError:
            pass
    
    if target_index == -1:
        return False, "Song not found in queue"
    
    # Remove songs before the target
    for _ in range(target_index):
        try:
            song_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    
    # Stop current song to trigger next
    if current_voice_client and (current_voice_client.is_playing() or current_voice_client.is_paused()):
        current_voice_client.stop()
    
    return True, f"Skipping to: {queue_list[target_index]}"


async def play_next_song(interaction):
    global now_playing, is_playing, current_voice_client, processing_queue

    if processing_queue:
        print("Already processing queue, ignoring duplicate call")
        return
    
    if song_queue.empty():
        now_playing = None
        is_playing = False
        print("Queue empty, stopping playback")
        return

    try:
        query = await song_queue.get()
        print(f"Got from queue: {query}")
        
        processing_queue = True
        
        if not current_voice_client or not current_voice_client.is_connected():
            if interaction.user.voice and interaction.user.voice.channel:
                print(f"Connecting to voice channel: {interaction.user.voice.channel.name}")
                current_voice_client = await interaction.user.voice.channel.connect()
            else:
                print("User not in voice channel")
                processing_queue = False
                return

        print(f"Starting download: {query}")
        mp3_path = download_song(query)
        print(f"Download result: {mp3_path}")
        
        if not mp3_path:
            print(f"Download failed (None returned): {query}")
            processing_queue = False
            await play_next_song(interaction)
            return
            
        if not os.path.exists(mp3_path):
            print(f"File doesn't exist: {mp3_path}")
            processing_queue = False
            await play_next_song(interaction)
            return

        file_size = os.path.getsize(mp3_path)
        print(f"File ready: {mp3_path} ({file_size} bytes)")
        
        if file_size < 1000:
            print(f"File too small, probably corrupted: {file_size} bytes")
            processing_queue = False
            await play_next_song(interaction)
            return

        if not current_voice_client or not current_voice_client.is_connected():
            print("Voice client disconnected during download")
            processing_queue = False
            return

        if current_voice_client.is_playing():
            print("Stopping current audio")
            current_voice_client.stop()

        now_playing = query
        is_playing = True
        
        print(f"Starting playback: {query}")
        
        ffmpeg_options = {
            'options': '-vn'
        }
        
        def after_playing(error):
            global is_playing, processing_queue
            print(f"after_playing called for: {query}")
            
            if error:
                print(f"Playback error: {error}")
            else:
                print(f"Finished playing: {query}")
            
            is_playing = False
            processing_queue = False
            
            def schedule_next():
                asyncio.run_coroutine_threadsafe(play_next_song(interaction), bot.loop)
            
            bot.loop.call_later(0.5, schedule_next)

        try:
            audio_source = FFmpegPCMAudio(mp3_path, **ffmpeg_options)
            print(f"Audio source created for: {query}")
            
            current_voice_client.play(audio_source, after=after_playing)
            print(f"Playback started: {query}")
            
            try:
                if hasattr(interaction, 'followup'):
                    await interaction.followup.send(f"Now playing: **{query}**")
                elif hasattr(interaction, 'channel') and interaction.channel:
                    await interaction.channel.send(f"Now playing: **{query}**")
            except Exception as msg_error:
                print(f"Could not send message: {msg_error}")
                
        except Exception as play_error:
            print(f"Error starting playback: {play_error}")
            is_playing = False
            processing_queue = False
            await play_next_song(interaction)
            
    except Exception as e:
        print(f"Major error in play_next_song: {e}")
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
        await interaction.followup.send("Join a voice channel first.")
        return

    if not current_voice_client or not current_voice_client.is_connected():
        try:
            current_voice_client = await user.voice.channel.connect()
            print(f"Connected to {user.voice.channel.name}")
        except Exception as e:
            await interaction.followup.send(f"Failed to connect to voice channel: {e}")
            return

    await song_queue.put(query)
    queue_size = song_queue.qsize()
    
    if queue_size == 1 and not is_playing:
        await interaction.followup.send(f"Playing: **{query}**")
        await play_next_song(interaction)
    else:
        await interaction.followup.send(f"Queued: **{query}** (Position: {queue_size})")


@tree.command(name="playlist", description="Queue all songs in a Spotify playlist")
@app_commands.describe(url="Full Spotify playlist URL")
async def playlist(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    user = interaction.user

    if not user.voice or not user.voice.channel:
        await interaction.followup.send("Join a voice channel first.")
        return

    try:
        tracks = get_tracks_from_playlist(url)
        if not tracks:
            await interaction.followup.send("No tracks found in playlist.")
            return

        for track in tracks:
            await song_queue.put(track)

        await interaction.followup.send(f"Queued {len(tracks)} songs from playlist. Starting playback...")

        global current_voice_client, is_playing
        
        if not current_voice_client or not current_voice_client.is_connected():
            current_voice_client = await user.voice.channel.connect()

        if not is_playing:
            await play_next_song(interaction)
            
    except Exception as e:
        await interaction.followup.send(f"Error loading playlist: {e}")


@tree.command(name="skipto", description="Skip to a specific song in the queue")
@app_commands.describe(song="Song name or position number to skip to")
async def skipto(interaction: discord.Interaction, song: str = None):
    await interaction.response.defer()
    
    queue_list = await get_queue_list()
    
    if not queue_list and not now_playing:
        await interaction.followup.send("Queue is empty.")
        return
    
    # If no song specified, show the queue
    if not song:
        message = "**Current Queue:**\n"
        if now_playing:
            message += f"**Now Playing:** {now_playing}\n\n"
        
        if queue_list:
            message += "**Up Next:**\n"
            for i, track in enumerate(queue_list, 1):
                message += f"{i}. {track}\n"
            message += "\nUse `/skipto <song name or number>` to skip to a specific song."
        else:
            message += "No songs in queue."
        
        await interaction.followup.send(message)
        return
    
    # Skip to the specified song
    success, result_message = await skip_to_song(song, interaction)
    
    if success:
        await interaction.followup.send(result_message)
    else:
        await interaction.followup.send(f"Error: {result_message}")


@tree.command(name="pause", description="Pause the current song")
async def pause(interaction: discord.Interaction):
    if current_voice_client and current_voice_client.is_playing():
        current_voice_client.pause()
        await interaction.response.send_message("Paused.")
    else:
        await interaction.response.send_message("Nothing is playing.")


@tree.command(name="resume", description="Resume the paused song")
async def resume(interaction: discord.Interaction):
    if current_voice_client and current_voice_client.is_paused():
        current_voice_client.resume()
        await interaction.response.send_message("Resumed.")
    else:
        await interaction.response.send_message("Nothing is paused.")


@tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction):
    if current_voice_client and (current_voice_client.is_playing() or current_voice_client.is_paused()):
        current_voice_client.stop()
        await interaction.response.send_message("Skipped.")
    else:
        await interaction.response.send_message("Nothing to skip.")


@tree.command(name="stop", description="Stop playing and clear the queue")
async def stop(interaction: discord.Interaction):
    global is_playing, now_playing, processing_queue
    
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
    await interaction.response.send_message("Stopped and cleared queue.")


@tree.command(name="disconnect", description="Disconnect from voice channel")
async def disconnect(interaction: discord.Interaction):
    global current_voice_client, is_playing, now_playing, processing_queue
    
    if current_voice_client:
        await current_voice_client.disconnect()
        current_voice_client = None
        is_playing = False
        now_playing = None
        processing_queue = False
        
        while not song_queue.empty():
            try:
                song_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
                
        await interaction.response.send_message("Disconnected from voice channel.")
    else:
        await interaction.response.send_message("Not connected to a voice channel.")


@tree.command(name="queue", description="Show the current queue")
async def show_queue(interaction: discord.Interaction):
    queue_list = await get_queue_list()
    
    if not queue_list and not now_playing:
        await interaction.response.send_message("Queue is empty.")
        return
    
    message = "**Current Queue:**\n"
    if now_playing:
        message += f"**Now Playing:** {now_playing}\n\n"
    
    if queue_list:
        message += "**Up Next:**\n"
        for i, song in enumerate(queue_list[:10], 1):
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
            f"**Playlist Stats**:\n"
            f"**{stats['name']}**\n"
            f"- Total Songs: {stats['total']}\n"
            f"- Total Duration: {stats['duration_min']} min\n"
            f"- Top Artists: {', '.join(stats['artists'][:5])}{'...' if len(stats['artists']) > 5 else ''}"
        )
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")


@tasks.loop(hours=24)
async def cleanup_old_files():
    now = datetime.now()
    for filename in os.listdir(DOWNLOAD_FOLDER):
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        if os.path.isfile(file_path):
            modified = datetime.fromtimestamp(os.path.getmtime(file_path))
            if now - modified > timedelta(days=30):
                os.remove(file_path)
                print(f"Deleted old file: {filename}")


@bot.event
async def on_voice_state_update(member, before, after):
    global current_voice_client
    
    # If bot is alone in voice channel, disconnect
    if current_voice_client and current_voice_client.channel:
        if len(current_voice_client.channel.members) == 1:
            await current_voice_client.disconnect()
            current_voice_client = None
            print("Bot left empty voice channel")


if __name__ == "__main__":
    try:
        bot.run(CREDENTIALS['discord_token'])
    except Exception as e:
        print(f"Failed to start bot: {e}")
        sys.exit(1)