import os, time
import RPi.GPIO as GPIO

from BluetoothService import BluetoothService
from GameRadioStation import GameRadioStation
from Logger import Logger
from PIL import Image
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

        # Initialize logger
        self.logger = Logger(self.path_root)

        # Initialize the TFT display
        self.lcd = LCD_1inch28.LCD_1inch28()
        self.lcd.Init()
        self.lcd.clear()
        self.show_loading_image()

        # Initialize bluetooth connection
        self.bluetooth_service = BluetoothService(self.logger, self.path_root, ['mycar'], scan_interval=5, auto_start=True)

        # Initialize Radio Controller
        self.controller = RadioController(self.logger)

        # Initialize game radio station
        self.game_radio_station = GameRadioStation(self.logger, self.controller, self.path_root, self.lcd)

        # Initialize rotary encoder (pins BCM 17, 18, 23)
        self.encoder = Encoder(self.logger, self.game_radio_station, self.controller, self.bluetooth_service, self.lcd)

        # Start the main loop to keep program alive
        self.main_loop()

    def show_loading_image(self):
        """
        Displays the loading image on the TFT screen.
        """
        try:
            img = Image.open(os.path.join(self.path_root, "lib/loading.png")).resize((240, 240))
            self.lcd.ShowImage(img)
        except Exception as e:
            self.logger.write(f"[ERROR] Could not load loading image: {e}")

    def show_closed_image(self):
        """
        Displays a closed image on program exit.
        """
        try:
            img = Image.open(os.path.join(self.path_root, "lib/closed.png")).resize((240, 240))
            self.lcd.ShowImage(img)
        except Exception as e:
            self.logger.write(f"[ERROR] Could not load closed image: {e}")

    def main_loop(self):
        """
        Keeps the main program alive. cleans up Bluetooth, GPIO and shows closed image.
        """
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt as e:
            self.logger.write(f"[INFO] Program interrupted. {e} Cleaning up...")
            self.show_closed_image()
            self.bluetooth_service.stop()
            GPIO.cleanup()

# ----------------------------
# Main program running
# ----------------------------
Startup()