import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from nabd.leds import Led
from nabd.nabd import Nabd, State
from nabd.nlu import NLU


class TestNativeASRLifecycle(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rabbit = rabbit = object.__new__(Nabd)
        rabbit.state = State.IDLE
        rabbit.idle_cv = asyncio.Condition()
        rabbit._asr_task = None
        rabbit._asr_stop = asyncio.Event()
        rabbit.interactive_service_writer = None
        rabbit.interactive_service_events = []
        rabbit.playing_cancelable = False
        rabbit.broadcast_state = Mock()
        rabbit.broadcast_event = Mock()
        rabbit.asr = Mock()
        rabbit.asr.get_decoded_string = AsyncMock(
            return_value="quelle heure est il"
        )
        rabbit.nlu = SimpleNamespace(
            interpret=AsyncMock(return_value={"intent": "nabclockd/clock"})
        )
        self.capturing = False
        self.started = asyncio.Event()
        rabbit.nabio = SimpleNamespace(
            sound=SimpleNamespace(
                stop_recording=AsyncMock(side_effect=self.stop_capture)
            ),
            rfid=Mock(),
            start_acquisition=AsyncMock(side_effect=self.start_capture),
            end_acquisition=AsyncMock(side_effect=self.stop_capture),
            asr_failed=AsyncMock(),
        )
        rabbit.transition_to = AsyncMock(side_effect=self.transition)

    async def asyncTearDown(self):
        task = self.rabbit._asr_task
        if task is not None:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def start_capture(self, callback):
        self.capturing = True
        self.started.set()

    async def stop_capture(self):
        self.capturing = False

    async def transition(self, state):
        self.rabbit.state = state

    def hold(self):
        self.rabbit.button_callback("hold", 1)
        return self.rabbit._asr_task

    def assert_released(self):
        self.assertFalse(self.capturing)
        self.assertEqual(self.rabbit.state, State.IDLE)
        self.assertIsNone(self.rabbit._asr_task)
        self.rabbit.nabio.rfid.enable_polling.assert_called_once()

    async def test_release_during_listen_sound_and_concurrent_stops(self):
        beep_started, finish_beep = asyncio.Event(), asyncio.Event()

        async def delayed_start(callback):
            beep_started.set()
            await finish_beep.wait()
            await self.start_capture(callback)

        self.rabbit.nabio.start_acquisition.side_effect = delayed_start
        task = self.hold()
        await beep_started.wait()
        self.rabbit.button_callback("up", 2)
        stops = [asyncio.create_task(self.rabbit.stop_asr()) for _ in range(2)]
        await asyncio.sleep(0)
        self.rabbit.nabio.end_acquisition.assert_not_awaited()
        finish_beep.set()
        await asyncio.wait_for(asyncio.gather(task, *stops), 1)
        self.assert_released()
        self.rabbit.asr.reset.assert_called_once()
        self.rabbit.nabio.end_acquisition.assert_awaited_once()
        self.rabbit.asr.get_decoded_string.assert_awaited_once_with(True)
        self.rabbit.broadcast_event.assert_called_once()
        event, packet = self.rabbit.broadcast_event.call_args.args
        self.assertEqual(event, "asr/nabclockd")
        self.assertEqual(packet["nlu"], {"intent": "nabclockd/clock"})

    async def test_release_before_start_task_runs(self):
        task = self.hold()
        self.rabbit.button_callback("up", 2)
        await asyncio.wait_for(task, 1)
        self.assert_released()

    async def test_native_commands_route_to_their_services(self):
        commands = (
            ("quelle heure est il", "nabclockd/clock"),
            ("dodo", "nabclockd/sleep"),
            ("météo", "nabweatherd/forecast"),
            ("qualité de l' air", "nabairqualityd/forecast"),
            ("tai chi", "nabtaichid/taichi"),
            ("t' en penses quoi nabaztag", "nab8balld/8ball"),
            ("fais moi rire", "nabsurprised/surprise"),
            ("carotte", "nabsurprised/carrot"),
            ("que sais tu faire", "nabsurprised/autopromo"),
            ("anniversaire", "nabsurprised/birthday"),
        )
        for phrase, intent in commands:
            with self.subTest(phrase=phrase):
                self.assertIsNone(self.rabbit._asr_task)
                self.setUp()
                self.rabbit.asr.get_decoded_string.return_value = phrase
                self.rabbit.nlu = NLU("fr_FR")
                task = self.hold()
                self.rabbit.button_callback("up", 2)
                await asyncio.wait_for(task, 1)
                self.assert_released()
                self.rabbit.broadcast_event.assert_called_once()
                event, packet = self.rabbit.broadcast_event.call_args.args
                self.assertEqual(event, f"asr/{intent.split('/')[0]}")
                self.assertEqual(packet["type"], "asr_event")
                self.assertEqual(packet["nlu"], {"intent": intent})

    async def test_lost_release_times_out_and_next_capture_starts(self):
        self.rabbit.ASR_CAPTURE_SECONDS = 0.01
        await asyncio.wait_for(self.hold(), 1)
        self.assert_released()
        self.rabbit.nabio.rfid.enable_polling.reset_mock()
        task = self.hold()
        self.rabbit.button_callback("up", 3)
        await asyncio.wait_for(task, 1)
        self.assert_released()
        self.assertEqual(self.rabbit.asr.reset.call_count, 2)
        self.assertEqual(self.rabbit.nabio.end_acquisition.await_count, 2)

    async def test_mac_reservation_wins_before_native_task_starts(self):
        task = self.hold()
        self.rabbit.state = State.INTERACTIVE
        self.rabbit.interactive_service_writer = object()
        await asyncio.wait_for(task, 1)
        self.assertEqual(self.rabbit.state, State.INTERACTIVE)
        self.assertIsNone(self.rabbit._asr_task)
        self.rabbit.nabio.start_acquisition.assert_not_awaited()
        self.rabbit.nabio.rfid.disable_polling.assert_not_called()
        self.rabbit.transition_to.assert_not_awaited()

    async def test_short_click_and_interactive_hold_keep_button_events(self):
        self.rabbit.button_callback("click", 1)
        self.assertIsNone(self.rabbit._asr_task)
        self.rabbit.broadcast_event.assert_called_once_with(
            "button", {"type": "button_event", "event": "click", "time": 1}
        )
        self.rabbit.broadcast_event.reset_mock()
        self.rabbit.state = State.INTERACTIVE
        self.rabbit.button_callback("hold", 2)
        self.assertIsNone(self.rabbit._asr_task)
        self.rabbit.broadcast_event.assert_called_once_with(
            "button", {"type": "button_event", "event": "hold", "time": 2}
        )

    async def test_acquisition_failure_stops_microphone_before_failure_sound(
        self,
    ):
        async def broken_start(callback):
            await self.start_capture(callback)
            raise OSError("capture failed")

        async def failure_sound():
            self.assertFalse(self.capturing)
            self.assertEqual(self.rabbit.state, State.RECORDING)

        self.rabbit.nabio.start_acquisition.side_effect = broken_start
        self.rabbit.nabio.asr_failed.side_effect = failure_sound
        with patch("nabd.nabd.logging"):
            await asyncio.wait_for(self.hold(), 1)
        self.assert_released()
        self.rabbit.nabio.sound.stop_recording.assert_awaited_once()
        self.rabbit.nabio.asr_failed.assert_awaited_once()
        self.rabbit.broadcast_event.assert_not_called()

    async def test_recognizer_failure_releases_session_and_can_retry(self):
        self.rabbit.asr.get_decoded_string.side_effect = RuntimeError(
            "decode failed"
        )
        with patch("nabd.nabd.logging"):
            task = self.hold()
            self.rabbit.button_callback("up", 2)
            await asyncio.wait_for(task, 1)
        self.assert_released()
        self.rabbit.nabio.asr_failed.assert_awaited_once()
        self.rabbit.broadcast_event.assert_not_called()
        self.rabbit.nabio.rfid.enable_polling.reset_mock()
        self.rabbit.asr.get_decoded_string.side_effect = None
        task = self.hold()
        self.rabbit.button_callback("up", 3)
        await asyncio.wait_for(task, 1)
        self.assert_released()
        self.rabbit.broadcast_event.assert_called_once()

    async def test_unknown_phrase_and_broken_failure_sound_still_release(self):
        self.rabbit.nlu.interpret.return_value = None
        self.rabbit.nabio.asr_failed.side_effect = OSError("speaker failed")
        with patch("nabd.nabd.logging"):
            task = self.hold()
            self.rabbit.button_callback("up", 2)
            await asyncio.wait_for(task, 1)
        self.assert_released()
        self.rabbit.broadcast_event.assert_not_called()

    async def test_cancel_during_capture_releases_without_dispatch(self):
        task = self.hold()
        await self.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assert_released()
        self.rabbit.nabio.sound.stop_recording.assert_awaited_once()
        self.rabbit.broadcast_event.assert_not_called()
        self.rabbit.nabio.asr_failed.assert_not_awaited()

    async def test_cancel_during_listen_sound_cannot_open_late_microphone(
        self,
    ):
        beep_started, finish_beep = asyncio.Event(), asyncio.Event()

        async def delayed_start(callback):
            beep_started.set()
            await finish_beep.wait()
            await self.start_capture(callback)

        self.rabbit.nabio.start_acquisition.side_effect = delayed_start
        task = self.hold()
        await beep_started.wait()
        task.cancel()
        await asyncio.sleep(0)
        self.rabbit.nabio.sound.stop_recording.assert_not_awaited()
        finish_beep.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assert_released()
        self.rabbit.nabio.sound.stop_recording.assert_awaited_once()
        self.rabbit.broadcast_event.assert_not_called()

    async def test_transcription_keeps_reservation_and_event_loop_responsive(
        self,
    ):
        decoding, finish_decode = asyncio.Event(), asyncio.Event()

        async def decode(sync):
            decoding.set()
            await finish_decode.wait()
            return "quelle heure est il"

        self.rabbit.asr.get_decoded_string.side_effect = decode
        task = self.hold()
        self.rabbit.button_callback("up", 2)
        await asyncio.wait_for(decoding.wait(), 1)
        self.assertFalse(self.capturing)
        self.assertEqual(self.rabbit.state, State.RECORDING)
        self.rabbit.transition_to.assert_not_awaited()
        await asyncio.sleep(0)
        finish_decode.set()
        await asyncio.wait_for(task, 1)
        self.assert_released()

    async def test_success_without_rfid_reader(self):
        self.rabbit.nabio.rfid = None
        task = self.hold()
        self.rabbit.button_callback("up", 2)
        await asyncio.wait_for(task, 1)
        self.assertFalse(self.capturing)
        self.assertEqual(self.rabbit.state, State.IDLE)
        self.rabbit.broadcast_event.assert_called_once()

    async def test_warmup_waits_until_server_is_listening(self):
        server = asyncio.get_running_loop().create_future()
        self.rabbit.asr.start = AsyncMock()
        with patch("nabd.nabd.logging") as logging:
            task = asyncio.create_task(self.rabbit._warmup_asr(server))
            await asyncio.sleep(0)
            self.rabbit.asr.start.assert_not_awaited()
            logging.info.assert_not_called()
            server.set_result(object())
            await task
        logging.info.assert_called_once_with("Native French voice ready")
        self.rabbit.asr.start.assert_awaited_once()

    async def test_warmup_failure_is_logged_without_failing_daemon(self):
        server = asyncio.get_running_loop().create_future()
        server.set_result(object())
        self.rabbit.asr.start = AsyncMock(side_effect=OSError("worker failed"))
        with patch("nabd.nabd.logging") as logging:
            await self.rabbit._warmup_asr(server)
        logging.warning.assert_called_once()
        self.assertEqual(self.rabbit.state, State.IDLE)

    async def test_cancel_warmup_does_not_cancel_server_startup(self):
        server = asyncio.get_running_loop().create_future()
        self.rabbit.asr.start = AsyncMock()
        task = asyncio.create_task(self.rabbit._warmup_asr(server))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(server.cancelled())
        server.set_result(object())
        self.rabbit.asr.start.assert_not_awaited()


class TestNativeASRReload(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.nabio = Mock()
        self.nabio.has_sound_input.return_value = True
        config = SimpleNamespace(locale="fr_FR")
        i18n = SimpleNamespace(
            Config=SimpleNamespace(
                load_once=Mock(return_value=config),
                load_async=AsyncMock(return_value=config),
            )
        )
        self.asr_type = Mock(side_effect=ImportError("French model missing"))
        self.asr_type.get_locale.return_value = "fr_FR"
        self.nlu_type = Mock()
        self.nlu_type.get_locale.return_value = "fr_FR"
        modules = {
            "nabd.i18n": i18n,
            "nabd.asr": SimpleNamespace(ASR=self.asr_type),
            "nabd.nlu": SimpleNamespace(NLU=self.nlu_type),
        }
        for patcher in (
            patch.dict("sys.modules", modules),
            patch("nabd.i18n", i18n, create=True),
            patch("nabd.nabd.settings.configure"),
            patch("nabd.nabd.logging"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_reload_recovers_model_missing_at_boot_with_same_locale(
        self,
    ):
        rabbit = Nabd(self.nabio)
        self.assertIsNone(rabbit.asr)
        self.assertIsNone(rabbit.nlu)
        self.assertEqual(rabbit._asr_locale, "fr_FR")
        self.assertFalse(hasattr(rabbit, "_nlu_locale"))
        self.asr_type.side_effect = None
        await rabbit.reload_config()
        self.assertIs(rabbit.asr, self.asr_type.return_value)
        self.assertIs(rabbit.nlu, self.nlu_type.return_value)
        self.assertEqual(rabbit._nlu_locale, "fr_FR")
        await rabbit.reload_config()
        self.assertEqual(self.asr_type.call_count, 2)
        self.nlu_type.assert_called_once_with("fr_FR")

    async def test_reload_keeps_voice_disabled_while_model_is_missing(self):
        rabbit = Nabd(self.nabio)
        await rabbit.reload_config()
        self.assertIsNone(rabbit.asr)
        self.assertIsNone(rabbit.nlu)
        self.assertEqual(self.asr_type.call_count, 2)
        self.nlu_type.assert_not_called()
        self.nabio.set_leds.assert_called_with(None, None, None, None, None)
        self.nabio.pulse.assert_called_with(Led.BOTTOM, (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
