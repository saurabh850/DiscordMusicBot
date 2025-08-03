import os
import discord
from discord.ext import commands, tasks
from discord import app_commands, FFmpegPCMAudio
from dotenv import load_dotenv
from downloader import download_song
from spotify_utils import get_tracks_from_playlist, get_playlist_stats
from datetime import datetime, timedelta
import asyncio
from os import path

load_dotenv()
DOWNLOAD_FOLDER = "songs"
# Note: songs folder should already exist

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree
song_queue = asyncio.Queue()
current_voice_client = None
now_playing = None
is_playing = False


@bot.event
async def on_ready():
    await tree.sync()
    cleanup_old_files.start()
    print(f"✅ Logged in as {bot.user}")


async def play_next_song(interaction):
    global now_playing, is_playing, current_voice_client

    if song_queue.empty():
        now_playing = None
        is_playing = False
        return

    try:
        query = await song_queue.get()
        print(f"🎵 Downloading: {query}")
        
        # Download the song
        mp3_path = download_song(query)
        print(f"📁 Download returned path: {mp3_path}")
        
        if not mp3_path:
            print(f"❌ download_song returned None for: {query}")
            await play_next_song(interaction)  # Try next song
            return
        
        if not os.path.exists(mp3_path):
            print(f"❌ File doesn't exist at path: {mp3_path}")
            # Let's check what files ARE in the songs folder
            try:
                files_in_folder = os.listdir("songs")
                print(f"📂 Files in songs folder: {files_in_folder}")
            except:
                print("❌ Can't access songs folder")
            await play_next_song(interaction)  # Try next song
            return

        print(f"✅ File exists at: {mp3_path}")
        print(f"📊 File size: {os.path.getsize(mp3_path)} bytes")

        # Ensure voice client is connected
        if not current_voice_client or not current_voice_client.is_connected():
            if interaction.user.voice and interaction.user.voice.channel:
                current_voice_client = await interaction.user.voice.channel.connect()
            else:
                print("❌ User not in voice channel")
                return

        now_playing = query
        is_playing = True
        
        # High quality FFmpeg options
        ffmpeg_options = {
            'options': '-vn -b:a 320k -ar 48000 -ac 2 -filter:a "volume=0.8"'
        }
        
        def after_playing(error):
            if error:
                print(f"❌ Player error: {error}")
            else:
                print(f"✅ Finished playing: {query}")
            
            # Schedule next song
            asyncio.run_coroutine_threadsafe(play_next_song(interaction), bot.loop)

        # Play the audio with high quality options
        audio_source = FFmpegPCMAudio(mp3_path, **ffmpeg_options)
        current_voice_client.play(audio_source, after=after_playing)
        
        print(f"🎵 Now playing: {query}")
        
        # Send now playing message to channel
        try:
            channel = interaction.channel or interaction.followup
            if hasattr(channel, 'send'):
                await channel.send(f"🎵 Now playing: **{query}**")
        except:
            pass  # Ignore if we can't send message
            
    except Exception as e:
        print(f"❌ Error in play_next_song: {e}")
        is_playing = False
        await play_next_song(interaction)  # Try next song


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

        # Add all tracks to queue
        for track in tracks:
            await song_queue.put(track)

        await interaction.followup.send(f"✅ Queued {len(tracks)} songs from playlist.")

        global current_voice_client, is_playing
        
        # Connect if not connected
        if not current_voice_client or not current_voice_client.is_connected():
            current_voice_client = await user.voice.channel.connect()

        # Start playing if nothing is playing
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
    global is_playing, now_playing
    
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
    await interaction.response.send_message("⏹️ Stopped and cleared queue.")


@tree.command(name="disconnect", description="Disconnect from voice channel")
async def disconnect(interaction: discord.Interaction):
    global current_voice_client, is_playing, now_playing
    
    if current_voice_client:
        await current_voice_client.disconnect()
        current_voice_client = None
        is_playing = False
        now_playing = None
        
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


bot.run(os.getenv("DISCORD_TOKEN"))