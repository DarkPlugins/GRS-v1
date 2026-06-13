import random
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone
from GetRadioData import SongEntry, GameRadio
from mutagen import File as MutagenFile           # requires 'pip install mutagen'

from Logger import Logger
from VLCPlayer import VLCPlayer


class RadioController:
    """
    RadioController provides:
      - random selection of a game and a song (radio station)
      - start_playback() simulates playback starting at a realistic timestamped offset
      - stop_playback() saves the current timestamp and offset in SONGS_PLAYED_LAST

    SONGS_PLAYED_LAST stores:
        {
          "song_name": {
              "stopped_timestamp": "<ISO UTC timestamp>",
              "stopped_offset": <float seconds>
          }
        }

    This allows resuming playback in a realistic way.
    """
    def __init__(self, logger: Logger):
        self.SONGS_PLAYED_LAST: Dict[str, Dict[str, float | str]] = {}
        self.logger = logger
        self.current_song: Optional[SongEntry] = None
        self.time_stamp_song_start: Optional[str] = None
        self.current_start_offset: float = 0.0
        self.vlc = VLCPlayer(logger)
        self.is_playing = False
        self.logger.write("[INFO] RadioController initialized.")

    @staticmethod
    def now_iso() -> str:
        """Return current UTC time as ISO 8601 string with 'Z' suffix."""
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def parse_iso(ts: str) -> datetime:
        """Parse ISO 8601 string (with Z) into a timezone-aware datetime in UTC."""
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))

    @staticmethod
    def is_audio_file(filename: str) -> bool:
        """Return True if the filename ends with a supported audio extension."""
        return filename.lower().endswith((".mp3", ".wav", ".flac", ".m4a"))

    def get_audio_length_seconds(self, path: str) -> float:
        """
        Use mutagen to get the length (duration) of the audio file in seconds.
        Returns float seconds. If mutagen cannot read file, returns 0.0.
        """
        try:
            audio = MutagenFile(path)
            if audio is None or not hasattr(audio, "info") or getattr(audio.info, "length", None) is None:
                self.logger.write(f"[WARN] Failed to read audio length for '{path}'; mutagen returned no info.")
                return 0.0
            length = float(audio.info.length)
            self.logger.write(f"[INFO] Audio length for '{path}' is {length:.2f}s.")
            return length
        except Exception as e:
            self.logger.write(f"[ERROR] Exception reading audio length for '{path}': {e}")
            return 0.0

    def get_random_song_entry(self, games_list) -> Tuple[GameRadio, SongEntry]:
        """Return one random song from a random game. Raises if no songs exist at all."""
        if not games_list:
            self.logger.write("[ERROR] No games available to select from.")
            raise RuntimeError("No games available to select from.")

        games_with_songs = [g for g in games_list if g.songs]
        if not games_with_songs:
            self.logger.write("[ERROR] No songs available in any game.")
            raise RuntimeError("No songs available in any game.")

        selected_game = random.choice(games_with_songs)
        selected_song = random.choice(selected_game.songs)
        self.logger.write(f"[PLAY] Selected random song '{selected_song.name}' from game '{selected_game.game_name}'.")
        return selected_game, selected_song

    def start_playback(self, new_song: SongEntry) -> None:
        """
        Start playback of the given song.
        - If it's the first time the song plays, start at a random offset.
        - If it was stopped earlier, calculate elapsed time since then and
          adjust the offset accordingly (simulate continuous playback).
        - Save the global playback start timestamp.
        """
        try:
            self.stop_playback()        # Stopping old playback

            song_key = new_song.name
            song_path = new_song.path_song
            self.current_song = new_song

            duration = self.get_audio_length_seconds(song_path)
            if duration <= 0:
                duration = 1.0  # Avoid division by zero
                self.logger.write(f"[WARN] Duration unknown for '{song_key}', using fallback 1.0s.")

            last_entry = self.SONGS_PLAYED_LAST.get(song_key)

            if last_entry is None:
                offset = random.uniform(0, max(0.0, duration - 0.001))
                self.logger.write(f"[PLAY] NEW song '{song_key}' starting at random offset {offset:.2f}s / {duration:.2f}s.")
            else:
                try:
                    last_ts = self.parse_iso(str(last_entry["stopped_timestamp"]))
                    last_offset = float(last_entry["stopped_offset"])
                    now_dt = datetime.now(timezone.utc)
                    elapsed = (now_dt - last_ts).total_seconds()
                    offset = (last_offset + elapsed) % duration
                    self.logger.write(
                        f"[PLAY] RESUME song '{song_key}'. "
                        f"Last stopped at offset {last_offset:.2f}s. Elapsed {elapsed:.2f}s. "
                        f"Starting at offset {offset:.2f}s / {duration:.2f}s."
                    )
                except Exception as e:
                    offset = random.uniform(0, max(0.0, duration - 0.001))
                    self.logger.write(f"[WARN] Failed to parse previous entry for '{song_key}': {e}. Starting random offset {offset:.2f}s.")

            self.time_stamp_song_start = self.now_iso()
            self.current_start_offset = offset

            try:
                self.vlc.play(song_path, offset)
                self.time_stamp_song_start = self.now_iso()
                self.current_start_offset = offset
                self.is_playing = True
                self.logger.write(f"[INFO] Playback started for '{song_key}' at offset {offset:.2f}s.")
            except Exception as e:
                self.is_playing = False
                self.logger.write(f"[ERROR] VLC play failed for '{song_key}': {e}")
        except Exception as e:
            self.logger.write(f"[ERROR] start_playback unexpected error: {e}")

    def stop_playback(self) -> None:
        """
        Stop playback and save:
          - the UTC timestamp when the stop happened
          - the current offset in the song
        This allows resuming the song realistically later.
        """
        try:
            if self.current_song is None and not self.is_playing:
                self.logger.write("[STOP] No song is currently playing.")
                return

            song_key = self.current_song.name if self.current_song else "<unknown>"
            ts = self.now_iso()

            try:
                stop_offset = float(self.vlc.get_playback_offset())
            except Exception as e:
                stop_offset = float(self.current_start_offset or 0.0)
                self.logger.write(f"[WARN] Failed to get playback offset from VLC for '{song_key}': {e}. Using {stop_offset:.2f}s.")

            try:
                self.vlc.stop()
            except Exception as e:
                self.logger.write(f"[ERROR] VLC stop failed for '{song_key}': {e}")

            self.SONGS_PLAYED_LAST[song_key] = {
                "stopped_timestamp": ts,
                "stopped_offset": stop_offset
            }

            self.is_playing = False
            self.logger.write(f"[STOP] '{song_key}' stopped at offset {stop_offset:.2f}s. Saved stop time: {ts}")
        except Exception as e:
            self.logger.write(f"[ERROR] stop_playback unexpected error: {e}")