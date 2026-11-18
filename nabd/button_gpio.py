import logging
import os
import time
from threading import Event, Lock, Thread, Timer

from nabcommon import hardware

from .button import Button
from .nabio import NabIO


class ButtonGPIO(Button):  # pragma: no cover
    BUTTON_CHANNEL_2018 = 2
    BUTTON_CHANNEL_2019 = 17

    HOLD_TIMEOUT = 2.0
    CLICK_AND_HOLD_TIMEOUT = 2.0
    DOUBLE_CLICK_TIMEOUT = 0.15
    TRIPLE_CLICK_TIMEOUT = 0.15

    def __init__(self, hw_model):
        self.callback = None
        self.button_sequence = 0
        self.button_timer = None
        self.button_sequence_lock = Lock()
        self.button_state = "up"
        self._gpio = None
        self._reader = None
        self._stopping = Event()
        if hw_model == NabIO.MODEL_2018:
            self.button_channel = ButtonGPIO.BUTTON_CHANNEL_2018
        else:
            self.button_channel = ButtonGPIO.BUTTON_CHANNEL_2019

    def _event_request(self):
        if not hardware.device_model().startswith("Raspberry Pi Zero W Rev "):
            return None
        try:
            from gpiod import LineSettings, request_lines
            from gpiod.line import Bias, Direction, Edge, Value
        except ImportError:
            return None
        chip = int(os.environ.get("RPI_LGPIO_CHIP", "0"))
        request = request_lines(
            f"/dev/gpiochip{chip}",
            consumer="nabd-button",
            config={
                self.button_channel: LineSettings(
                    direction=Direction.INPUT,
                    edge_detection=Edge.BOTH,
                    bias=Bias.DISABLED,
                )
            },
        )
        return request, Value.ACTIVE

    def _monitor(self, request, active_value, loop):
        try:
            with request:
                while not self._stopping.is_set():
                    if (
                        request.wait_edge_events(1)
                        and request.read_edge_events()
                    ):
                        self._button_event(
                            request.get_value(self.button_channel)
                            == active_value
                        )
        except OSError:
            logging.exception("Button GPIO event reader failed")
            loop.call_soon_threadsafe(loop.stop)

    def _gpio_event(self, channel):
        with self.button_sequence_lock:
            if self.callback is None:
                return
            is_up = self._gpio.input(channel) == self._gpio.HIGH
        self._button_event(is_up)

    def on_event(self, loop, callback):
        with self.button_sequence_lock:
            self.callback = (loop, callback)
        if self._reader is not None or self._gpio is not None:
            return
        event_request = self._event_request()
        if event_request is not None:
            # Keep gesture timing independent of the main asyncio loop.
            self._stopping.clear()
            request, active_value = event_request
            self._reader = Thread(
                target=self._monitor,
                args=(request, active_value, loop),
                daemon=True,
            )
            try:
                self._reader.start()
            except RuntimeError:
                self._reader = None
                request.release()
                raise
            return

        import RPi.GPIO as GPIO  # type: ignore

        GPIO.setwarnings(True)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.button_channel, GPIO.IN)
        self._gpio = GPIO
        try:
            GPIO.add_event_detect(
                self.button_channel, GPIO.BOTH, callback=self._gpio_event
            )
        except RuntimeError:
            GPIO.cleanup(self.button_channel)
            self._gpio = None
            raise

    def close(self):
        with self.button_sequence_lock:
            self.callback = None
            if self.button_timer is not None:
                self.button_timer.cancel()
                self.button_timer = None
        if self._reader is not None:
            self._stopping.set()
            self._reader.join()
            self._reader = None
        if self._gpio is not None:
            self._gpio.cleanup(self.button_channel)
            self._gpio = None

    #
    # (0) -- down -> (1) -- timer -> hold
    #                 |
    #                 -- up -> (2) -- timer -> click + goto state 0
    #                           |
    #  _________________________|
    #  |
    #  -- down -> (3) -- timer -> click_and_hold
    #              |
    #              -- up -> (4) -- timer -> double click
    #                        |
    #                        -- down -> (5) -- timer -> click_and_hold
    #
    def _button_event(self, is_up):
        now = time.time()
        with self.button_sequence_lock:
            state = "up" if is_up else "down"
            if self.callback is None or state == self.button_state:
                return
            if self.button_timer is not None:
                self.button_timer.cancel()
                self.button_timer = None
            loop, callback = self.callback
            self.button_state = state
            loop.call_soon_threadsafe(lambda: callback(state, now))
            if is_up:
                if self.button_sequence == 5:
                    self.button_sequence = 0
                    loop.call_soon_threadsafe(
                        lambda: callback("triple_click", now)
                    )
                elif self.button_sequence == 3:
                    self.button_sequence = 4
                    self._start_timer(
                        self.TRIPLE_CLICK_TIMEOUT, "double_click"
                    )
                elif self.button_sequence == 1:
                    self.button_sequence = 2
                    self._start_timer(self.DOUBLE_CLICK_TIMEOUT, "click")
            else:
                if self.button_sequence == 0:
                    self.button_sequence = 1
                    self._start_timer(self.HOLD_TIMEOUT, "hold")
                elif self.button_sequence == 2:
                    self.button_sequence = 3
                    self._start_timer(
                        self.CLICK_AND_HOLD_TIMEOUT, "click_and_hold"
                    )
                elif self.button_sequence == 4:
                    self.button_sequence = 5
                    self._start_timer(
                        self.TRIPLE_CLICK_TIMEOUT, "click_and_hold"
                    )

    def _start_timer(self, timeout, event):
        timer = Timer(timeout, lambda: self._timer_event_cb(timer, event))
        self.button_timer = timer
        timer.start()

    def _timer_event_cb(self, timer, event):
        now = time.time()
        with self.button_sequence_lock:
            if self.callback is None or self.button_timer is not timer:
                return
            loop, callback = self.callback
            loop.call_soon_threadsafe(lambda: callback(event, now))
            self.button_timer = None
            self.button_sequence = 0
