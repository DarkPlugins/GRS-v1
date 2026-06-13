import vlc                          # requires pipp install python-vlc (+ For RaspberryPi Zero WH | apt install vlc -y)
import time
import threading
from typing import Optional

class VLCPlayer:
    """
    Simple VLC wrapper supporting play(path, offset, repeat) and stop().
    Uses libvlc MediaPlayerEndReached event to automatically restart when media ends.
    Logging is done via self.logger; logger must provide a .write(str) method.
    """

    def __init__(self, logger) -> None:
        """
        Initialize player wrapper.
        :param logger: object with .write(string) method used for info/warn/error messages.
                       Messages should be passed already prefixed (example below).
        """
        self.player: Optional[vlc.MediaPlayer] = None
        self._lock = threading.Lock()
        self._start_wall_time: Optional[float] = None
        self._start_offset: float = 0.0
        self._path: Optional[str] = None
        self._repeat: bool = False
        self._logger = logger

    # -- Internal helpers -------------------------------------------------
    def _log_info(self, msg: str) -> None:
        try:
            self._logger.write(f"[INFO] {msg}")
        except Exception:
            # best-effort logging; swallow any exception from logger
            pass

    def _log_warn(self, msg: str) -> None:
        try:
            self._logger.write(f"[WARN] {msg}")
        except Exception:
            pass

    def _log_error(self, msg: str) -> None:
        try:
            self._logger.write(f"[ERROR] {msg}")
        except Exception:
            pass

    def _on_end(self, event) -> None:
        """
        libvlc event callback invoked when media playback reaches the end.
        This runs in libvlc's event thread, so avoid long blocking operations here.
        We schedule a short restart using a thread to avoid reentrancy into libvlc callback.
        """
        # Quick check; do not acquire main lock in libvlc event thread for long.
        if not self._repeat or not self._path:
            self._log_info("Media ended; repeat disabled or path missing.")
            return

        self._log_info("Media ended; scheduling restart (repeat enabled).")

        # Spawn a short-lived thread to restart playback to avoid libvlc callback complications.
        def _restart_worker(path_snapshot: str) -> None:
            # small delay to ensure libvlc finalized end state before restart
            time.sleep(0.05)
            try:
                # Call play to create a fresh player and start from 0.0
                self.play(path_snapshot, 0.0, repeat=True)
            except Exception as exc:
                self._log_error(f"Exception during restart: {exc}")

        try:
            threading.Thread(target=_restart_worker, args=(self._path,), daemon=True).start()
        except Exception as exc:
            # If thread creation fails, log error but do not raise
            self._log_error(f"Failed to spawn restart thread: {exc}")

    # -- Public API -------------------------------------------------------
    def play(self, path: str, offset: float = 0.0, repeat: bool = True) -> None:
        """
        Start playback at given offset (seconds). If repeat is True, the track will restart
        automatically whenever it ends.
        Uses set_time(ms) after play to seek reliably.
        """
        with self._lock:
            # Stop any existing player first
            if self.player:
                try:
                    self._log_info("Stopping existing player before starting new playback.")
                    # detach events by stopping and dropping reference
                    self.player.stop()
                except Exception as exc:
                    self._log_warn(f"Exception while stopping existing player: {exc}")
                finally:
                    self.player = None

            self._path = path
            self._repeat = bool(repeat)

            self._log_info(f"Creating VLC instance for path={path!r}, offset={offset}, repeat={self._repeat}")
            try:
                instance = vlc.Instance('--no-video', '--quiet')
                media = instance.media_new(path)
                player = instance.media_player_new()
                player.set_media(media)
            except Exception as exc:
                self._log_error(f"Failed to create VLC player: {exc}")
                raise

            # Attach end-of-media event to enable repeat
            try:
                events = player.event_manager()
                # EventType.MediaPlayerEndReached triggers when playback finishes
                events.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_end)
            except Exception as exc:
                # If event attach fails, log and continue; repeat may not work reliably.
                self._log_warn(f"Failed to attach end-of-media event: {exc}")

            # Start playback and seek to requested offset
            try:
                player.play()
                # Small sleep to allow libvlc to initialize; adjust if necessary on slow systems
                time.sleep(0.05)
                try:
                    player.set_time(int(offset * 1000))
                except Exception:
                    # Retry once after brief wait
                    time.sleep(0.05)
                    player.set_time(int(offset * 1000))
            except Exception as exc:
                self._log_error(f"Failed to start playback or seek: {exc}")
                raise

            # Save player and timing info
            self.player = player
            self._start_wall_time = time.time()
            self._start_offset = float(offset)
            self._log_info("Playback started successfully.")

    def stop(self) -> None:
        """
        Stop playback and disable repeat. Does not explicitly release the libvlc instance;
        it drops the reference to allow cleanup by garbage collection.
        """
        with self._lock:
            self._repeat = False
            if not self.player:
                self._log_info("Stop called but no active player.")
                self._start_wall_time = None
                self._start_offset = 0.0
                return
            try:
                self._log_info("Stopping player.")
                self.player.stop()
            except Exception as exc:
                self._log_warn(f"Exception while stopping player: {exc}")
            finally:
                self.player = None
                self._start_wall_time = None
                self._start_offset = 0.0
                self._log_info("Player stopped.")

    def get_playback_offset(self) -> float:
        """
        Return current offset in seconds (approx). If not playing, returns last known offset.
        Uses VLC's get_time() if available, otherwise calculates from wall-clock.
        """
        with self._lock:
            if self.player:
                try:
                    t_ms = self.player.get_time()
                    if t_ms is not None and t_ms >= 0:
                        return t_ms / 1000.0
                except Exception as exc:
                    # If getting time fails, fall back to wall-clock estimate
                    self._log_warn(f"get_time() failed, using wall-clock estimate: {exc}")

            if self._start_wall_time is None:
                return self._start_offset
            return self._start_offset + (time.time() - self._start_wall_time)
