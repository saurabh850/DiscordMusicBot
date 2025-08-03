Discord Spotify Music Bot

Description:
This is a self-hosted Discord bot that allows users to play music from Spotify and YouTube directly in voice channels. It supports individual songs, full playlists, and provides useful commands such as pause, resume, skip, and queue viewing. The bot is intended for personal or small community use and is designed to be lightweight and flexible.

Goals:
- Enable private, high-quality music playback in Discord using Spotify and YouTube.
- Provide full playlist queuing from Spotify with accurate metadata extraction.
- Support multiple methods for secure credential input (environment variables, CLI, or prompts).
- Automatically manage and clean up downloaded audio files.
- Expose features through Discord's modern slash commands.

Setup Instructions:

1. Install Dependencies

Run the following command to install all necessary Python packages:

    pip install -r requirements.txt

2. Set Up Environment Variables

Preferred method (Linux/macOS/WSL):

    export DISCORD_TOKEN="your_discord_token"
    export SPOTIFY_CLIENT_ID="your_spotify_client_id"
    export SPOTIFY_CLIENT_SECRET="your_spotify_client_secret"
    python bot.py

Windows Command Prompt:

    set DISCORD_TOKEN=your_discord_token
    set SPOTIFY_CLIENT_ID=your_spotify_client_id
    set SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
    python bot.py

Alternatively, you can run the bot by providing the credentials as command-line arguments:

    python bot.py YOUR_DISCORD_TOKEN YOUR_SPOTIFY_CLIENT_ID YOUR_SPOTIFY_CLIENT_SECRET

If neither method is used, the bot will securely prompt for credentials during startup.

3. Folder Structure

Your project should include the following files:

    bot.py
    downloader.py
    spotify_utils.py
    requirements.txt
    README.txt
    songs/            (empty folder for storing downloaded files)

4. Features and Commands

- /play <query>        - Play a song from YouTube or Spotify
- /playlist <url>      - Queue all songs from a Spotify playlist
- /pause               - Pause playback
- /resume              - Resume playback
- /skip                - Skip the current song
- /stop                - Stop playback and clear the queue
- /queue               - Display the current queue
- /disconnect          - Leave the voice channel
- /stats <playlist>    - Show Spotify playlist statistics

The bot will automatically disconnect if left alone in a voice channel and will clean up audio files older than 30 days.

Contact:
For issues or contributions, please create a GitHub issue or fork the repository.
