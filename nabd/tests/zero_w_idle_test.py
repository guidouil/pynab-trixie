import unittest
from unittest.mock import AsyncMock, Mock, patch

from nabd.leds import Led
from nabd.nabd import Nabd


class TestZeroWIdleLED(unittest.IsolatedAsyncioTestCase):
    async def test_idle_and_network_alerts(self):
        for address, internet, expected in (
            ("192.0.2.1", True, (0, 0, 0)),
            (None, False, (255, 0, 0)),
            ("192.0.2.1", False, (255, 165, 0)),
        ):
            with self.subTest(address=address, internet=internet):
                rabbit = object.__new__(Nabd)
                rabbit.ears = {"left": 0, "right": 10}
                rabbit.nabio = Mock()
                rabbit.nabio.move_ears_with_leds = AsyncMock()
                with (
                    patch(
                        "nabd.nabd.network.ip_address", return_value=address
                    ),
                    patch(
                        "nabd.nabd.network.internet_connection",
                        return_value=internet,
                    ),
                    patch("nabd.nabd.logging"),
                ):
                    await rabbit._do_transition_to_idle()
                rabbit.nabio.move_ears_with_leds.assert_awaited_once_with(
                    (0, 255, 255), 0, 10
                )
                rabbit.nabio.pulse.assert_called_with(Led.BOTTOM, expected)


if __name__ == "__main__":
    unittest.main()
