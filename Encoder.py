import time
import threading
from gpiozero import RotaryEncoder, Button

from PlayRadio import RadioController
from BluetoothService import BluetoothService
from Logger import Logger
from PIL import Image, ImageDraw, ImageFont
from lib import LCD_1inch28

class Encoder:
    def __init__(self, logger: Logger, game_radio_station, controller: RadioController, bluetooth_service: BluetoothService, lcd: LCD_1inch28):
        self.logger = logger
        self.game_radio_station = game_radio_station
        self.controller = controller
        self.bluetooth_service = bluetooth_service
        self.lcd = lcd

        # RotaryEncoder pins / state
        self.clk_pin = 17
        self.dt_pin = 18
        self.sw_pin = 23
        self.input_timeout = 0.5
        self.inputLock = False
        self.rc_last_rotation = 0
        self.rc_last_btn_press = 0

        self.encoder = RotaryEncoder(a=self.clk_pin, b=self.dt_pin, max_steps=0)
        self.button = Button(self.sw_pin, pull_up=True)

        # Event-Handler → Threads starten
        self.encoder.when_rotated = self._threaded_rotate
        self.button.when_released = self._threaded_button_release

        self.game_radio_station.encoder = self

    # ---------------------------------------------------
    # Event-Wrappers: starten jeweils neuen Thread
    # ---------------------------------------------------
    def _threaded_rotate(self):
        threading.Thread(target=self.rc_rotate, daemon=True).start()

    def _threaded_button_release(self):
        threading.Thread(target=self.rc_btn_release, daemon=True).start()

    # ---------------------------------------------------
    # Logik (läuft in separaten Threads)
    # ---------------------------------------------------
    # RotaryEncoder
    def rc_rotate(self):
        now = time.time()
        if now > (self.rc_last_rotation + self.input_timeout) and not self.inputLock:
            steps = self.encoder.steps
            if steps > 0:
                self.logger.write("[INPUT] KY-040: Rotation > Right")
                self.logger.write("[INFO] Next song is called")
                self.game_radio_station.switch_song("next")
            elif steps < 0:
                self.logger.write("[INPUT] KY-040: Rotation > Left")
                self.logger.write("[INFO] Previous song is called up")
                self.game_radio_station.switch_song("prev")
            self.rc_last_rotation = now
        self.encoder.steps = 0

    def rc_btn_release(self):
        if self.inputLock:
            return

        now = time.time()
        if now > (self.rc_last_btn_press + self.input_timeout):
            self.logger.write("[INPUT] KY-040: Button pressed")
            # Kurzdruck: nächstes Spiel
            self.logger.write("[INFO] Switching to next game...")
            self.game_radio_station.next_game()
            self.rc_last_btn_press = now

    # ---------------------------------------------------
    # Public
    # ---------------------------------------------------

    def lock(self):
        self.inputLock = True

    def unlock(self):
        self.inputLock = False