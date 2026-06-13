import os
from dataclasses import dataclass, field
from typing import List

# --- Data classes ---
@dataclass
class SongEntry:
    name: str               # The song's name without file extension (e.g. "track01")
    path_song: str          # Full path to the audio file (e.g. "C:\...\GameRadios\GameA\track01.mp3")
    path_thumbnail: str     # Full path to the thumbnail PNG for this song (or empty string if none)

@dataclass
class GameRadio:
    game_name: str                                              # Folder name / display name for the game
    path_thumbnails: str                                        # Directory where thumbnails for this game are stored (here: the game folder)
    path_songs: str                                             # Directory where songs for this game are stored (here: the game folder)
    songs: List[SongEntry] = field(default_factory=list)        # List of SongEntry objects for this game
    path_game_thumbnail: str = ""                               # Path to the game's thumbnail (thumbnail.png) (or empty string if missing)

# --- Helper functions ---
def is_audio_file(filename: str) -> bool:
    """
    Return True if filename ends with a supported audio extension.
    Case-insensitive check for .mp3 and .wav files.
    """
    return filename.lower().endswith((".mp3", ".wav"))

def find_thumbnail_for(base_dir: str, song_name: str) -> str:
    """
    Look for a PNG thumbnail named exactly like the song (song_name.png)
    inside base_dir. Return the full path if it exists, otherwise return an empty string.
    """
    candidate = os.path.join(base_dir, f"{song_name}.png")
    return candidate if os.path.isfile(candidate) else ""

def scan_game_radios(root_path: str) -> List[GameRadio]:
    """
    Scan the directory structure and build a list of GameRadio objects.

    Expected structure:
      root_path/lib/default_thumbnail.png        # optional global default thumbnail
      root_path/GameRadios/<GameFolder>/         # each game folder
          thumbnail.png                          # optional game-level thumbnail
          <song>.mp3 / <song>.wav                # audio files
          <song>.png                             # optional per-song thumbnail

    For each song the thumbnail resolution follows this priority:
      1) <song>.png in the game folder
      2) thumbnail.png (game-level)
      3) default_thumbnail.png (root-level)
      4) empty string (no thumbnail)
    """
    games: List[GameRadio] = []

    # Build path to the global default thumbnail and check existence
    default_thumb = os.path.join(root_path, r"lib\default_thumbnail.png")
    default_thumb_exists = os.path.isfile(default_thumb)

    # Path to the GameRadios folder where game subfolders live
    game_radios_dir = os.path.join(root_path, "gameradios")
    if not os.path.isdir(game_radios_dir):
        # If GameRadios folder doesn't exist, return an empty list
        return games

    # Iterate over each entry in GameRadios (sorted for deterministic order)
    for game_name in sorted(os.listdir(game_radios_dir)):
        game_folder = os.path.join(game_radios_dir, game_name)
        # Skip non-directories (files) inside GameRadios
        if not os.path.isdir(game_folder):
            continue

        # For this setup thumbnails and songs live in the same folder
        path_thumbnails = game_folder
        path_songs = game_folder

        # Check for a game-level thumbnail file named "thumbnail.png"
        game_thumb_candidate = os.path.join(game_folder, "thumbnail.png")
        if os.path.isfile(game_thumb_candidate):
            # Use the game-level thumbnail if present
            game_thumb = game_thumb_candidate
        elif default_thumb_exists:
            # Otherwise fall back to the global default thumbnail if it exists
            game_thumb = default_thumb
        else:
            # If neither exists, leave as empty string
            game_thumb = ""

        # Create the GameRadio instance with its metadata
        game = GameRadio(
            game_name=game_name,
            path_thumbnails=path_thumbnails,
            path_songs=path_songs,
            path_game_thumbnail=game_thumb
        )

        # Iterate files inside the game folder to find audio files
        for file_name in sorted(os.listdir(game_folder)):
            file_path = os.path.join(game_folder, file_name)
            # Skip directories and non-files
            if not os.path.isfile(file_path):
                continue
            # If this file is an audio file, create a SongEntry
            if is_audio_file(file_name):
                base_name, _ext = os.path.splitext(file_name)

                # 1) Try song-specific thumbnail: <song>.png
                thumb = find_thumbnail_for(path_thumbnails, base_name)

                # 2) If no song-specific thumbnail, use the game's thumbnail (already resolved above)
                if not thumb:
                    thumb = game.path_game_thumbnail

                # 3) As a final check ensure fallback to global default if somehow still empty
                if not thumb and default_thumb_exists:
                    thumb = default_thumb

                # Construct SongEntry and append to the game's song list
                song = SongEntry(name=base_name, path_song=file_path, path_thumbnail=thumb)
                game.songs.append(song)

        # Append the populated GameRadio object to the results
        games.append(game)

    return games