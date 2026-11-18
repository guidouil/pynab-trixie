import unittest
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, patch

from nabd.button_gpio import ButtonGPIO
from nabd.nabio import NabIO


class FakeTimer:
    def __init__(self, delay, callback, args=()):
        self.delay = delay
        self.callback = callback
        self.args = args
        self.cancelled = False
        self.started = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if self.started and not self.cancelled:
            self.callback(*self.args)


class ButtonGPIOTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.loop = Mock()
        self.loop.is_closed.return_value = False
        self.loop.call_soon_threadsafe.side_effect = lambda fn, *args: fn(
            *args
        )
        self.enterContext(patch("nabd.button_gpio.Timer", FakeTimer))

    def make_button(self, model=NabIO.MODEL_2019_TAGTAG):
        button = ButtonGPIO(model)
        button.callback = (self.loop, self.capture)
        self.addCleanup(button.close)
        return button

    def capture(self, event, _timestamp):
        self.events.append(event)

    def test_click_gestures(self):
        for count, gesture in (
            (1, "click"),
            (2, "double_click"),
            (3, "triple_click"),
        ):
            with self.subTest(gesture=gesture):
                self.events.clear()
                button = self.make_button()
                for _ in range(count):
                    button._button_event(False)
                    button._button_event(True)
                if count < 3:
                    self.assertEqual(button.button_timer.delay, 0.15)
                    button.button_timer.fire()
                self.assertEqual(
                    self.events, ["down", "up"] * count + [gesture]
                )

    def test_hold_starts_before_release(self):
        button = self.make_button()
        button._button_event(False)
        self.assertEqual(button.button_timer.delay, 2.0)
        button.button_timer.fire()
        button._button_event(True)
        self.assertEqual(self.events, ["down", "hold", "up"])

    def test_click_and_hold_starts_on_second_press(self):
        button = self.make_button()
        button._button_event(False)
        button._button_event(True)
        button._button_event(False)
        self.assertEqual(button.button_timer.delay, 2.0)
        button.button_timer.fire()
        button._button_event(True)
        self.assertEqual(
            self.events, ["down", "up", "down", "click_and_hold", "up"]
        )

    def test_duplicate_level_keeps_pending_gesture(self):
        button = self.make_button()
        button._button_event(False)
        hold = button.button_timer
        button._button_event(False)
        self.assertIs(button.button_timer, hold)
        hold.fire()
        self.assertEqual(self.events, ["down", "hold"])

    def test_close_cancels_unfinished_gesture(self):
        button = self.make_button()
        button._button_event(False)
        hold = button.button_timer
        button.close()
        self.assertTrue(hold.cancelled)
        hold.callback(*hold.args)  # A timer can race with cancellation.
        button._button_event(True)
        self.assertEqual(self.events, ["down"])

    def test_cancelled_timer_cannot_replace_new_gesture(self):
        button = self.make_button()
        button._button_event(False)
        hold = button.button_timer
        button._button_event(True)
        click = button.button_timer
        hold.callback(*hold.args)  # Simulate a callback that already woke up.
        self.assertIs(button.button_timer, click)
        click.fire()
        self.assertEqual(self.events, ["down", "up", "click"])

    def test_close_releases_reader_request(self):
        button = self.make_button()
        request = MagicMock()
        reading = Event()

        def wait_for_event(timeout):
            reading.set()
            button._stopping.wait(timeout)
            return False

        request.wait_edge_events.side_effect = wait_for_event
        with patch.object(button, "_event_request", return_value=(request, 1)):
            button.on_event(self.loop, self.capture)
        self.assertTrue(reading.wait(2))
        button.close()
        request.__exit__.assert_called_once_with(None, None, None)

    def test_zero_w_requests_both_gpio_edges_without_internal_pulls(self):
        button = self.make_button()
        gpiod = SimpleNamespace(LineSettings=Mock(), request_lines=Mock())
        line_types = SimpleNamespace(
            Direction=SimpleNamespace(INPUT=object()),
            Bias=SimpleNamespace(DISABLED=object()),
            Edge=SimpleNamespace(BOTH=object()),
            Value=SimpleNamespace(ACTIVE=object()),
        )
        with patch(
            "nabd.button_gpio.hardware.device_model",
            return_value="Raspberry Pi Zero W Rev 1.1",
        ):
            with patch.dict("sys.modules", {"gpiod": None}):
                self.assertIsNone(button._event_request())
            with (
                patch.dict(
                    "sys.modules", {"gpiod": gpiod, "gpiod.line": line_types}
                ),
                patch.dict("os.environ", {"RPI_LGPIO_CHIP": "4"}),
            ):
                self.assertEqual(
                    button._event_request(),
                    (
                        gpiod.request_lines.return_value,
                        line_types.Value.ACTIVE,
                    ),
                )
                gpiod.request_lines.side_effect = OSError("busy GPIO")
                with self.assertRaisesRegex(OSError, "busy GPIO"):
                    button._event_request()
        gpiod.LineSettings.assert_called_with(
            direction=line_types.Direction.INPUT,
            bias=line_types.Bias.DISABLED,
            edge_detection=line_types.Edge.BOTH,
        )
        gpiod.request_lines.assert_called_with(
            "/dev/gpiochip4",
            consumer="nabd-button",
            config={17: gpiod.LineSettings.return_value},
        )

    def test_monitor_drains_edges_and_uses_stable_current_level(self):
        for model, channel in (
            (NabIO.MODEL_2018, 2),
            (NabIO.MODEL_2019_TAGTAG, 17),
        ):
            with self.subTest(channel=channel):
                self.events.clear()
                button = self.make_button(model)
                request = MagicMock()
                request.read_edge_events.return_value = [object()]
                active = object()
                request.get_value.side_effect = [object(), active]

                def stop_monitor():
                    button._stopping.set()
                    return False

                waits = iter((True, True))
                request.wait_edge_events.side_effect = (
                    lambda *args, **kwargs: next(waits, False)
                    or stop_monitor()
                )

                button._monitor(request, active, self.loop)
                self.assertEqual(self.events, ["down", "up"])
                reads = [
                    command
                    for command in request.method_calls
                    if command[0] in {"read_edge_events", "get_value"}
                ]
                self.assertEqual(
                    reads,
                    [call.read_edge_events(), call.get_value(channel)] * 2,
                )
