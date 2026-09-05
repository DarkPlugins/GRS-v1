import os
import signal
import threading
import RPi.GPIO as GPIO

from BluetoothService import BluetoothService
from GameRadioStation import GameRadioStation
from Logger import Logger
from PIL import Image
from Settings import Settings
from lib import LCD_1inch28

from Encoder import Encoder
from PlayRadio import RadioController


class Startup:
    """
    Main startup class for initializing logger, display, rotary encoder, and game radio station.
    """
    def __init__(self):
        # Determine the root path of the script
        self.path_root = os.path.dirname(os.path.abspath(__file__))
        self._shutdown_event = threading.Event()
        self._shutdown_done = False
        self.lcd = None
        self.bluetooth_service = None
        self.controller = None
        self.game_radio_station = None
        self.encoder = None

        self.settings = Settings(self.path_root)

        # Initialize logger
        self.logger = Logger(self.path_root, enabled=self.settings.logging_enabled)
        for warning in self.settings.warnings:
            self.logger.write(f"[WARN] [SETTINGS] {warning}")
        signal.signal(signal.SIGINT, self._request_shutdown)
        signal.signal(signal.SIGTERM, self._request_shutdown)

        try:
            # Initialize the TFT display
            self.lcd = LCD_1inch28.LCD_1inch28(**self.settings.lcd)
            self.lcd.Init()
            self.lcd.clear()
            self.show_loading_image()

            self.bluetooth_service = BluetoothService(
                self.logger,
                self.path_root,
                self.settings.bluetooth_targets,
                scan_interval=self.settings.bluetooth_scan_interval,
                auto_start=True,
            )

            self.controller = RadioController(self.logger)
            self.game_radio_station = GameRadioStation(
                self.logger,
                self.controller,
                self.path_root,
                self.lcd,
            )

            # Initialize rotary encoder (pins BCM 5, 6, 23)
            self.encoder = Encoder(
                self.logger,
                self.game_radio_station,
                **self.settings.encoder,
            )

            self.main_loop()
        except Exception:
            self.shutdown()
            raise

    def show_loading_image(self):
        """
        Displays the loading image on the TFT screen.
        """
        try:
            with Image.open(os.path.join(self.path_root, "lib", "loading.png")) as source:
                img = source.convert("RGB").resize((240, 240))
            self.lcd.ShowImage(img)
        except Exception as e:
            self.logger.write(f"[ERROR] Could not load loading image: {e}")

    def show_closed_image(self):
        """
        Displays a closed image on program exit.
        """
        try:
            with Image.open(os.path.join(self.path_root, "lib", "closed.png")) as source:
                img = source.convert("RGB").resize((240, 240))
            self.lcd.ShowImage(img)
        except Exception as e:
            self.logger.write(f"[ERROR] Could not load closed image: {e}")

    def main_loop(self):
        """
        Keep the main program alive until SIGINT, SIGTERM, or a direct request.
        """
        try:
            while not self._shutdown_event.wait(1):
                pass
        except KeyboardInterrupt:
            self._request_shutdown(signal.SIGINT, None)
        finally:
            self.shutdown()

    def _request_shutdown(self, signum, frame):
        self.logger.write(f"[INFO] Shutdown requested by signal {signum}.")
        self._shutdown_event.set()

    def shutdown(self):
        """Stop worker threads and hardware in an order that prevents races."""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self.logger.write("[INFO] Cleaning up...")

        if self.encoder is not None:
            self.encoder.close()
        if self.controller is not None:
            self.controller.stop_playback()
        if self.game_radio_station is not None:
            self.game_radio_station.close()
        if self.bluetooth_service is not None:
            self.bluetooth_service.stop()
        if self.lcd is not None:
            self.show_closed_image()
            try:
                self.lcd.module_exit()
            except Exception as exc:
                self.logger.write(f"[WARN] LCD cleanup failed: {exc}")
        try:
            GPIO.cleanup()
        except Exception as exc:
            self.logger.write(f"[WARN] GPIO cleanup failed: {exc}")

# ----------------------------
# Main program running
# ----------------------------
if __name__ == "__main__":
    Startup()
