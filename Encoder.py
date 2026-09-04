"""KY-040 rotary encoder and button input handling."""

from __future__ import annotations

import queue
import threading

from gpiozero import Button, RotaryEncoder

from PlayRadio import RadioController
from BluetoothService import BluetoothService
from Logger import Logger
from lib import LCD_1inch28


class Encoder:
    """Process each encoder detent and button release exactly once."""

    DEFAULT_CLK_PIN = 5
    DEFAULT_DT_PIN = 6
    DEFAULT_SW_PIN = 23

    def __init__(
        self,
        logger: Logger,
        game_radio_station,
        controller: RadioController,
        bluetooth_service: BluetoothService,
        lcd: LCD_1inch28,
        clk_pin: int = DEFAULT_CLK_PIN,
        dt_pin: int = DEFAULT_DT_PIN,
        sw_pin: int = DEFAULT_SW_PIN,
        rotary_bounce_time: float = 0.003,
        button_bounce_time: float = 0.05,
    ):
        self.logger = logger
        self.game_radio_station = game_radio_station
        self.controller = controller
        self.bluetooth_service = bluetooth_service
        self.lcd = lcd

        self.clk_pin = clk_pin
        self.dt_pin = dt_pin
        self.sw_pin = sw_pin

        self._actions = queue.Queue()
        self._state_lock = threading.Lock()
        self._closed = False

        # GPIO Zero decodes the quadrature signal.  The callbacks only enqueue
        # an action; all radio/UI work is performed by one worker thread.
        self.encoder = RotaryEncoder(
            a=self.clk_pin,
            b=self.dt_pin,
            max_steps=0,
            bounce_time=rotary_bounce_time,
        )
        self.button = Button(
            self.sw_pin,
            pull_up=True,
            bounce_time=button_bounce_time,
        )

        self.encoder.when_rotated_clockwise = self._on_rotated_clockwise
        self.encoder.when_rotated_counter_clockwise = self._on_rotated_counter_clockwise
        self.button.when_released = self._on_button_released

        self.game_radio_station.encoder = self

        self._worker = threading.Thread(
            target=self._process_actions,
            name="radio-input-worker",
            daemon=True,
        )
        self._worker.start()

        self.logger.write(
            "[INFO] KY-040 initialized "
            f"(CLK=GPIO{self.clk_pin}, DT=GPIO{self.dt_pin}, SW=GPIO{self.sw_pin}, "
            f"rotary_bounce={rotary_bounce_time:.3f}s, "
            f"button_bounce={button_bounce_time:.3f}s)"
        )

    # ---------------------------------------------------
    # GPIO callbacks: enqueue only
    # ---------------------------------------------------
    def _on_rotated_clockwise(self):
        self._enqueue(("rotate", 1))

    def _on_rotated_counter_clockwise(self):
        self._enqueue(("rotate", -1))

    def _on_button_released(self):
        self._enqueue(("button", None))

    def _enqueue(self, action):
        with self._state_lock:
            if self._closed:
                return
        self._actions.put(action)

    # ---------------------------------------------------
    # Single consumer for all input actions
    # ---------------------------------------------------
    def _process_actions(self):
        while True:
            action = self._actions.get()
            try:
                if action is None:
                    return

                action_type, payload = action
                if action_type == "rotate":
                    self.rc_rotate(payload)
                elif action_type == "button":
                    self.rc_btn_release()
            except Exception as exc:
                self.logger.write(f"[ERROR] Input action {action!r} failed: {exc}")
            finally:
                self._actions.task_done()

    def rc_rotate(self, direction: int):
        """Switch exactly one song for each confirmed encoder detent."""
        if direction > 0:
            self.logger.write("[INPUT] KY-040: Rotation > Right")
            self.logger.write("[INFO] Next song is called")
            self.game_radio_station.switch_song("next")
        else:
            self.logger.write("[INPUT] KY-040: Rotation > Left")
            self.logger.write("[INFO] Previous song is called up")
            self.game_radio_station.switch_song("prev")

    def rc_btn_release(self):
        """Switch to the next game for each debounced button release."""
        self.logger.write("[INPUT] KY-040: Button pressed")
        self.logger.write("[INFO] Switching to next game...")
        self.game_radio_station.next_game()

    # ---------------------------------------------------
    # Public lifecycle API
    # ---------------------------------------------------
    def close(self):
        with self._state_lock:
            if self._closed:
                return
            self._closed = True

        self.encoder.when_rotated_clockwise = None
        self.encoder.when_rotated_counter_clockwise = None
        self.button.when_released = None
        self._actions.put(None)

        if self._worker.is_alive():
            self._worker.join(timeout=2)

        self.encoder.close()
        self.button.close()
