import asyncio
import io
import queue
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from nabd.nabio import NabIO

try:
    from nabd.sound_alsa import SoundAlsa
except ModuleNotFoundError as error:
    if error.name != "alsaaudio":
        raise
    sys.modules["alsaaudio"] = Mock()
    try:
        from nabd.sound_alsa import SoundAlsa
    finally:
        del sys.modules["alsaaudio"]


class TestNativeAcquisition(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.callback = Mock()
        self.recording = False
        self.record_cb = None
        self.sound = SimpleNamespace(
            start_recording=AsyncMock(side_effect=self.start),
            play_list=AsyncMock(side_effect=self.listen),
            stop_recording=AsyncMock(side_effect=self.stop),
        )
        self.nabio = SimpleNamespace(sound=self.sound, set_leds=Mock())

    async def start(self, callback):
        self.recording = True
        self.record_cb = callback
        callback(b"before beep", False)

    async def listen(self, files, preloaded):
        self.assertTrue(self.recording)
        self.assertEqual(files, ["asr/listen.mp3"])
        self.record_cb(b"listen beep", False)

    async def stop(self):
        self.recording = False
        if self.record_cb is not None:
            self.record_cb(b"last period", True)

    async def test_capture_opens_before_beep_and_ignores_it(self):
        await NabIO.start_acquisition(self.nabio, self.callback)
        self.callback.assert_not_called()
        self.record_cb(b"first spoken word", False)
        self.callback.assert_called_once_with(b"first spoken word", False)
        await self.sound.stop_recording()
        self.callback.assert_called_with(b"last period", True)

    async def test_failed_beep_closes_capture_and_keeps_finalize(self):
        self.sound.play_list.side_effect = OSError("beep failed")
        with self.assertRaisesRegex(OSError, "beep failed"):
            await NabIO.start_acquisition(self.nabio, self.callback)
        self.assertFalse(self.recording)
        self.sound.stop_recording.assert_awaited_once()
        self.callback.assert_called_once_with(b"", True)

    async def test_failed_capture_does_not_play_ready_beep(self):
        self.sound.start_recording.side_effect = OSError("microphone failed")
        with self.assertRaisesRegex(OSError, "microphone failed"):
            await NabIO.start_acquisition(self.nabio, self.callback)
        self.sound.play_list.assert_not_awaited()
        self.sound.stop_recording.assert_awaited_once()

    async def test_cancelled_beep_closes_microphone(self):
        listening = asyncio.Event()

        async def blocked_beep(files, preloaded):
            listening.set()
            await asyncio.Event().wait()

        self.sound.play_list.side_effect = blocked_beep
        task = asyncio.create_task(
            NabIO.start_acquisition(self.nabio, self.callback)
        )
        await listening.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.recording)
        self.callback.assert_called_once_with(b"", True)


class TestNativePCMReadiness(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.frames = queue.Queue()
        self.configuring, self.configured = (
            threading.Event(),
            threading.Event(),
        )
        self.configured.set()
        self.device = Mock()
        self.device.setperiodsize.side_effect = self.configure
        self.device.read.side_effect = lambda: self.frames.get(timeout=2)
        self.alsa = SimpleNamespace(
            PCM=Mock(return_value=self.device),
            PCM_CAPTURE=1,
            PCM_NORMAL=0,
            PCM_FORMAT_S16_LE=2,
        )
        self.sound = object.__new__(SoundAlsa)
        self.sound.record_device = "fake microphone"
        self.sound.future = self.sound.record_future = None
        self.sound.currently_playing = self.sound.currently_recording = False
        self.sound._recorded_raw = None
        self.sound.executor = ThreadPoolExecutor(max_workers=1)
        self.callback = Mock()
        logger = Mock()
        logger.isEnabledFor.return_value = False
        for patcher in (
            patch("nabd.sound_alsa.alsaaudio", self.alsa),
            patch("nabd.sound_alsa.logging.getLogger", return_value=logger),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def configure(self, periodsize):
        self.configuring.set()
        if not self.configured.wait(timeout=2):
            raise TimeoutError("test PCM configuration timed out")

    async def asyncTearDown(self):
        self.configured.set()
        if self.sound.record_future is not None:
            self.frames.put((0, b""))
            try:
                await self.sound.stop_recording()
            except Exception:
                pass
        self.sound.executor.shutdown()

    async def finish_capture(self):
        task = asyncio.create_task(self.sound.stop_recording())
        await asyncio.sleep(0)
        self.frames.put((1600, b"\x01\0" * 1600))
        await asyncio.wait_for(task, 1)

    async def test_start_waits_for_configured_pcm_and_stop_finalizes(self):
        self.configured.clear()
        task = asyncio.create_task(self.sound.start_recording(self.callback))
        self.assertTrue(await asyncio.to_thread(self.configuring.wait, 1))
        self.assertFalse(task.done())
        self.configured.set()
        await asyncio.wait_for(task, 1)
        self.device.setchannels.assert_called_once_with(1)
        self.device.setrate.assert_called_once_with(16000)
        self.device.setformat.assert_called_once_with(2)
        self.device.setperiodsize.assert_called_once_with(1600)
        await self.finish_capture()
        self.callback.assert_called_once_with(b"\x01\0" * 1600, True)
        self.device.close.assert_called_once()
        self.assertIsNone(self.sound.record_future)

    async def test_playback_runs_while_microphone_is_open(self):
        await self.sound.start_recording(self.callback)
        self.sound._play = Mock()
        await self.sound.start_playing_preloaded("listen.mp3")
        await asyncio.wait_for(self.sound.wait_until_done(), 1)
        self.sound._play.assert_called_once_with("listen.mp3")
        self.assertTrue(self.sound.currently_recording)
        self.assertFalse(self.sound.record_future.done())
        await self.finish_capture()

    async def test_pcm_configuration_error_propagates_and_closes(self):
        self.device.setrate.side_effect = OSError("PCM configuration failed")
        with patch("nabd.sound_alsa.logging.exception"):
            with self.assertRaisesRegex(OSError, "PCM configuration failed"):
                await self.sound.start_recording(self.callback)
        self.assertFalse(self.sound.currently_recording)
        self.assertIsNone(self.sound.record_future)
        self.device.close.assert_called_once()
        self.callback.assert_not_called()

    async def test_read_error_propagates_and_closes_debug_audio(self):
        await self.sound.start_recording(self.callback)
        raw = io.BytesIO()
        self.sound._recorded_raw = raw
        self.frames.put((-32, b""))
        await asyncio.wait_for(
            asyncio.wait([self.sound.record_future]), timeout=1
        )
        with self.assertRaisesRegex(OSError, "-32"):
            await self.sound.stop_recording()
        self.assertFalse(self.sound.currently_recording)
        self.assertIsNone(self.sound.record_future)
        self.assertTrue(raw.closed)
        self.device.close.assert_called_once()

    async def test_cancelled_start_waits_for_microphone_cleanup(self):
        self.configured.clear()
        task = asyncio.create_task(self.sound.start_recording(self.callback))
        self.assertTrue(await asyncio.to_thread(self.configuring.wait, 1))
        task.cancel()
        await asyncio.sleep(0)
        self.configured.set()
        self.frames.put((0, b""))
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        self.assertFalse(self.sound.currently_recording)
        self.assertIsNone(self.sound.record_future)
        self.device.close.assert_called_once()

    async def test_cancelled_stop_still_waits_for_final_pcm(self):
        await self.sound.start_recording(self.callback)
        task = asyncio.create_task(self.sound.stop_recording())
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        self.frames.put((0, b""))
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        self.callback.assert_called_once_with(b"", True)
        self.device.close.assert_called_once()
        self.assertIsNone(self.sound.record_future)


if __name__ == "__main__":
    unittest.main()
