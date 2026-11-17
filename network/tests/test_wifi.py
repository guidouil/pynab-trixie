import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from network import comitup_start, wifi_boot


class BootButtonTests(unittest.TestCase):
    def setUp(self):
        self.gpio = mock.Mock(BCM=11, IN=1, LOW=0)

    def test_unpressed_button_does_not_delay_boot(self):
        self.gpio.input.return_value = 1
        with mock.patch.object(wifi_boot.time, "sleep") as sleep:
            self.assertFalse(wifi_boot.button_held(self.gpio))
        sleep.assert_not_called()
        self.gpio.cleanup.assert_called_once_with(17)

    def test_release_before_deadline_is_not_setup_request(self):
        self.gpio.input.side_effect = [0, 0, 1]
        with (
            mock.patch.object(
                wifi_boot.time, "monotonic", side_effect=[0, 0.1, 1]
            ),
            mock.patch.object(wifi_boot.time, "sleep"),
        ):
            self.assertFalse(wifi_boot.button_held(self.gpio))
        self.gpio.cleanup.assert_called_once_with(17)

    def test_button_must_stay_pressed_for_two_seconds(self):
        self.gpio.input.return_value = 0
        with (
            mock.patch.object(
                wifi_boot.time, "monotonic", side_effect=[0, 0.1, 2]
            ),
            mock.patch.object(wifi_boot.time, "sleep"),
        ):
            self.assertTrue(wifi_boot.button_held(self.gpio))
        self.gpio.cleanup.assert_called_once_with(17)

    def test_read_error_still_releases_gpio(self):
        self.gpio.input.side_effect = RuntimeError("GPIO read failed")
        with self.assertRaises(RuntimeError):
            wifi_boot.button_held(self.gpio)
        self.gpio.cleanup.assert_called_once_with(17)

    def test_setup_request_is_private_even_if_leds_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / "request"
            with (
                mock.patch.object(wifi_boot, "SETUP_REQUEST", request),
                mock.patch.object(wifi_boot, "button_held", return_value=True),
                mock.patch.object(
                    wifi_boot,
                    "show_setup_leds",
                    side_effect=RuntimeError("LED unavailable"),
                ),
                mock.patch.dict(
                    "sys.modules",
                    {
                        "RPi": SimpleNamespace(GPIO=self.gpio),
                        "RPi.GPIO": self.gpio,
                    },
                ),
                self.assertLogs(level="WARNING"),
            ):
                wifi_boot.main()
            self.assertTrue(request.exists())
            self.assertEqual(request.stat().st_mode & 0o777, 0o600)


class ComitupStartupTests(unittest.TestCase):
    def test_proxy_starts_only_after_upstream_connection(self):
        client = mock.Mock()
        module = SimpleNamespace(CiuClient=mock.Mock(return_value=client))
        with mock.patch.dict("sys.modules", {"comitup.client": module}):
            for state in ("HOTSPOT", "CONNECTING"):
                client.ciu_state.return_value = (state, 1)
                self.assertFalse(comitup_start.connected())
            client.ciu_state.return_value = ("CONNECTED", 1)
            self.assertTrue(comitup_start.connected())

    def test_forced_start_offers_hotspot_and_keeps_saved_connections(self):
        pending = []
        saved = ["Home", "Workshop"]
        states = SimpleNamespace(
            startup=False,
            saved=saved,
            state=None,
            mdns=mock.Mock(),
            dns_names=["Nabaztag-123.local"],
        )

        def initialize(hosts, callbacks, password):
            states.startup = True
            pending.append(
                lambda: setattr(
                    states,
                    "state",
                    "CONNECTING" if states.startup else "HOTSPOT",
                )
            )

        states.init_states = initialize
        comitup_start.prefer_hotspot(states)
        states.init_states(["Nabaztag-123.local"], [], "")
        pending.pop()()
        self.assertEqual(states.state, "HOTSPOT")
        self.assertEqual(saved, ["Home", "Workshop"])
        states.mdns.add_hosts.assert_called_once_with(["Nabaztag-123.local"])

    def test_request_is_consumed_once_and_normal_start_uses_unmodified_comitup(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / "request"
            states = SimpleNamespace(
                init_states=mock.Mock(),
                startup=False,
                mdns=mock.Mock(),
                dns_names=[],
            )
            original_initialize = states.init_states
            comitup = SimpleNamespace(main=mock.Mock())
            package = SimpleNamespace(comitup=comitup, states=states)
            with (
                mock.patch.object(comitup_start, "SETUP_REQUEST", request),
                mock.patch.object(
                    comitup_start, "version", return_value="1.43"
                ),
                mock.patch.dict("sys.modules", {"comitup": package}),
            ):
                comitup_start.main()
                self.assertIs(states.init_states, original_initialize)
                request.touch()
                comitup_start.main()
                self.assertFalse(request.exists())
            self.assertEqual(comitup.main.call_count, 2)

    def test_unknown_version_or_changed_api_keeps_normal_network_startup(self):
        states = SimpleNamespace(
            init_states=mock.Mock(),
            startup=False,
            mdns=mock.Mock(),
            dns_names=[],
        )
        self.assertTrue(
            comitup_start.supports_hotspot_override(states, "1.43")
        )
        self.assertTrue(
            comitup_start.supports_hotspot_override(states, "1.47.1")
        )
        self.assertFalse(
            comitup_start.supports_hotspot_override(states, "1.48")
        )
        self.assertFalse(
            comitup_start.supports_hotspot_override(states, "unknown")
        )
        self.assertFalse(
            comitup_start.supports_hotspot_override(SimpleNamespace(), "1.43")
        )


if __name__ == "__main__":
    unittest.main()
