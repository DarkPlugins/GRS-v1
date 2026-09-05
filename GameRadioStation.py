import os
import json
import random
import tempfile
import time
from collections import OrderedDict

from GetRadioData import scan_game_radios, GameRadio, SongEntry
from Logger import Logger
from PlayRadio import RadioController
from typing import Tuple
from PIL import Image
from lib import LCD_1inch28

class GameRadioStation:
    IMAGE_CACHE_SIZE = 8

    def __init__(self, logger: Logger, controller: RadioController, path_root: str, lcd :LCD_1inch28):
        # DEFINITIONS
        self.CurrentGame = None
        self.CurrentSong = None
        self.logger = logger
        self.path_save_file = os.path.join(path_root, "lib", "last_run.json")
        self.lcd = lcd
        self.encoder = None
        self._image_cache = OrderedDict()
        self._image_signatures = {}

        # --- Start loading ---
        self.games_list = scan_game_radios(path_root)                               # Get list of available game_radios
        self.controller = controller
        if not self.games_list:
            self.logger.write("[ERROR] No playable game radios found.")
            return

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

        temp_path = None
        try:
            save_dir = os.path.dirname(self.path_save_file)
            os.makedirs(save_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=save_dir,
                prefix="last-run-",
                suffix=".tmp",
                delete=False,
            ) as f:
                temp_path = f.name
                json.dump(data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.path_save_file)
            self.logger.write(f"[SAVE] Current state saved: Game='{data['game_name']}', Song='{data['song_name']}'")
        except Exception as e:
            self.logger.write(f"[ERROR] [SAVE] Failed to save state: {e}")
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

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

            if data is not None and not isinstance(data, dict):
                self.logger.write("[ERROR] Invalid state file (expected a JSON object).")
                data = None

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

    def _show_image(self, path: str, description: str) -> bool:
        """Display an image if it is available without breaking playback."""
        if not path or not os.path.isfile(path):
            self.logger.write(f"[WARN] {description} not found: {path!r}")
            return False

        try:
            if not hasattr(self, "_image_signatures"):
                self._image_signatures = {}
            stat = os.stat(path)
            signature = (stat.st_mtime_ns, stat.st_size)
            image = self._image_cache.pop(path, None)
            cached_signature = self._image_signatures.pop(path, None)
            if image is None or cached_signature != signature:
                if image is not None:
                    image.close()
                with Image.open(path) as source:
                    image = source.convert("RGB").resize((240, 240))
                self._image_signatures[path] = signature
            self._image_cache[path] = image
            while len(self._image_cache) > self.IMAGE_CACHE_SIZE:
                old_path, old_image = self._image_cache.popitem(last=False)
                self._image_signatures.pop(old_path, None)
                try:
                    old_image.close()
                except Exception as exc:
                    self.logger.write(f"[WARN] Could not release cached image '{old_path}': {exc}")

            self.logger.write(f"[INFO] Showing image... {description}: {path}")
            self.lcd.ShowImage(image)
            return True
        except Exception as exc:
            self.logger.write(f"[WARN] Could not show {description} '{path}': {exc}")
            return False

    def close(self):
        """Release cached image buffers during application shutdown."""
        if not hasattr(self, "_image_cache"):
            return
        for image in self._image_cache.values():
            try:
                image.close()
            except Exception as exc:
                self.logger.write(f"[WARN] Could not release cached image: {exc}")
        self._image_cache.clear()
        if hasattr(self, "_image_signatures"):
            self._image_signatures.clear()

    def start_song(self, current_game_radio: GameRadio, current_song_entry: SongEntry) -> bool:
        if not current_game_radio or not current_song_entry:
            self.logger.write("[WARN] Cannot start an empty game or song selection.")
            return False

        if self.CurrentGame is not current_game_radio:
            self._show_image(current_game_radio.path_game_thumbnail, "game image")
            time.sleep(0.15)

        self._show_image(current_song_entry.path_thumbnail, "song image")

        if not self.controller.start_playback(current_song_entry):
            self.logger.write(f"[ERROR] Could not start playback for '{current_song_entry.name}'.")
            return False

        self.CurrentGame = current_game_radio
        self.CurrentSong = current_song_entry
        self.save_current_state_to_json(current_game_radio, current_song_entry)
        return True


    def next_game(self):
        """
        Move to the next game in games_list.
        Wraps around to the start if at the end.
        """
        self.logger.write("[INFO] Switching to next game")

        if not self.games_list:
            self.logger.write("[WARN] No game radios available.")
            return

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
        if self.start_song(next_game, random.choice(next_game.songs)):
            self.logger.write(f"[INFO] Switched to game index {next_index}: {self.CurrentGame.game_name}")


    def switch_song(self, direction: str):
        """
        Switches the current song inside self.CurrentGame.songs.

        Parameters:
            direction: "next" or "prev" to move forward or backward.
        """
        self.logger.write(f"[INFO] Switching to {direction} song")

        if not self.CurrentGame or not self.CurrentGame.songs:
            self.logger.write("[WARN] No current game or songs available.")
            return

        songs = self.CurrentGame.songs

        # Get current song index
        try:
            current_index = songs.index(self.CurrentSong)
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
        if self.start_song(self.CurrentGame, songs[next_index]):
            self.logger.write(f"[INFO] Switched to song {next_index}: {self.CurrentSong.name}")
