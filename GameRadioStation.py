import os, json
import random
import threading
import time

from GetRadioData import scan_game_radios, GameRadio, SongEntry
from Logger import Logger
from PlayRadio import RadioController
from typing import Tuple
from PIL import Image
from lib import LCD_1inch28

class GameRadioStation:
    def __init__(self, logger: Logger, controller: RadioController, path_root: str, lcd :LCD_1inch28):
        # DEFINITIONS
        self.CurrentGame = None
        self.CurrentSong = None
        self.logger = logger
        self.path_save_file = os.path.join(path_root, r"lib/settings.json")
        self.lcd = lcd
        self.encoder = None

        # --- Start loading ---
        self.games_list = scan_game_radios(path_root)                               # Get list of available game_radios
        self.controller = controller
        current_game_radio, current_song_entry = self.get_starting_song()           # Get starting game_radio and song
        self.start_song(current_game_radio, current_song_entry)

    # ---------------------------------------------
    # Save / Load current game and song as JSON
    # ---------------------------------------------
    def save_current_state_to_json(self, current_game: GameRadio, current_song: SongEntry) -> None:
        """
        Save the currently selected game and song into a JSON file.
        """
        if not current_song or not current_game:
            self.logger.write("[INFO] [SAVE] No current game or song to save.")
            return

        data = {
            "game_name": current_game.game_name,
            "song_name": current_song.name
        }

        try:
            with open(self.path_save_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            self.logger.write(f"[SAVE] Current state saved: Game='{data['game_name']}', Song='{data['song_name']}'")
        except Exception as e:
            self.logger.write(f"[ERROR] [SAVE] Failed to save state: {e}")

    def get_starting_song(self) -> Tuple[GameRadio, SongEntry]:
        """
        Load the last saved game and song from JSON and restore it if both exist in games_list.
        Does not return early — runs through entirely and checks conditions step by step.
        """

        current_game_radio = None
        current_song_entry = None

        # 1. File exists?
        if not os.path.exists(self.path_save_file):
            self.logger.write("[INFO] No saved state found.")
        else:
            # 2. Load file
            data = None
            try:
                with open(self.path_save_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.logger.write("[INFO] State file loaded successfully.")
            except Exception as e:
                self.logger.write(f"[ERROR] Failed to read state file: {e}")

            if data:
                game_name = data.get("game_name")
                song_name = data.get("song_name")

                # 3. Validate data
                if not game_name or not song_name:
                    self.logger.write("[ERROR] Invalid state file (missing game_name or song_name).")
                else:
                    # 4. Check game
                    matching_game = next((g for g in self.games_list if g.game_name == game_name), None)
                    if matching_game is None:
                        self.logger.write(f"[WARN] Game '{game_name}' not found in games_list.")
                    else:
                        # 5. Check song
                        matching_song = next((s for s in matching_game.songs if s.name == song_name), None)
                        if matching_song is None:
                            self.logger.write(f"[WARN] Song '{song_name}' not found in game '{game_name}'.")
                        else:
                            # 6. Set state
                            current_game_radio = matching_game
                            current_song_entry = matching_song
                            self.logger.write(f"[INFO] Restored saved song '{song_name}' from game '{game_name}'.")

        # 7. Final check, if not set, pick a random one
        if current_game_radio is None or current_song_entry is None:
            self.logger.write("[INFO] No valid game or song could be restored. Selecting random...")
            current_game_radio, current_song_entry = self.controller.get_random_song_entry(self.games_list)
            self.logger.write(
                f"[INFO] NEW song '{current_song_entry.name}' from game '{current_game_radio.game_name}' starting at random offset.")
        return current_game_radio, current_song_entry

    def start_song(self, current_game_radio: GameRadio, current_song_entry: SongEntry):
        # Lock inputs while switching (if encoder is already set)
        if self.encoder is not None:
            self.encoder.lock()
            self.logger.write("[LOCK] Locked input")

        if self.CurrentGame is not current_game_radio:
            self.CurrentGame = current_game_radio
            img = Image.open(current_game_radio.path_game_thumbnail).resize((240, 240))
            self.logger.write(f"[INFO] Showing image... Game-Image-Path: {current_game_radio.path_game_thumbnail}")
            self.lcd.ShowImage(img)
            time.sleep(1)

        img = Image.open(current_song_entry.path_thumbnail).resize((240, 240))
        self.logger.write(f"[INFO] Showing image... Song-Image-Path: {current_song_entry.path_thumbnail}")
        self.lcd.ShowImage(img)

        self.controller.start_playback(current_song_entry)
        self.save_current_state_to_json(current_game_radio, current_song_entry)
        self.CurrentSong = current_song_entry

        # Unlock here
        if self.encoder is not None:
            threading.Timer(0.5, self.encoder.unlock).start()  # unlock asynchronously
            self.logger.write("[UNLOCK] Unlocked input (async)")

    def next_game(self):
        """
        Move to the next game in games_list.
        Wraps around to the start if at the end.
        """
        self.logger.write("[INFO] Switching to next game")

        # Find current index
        try:
            current_index = self.games_list.index(self.CurrentGame)
        except ValueError:
            # If CurrentGame is not in the list, start at 0
            current_index = -1

            # Calculate next index (wrap around using modulo)
        next_index = (current_index + 1) % len(self.games_list)
        next_game = self.games_list[next_index]

        # Set the next game
        self.start_song(next_game, random.choice(next_game.songs))
        self.logger.write(f"[INFO] Switched to game index {next_index}: {self.CurrentGame.game_name}")

        # Unlock here
        if self.encoder is not None:
            threading.Timer(0.2, self.encoder.unlock).start()  # unlock asynchronously
            self.logger.write("[UNLOCK] Unlocked input (async)")

    def switch_song(self, direction: str):
        """
        Switches the current song inside self.CurrentGame.songs.

        Parameters:
            direction: "next" or "prev" to move forward or backward.
        """
        self.logger.write("[INFO] Switching to next song")

        if not self.CurrentGame or not self.CurrentGame.songs:
            self.logger.write("[WARN] No current game or songs available.")
            return

        songs = self.CurrentGame.songs

        # Get current song index
        try:
            current_index = songs.index(self.CurrentSong)
        except AttributeError:
            # First time: no self.CurrentSong yet
            current_index = -1
        except ValueError:
            # Current song not found in list
            current_index = -1

        # Determine next index
        if direction == "next":
            next_index = (current_index + 1) % len(songs)
        elif direction == "prev":
            next_index = (current_index - 1) % len(songs)
        else:
            self.logger.write(f"[ERROR] Invalid direction '{direction}'")
            return

        # Update current song
        self.start_song(self.CurrentGame, songs[next_index])
        self.logger.write(f"[INFO] Switched to song {next_index}: {self.CurrentSong.name}")