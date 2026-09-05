import threading
import sys
import time
from typing import Optional

import vlc  # requires python-vlc and the VLC runtime


class VLCPlayer:
    """Small, thread-safe VLC wrapper with guarded repeat playback."""

    def __init__(self, logger) -> None:
        self.player: Optional[vlc.MediaPlayer] = None
        self._instance = None
        self._media = None
        self._events = None
        self._end_callback = None
        self._lock = threading.RLock()
        self._start_wall_time: Optional[float] = None
        self._start_offset: float = 0.0
        self._path: Optional[str] = None
        self._repeat: bool = False
        self._generation = 0
        self._logger = logger

    def _log_info(self, msg: str) -> None:
        try:
            self._logger.write(f"[INFO] {msg}")
        except Exception as exc:
            self._fallback_log("ERROR", f"logger.write failed while recording {msg!r}", exc)

    def _log_warn(self, msg: str) -> None:
        try:
            self._logger.write(f"[WARN] {msg}")
        except Exception as exc:
            self._fallback_log("ERROR", f"logger.write failed while recording {msg!r}", exc)

    def _log_error(self, msg: str) -> None:
        try:
            self._logger.write(f"[ERROR] {msg}")
        except Exception as exc:
            self._fallback_log("ERROR", f"logger.write failed while recording {msg!r}", exc)

    @staticmethod
    def _fallback_log(level: str, operation: str, error: Exception) -> None:
        try:
            sys.stderr.write(
                f"[{level}] [VLC] {operation}: {type(error).__name__}: {error}\n"
            )
        except (OSError, ValueError):
            return

    def _release_native(self, resource, description: str) -> None:
        if resource is None:
            return
        try:
            release = getattr(resource, "release", None)
            if release:
                release()
            else:
                self._log_warn(f"Native VLC object '{description}' has no release() method.")
        except Exception as exc:
            self._log_warn(f"Could not release native VLC object '{description}': {exc}")

    def _release_resources_locked(self) -> None:
        """Stop and release all native VLC objects owned by this wrapper."""
        if self._events is not None and self._end_callback is not None:
            try:
                self._events.event_detach(vlc.EventType.MediaPlayerEndReached)
            except Exception as exc:
                self._log_warn(f"Could not detach VLC end event: {exc}")

        player = self.player
        media = self._media
        instance = self._instance
        self.player = None
        self._media = None
        self._instance = None
        self._events = None
        self._end_callback = None

        if player is not None:
            try:
                player.stop()
            except Exception as exc:
                self._log_warn(f"Could not stop VLC player: {exc}")
            self._release_native(player, "player")
        self._release_native(media, "media")
        self._release_native(instance, "instance")

    def _on_end(self, event, generation: int, player) -> None:
        """Schedule a repeat only if the callback still belongs to the active player."""
        with self._lock:
            if (
                generation != self._generation
                or player is not self.player
                or not self._repeat
                or not self._path
            ):
                return
            path_snapshot = self._path

        self._log_info("Media ended; scheduling restart (repeat enabled).")

        def restart_worker() -> None:
            time.sleep(0.05)
            # The expected generation makes stop()/play(new_path) win races
            # against this delayed callback.
            if not self.play(
                path_snapshot,
                0.0,
                repeat=True,
                expected_generation=generation,
            ):
                self._log_info("Repeat restart cancelled because playback changed.")

        try:
            threading.Thread(target=restart_worker, daemon=True).start()
        except Exception as exc:
            self._log_error(f"Failed to spawn restart thread: {exc}")

    def play(
        self,
        path: str,
        offset: float = 0.0,
        repeat: bool = True,
        *,
        expected_generation: Optional[int] = None,
    ) -> bool:
        """Start playback and return ``True`` only when VLC accepted it."""
        with self._lock:
            if expected_generation is not None and expected_generation != self._generation:
                return False

            self._generation += 1
            self._release_resources_locked()
            self._path = path
            self._repeat = bool(repeat)

            instance = media = player = None
            try:
                self._log_info(
                    f"Creating VLC instance for path={path!r}, offset={offset}, repeat={self._repeat}"
                )
                instance = vlc.Instance("--no-video", "--quiet")
                self._instance = instance
                media = instance.media_new(path)
                self._media = media
                player = instance.media_player_new()
                self.player = player
                player.set_media(media)

                try:
                    self._events = player.event_manager()
                    generation = self._generation
                    self._end_callback = lambda event: self._on_end(event, generation, player)
                    self._events.event_attach(
                        vlc.EventType.MediaPlayerEndReached,
                        self._end_callback,
                    )
                except Exception as exc:
                    self._log_warn(f"Failed to attach end-of-media event: {exc}")

                play_result = player.play()
                if play_result == -1:
                    raise RuntimeError("VLC rejected play()")

                time.sleep(0.05)
                seek_result = player.set_time(int(offset * 1000))
                if seek_result == -1:
                    time.sleep(0.05)
                    seek_result = player.set_time(int(offset * 1000))
                    if seek_result == -1:
                        raise RuntimeError("VLC rejected set_time()")

                self._start_wall_time = time.time()
                self._start_offset = float(offset)
                self._log_info("Playback started successfully.")
                return True
            except Exception as exc:
                self._log_error(f"Failed to start playback: {exc}")
                self._release_resources_locked()
                self._path = None
                self._repeat = False
                self._start_wall_time = None
                self._start_offset = 0.0
                return False

    def stop(self) -> None:
        """Disable repeat and release the active VLC resources."""
        with self._lock:
            self._generation += 1
            self._repeat = False
            self._path = None
            self._release_resources_locked()
            self._start_wall_time = None
            self._start_offset = 0.0

    def get_playback_offset(self) -> float:
        """Return the current playback offset in seconds, when available."""
        with self._lock:
            if self.player:
                try:
                    t_ms = self.player.get_time()
                    if t_ms is not None and t_ms >= 0:
                        return t_ms / 1000.0
                except Exception as exc:
                    self._log_warn(f"get_time() failed, using wall-clock estimate: {exc}")

            if self._start_wall_time is None:
                return self._start_offset
            return self._start_offset + (time.time() - self._start_wall_time)
