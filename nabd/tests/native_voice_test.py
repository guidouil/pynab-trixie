import asyncio
import datetime
import json
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

from nabd.nlu import NLU

try:
    from nabd.asr import ASR
except ImportError:
    ASR = None


class TestNativeNLU(unittest.IsolatedAsyncioTestCase):
    async def test_native_intents_and_tomorrow(self):
        nlu = NLU("fr_FR")
        for phrase, command in NLU.PHRASES.items():
            with self.subTest(phrase=phrase):
                result = await nlu.interpret(phrase)
                self.assertEqual(result["intent"], NLU.INTENTS[command])
                if command == "tomorrow":
                    self.assertEqual(
                        result["date"],
                        (
                            datetime.date.today() + datetime.timedelta(days=1)
                        ).isoformat(),
                    )
                else:
                    self.assertNotIn("date", result)

    async def test_unknown_partial_and_multiple_commands_are_rejected(self):
        for phrase in (
            "",
            "demain",
            "quelle heure est",
            "bonjour",
            "quelle heure est il et la météo",
        ):
            self.assertIsNone(await NLU("fr_FR").interpret(phrase))


@unittest.skipIf(ASR is None, "Optional PocketSphinx is not installed")
class TestNativeASRBuffer(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.asr = object.__new__(ASR)
        self.asr._buffer_lock = threading.Lock()
        self.asr._worker_lock = asyncio.Lock()
        self.asr._process = None
        self.asr.reset()
        self.asr._decode = AsyncMock(return_value="la météo")

    async def test_async_decode_keeps_buffer_one_shot(self):
        pcm = b"\x01\x00" * 5000

        async def decode(data):
            self.assertEqual(data, pcm)
            await asyncio.sleep(0.03)
            return "la météo"

        self.asr._decode.side_effect = decode
        self.asr.decode_chunk(pcm[:5000], False)
        self.asr.decode_chunk(pcm[5000:], True)
        task = asyncio.create_task(self.asr.get_decoded_string())
        await asyncio.sleep(0.005)
        self.assertFalse(task.done())
        self.assertEqual(await task, "la météo")
        self.asr._decode.assert_awaited_once_with(pcm)
        self.assertEqual(await self.asr.get_decoded_string(), "")

    async def test_invalid_unfinished_short_and_oversized_audio_are_rejected(
        self,
    ):
        for pcm, finalized in (
            (b"\0" * 6400, False),
            (b"\0" * 20, True),
            (b"\0" * 6401, True),
            (b"\0" * (ASR.MAX_BYTES + 2), True),
        ):
            with self.subTest(size=len(pcm), finalized=finalized):
                self.asr.reset()
                self.asr.decode_chunk(pcm, finalized)
                self.assertLessEqual(len(self.asr._pcm), ASR.MAX_BYTES)
                self.assertEqual(await self.asr.get_decoded_string(), "")
        self.asr._decode.assert_not_awaited()

    async def test_reset_discards_cancelled_capture(self):
        self.asr.decode_chunk(b"\x01\x00" * 4000, False)
        self.asr.reset()
        pcm = b"\x02\x00" * 4000
        self.asr.decode_chunk(pcm, True)
        self.assertEqual(await self.asr.get_decoded_string(), "la météo")
        self.asr._decode.assert_awaited_once_with(pcm)

    async def test_child_failure_reports_bounded_diagnostic(self):
        process = Mock(returncode=None)
        process.stdin.drain = AsyncMock()
        process.stdout.readline = AsyncMock(
            side_effect=[
                b'{"ready": true}\n',
                json.dumps({"error": "x" * 1000}).encode() + b"\n",
            ]
        )
        process.wait = AsyncMock()
        with patch(
            "nabd.asr.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ):
            with self.assertRaises(RuntimeError) as error:
                await ASR._decode(self.asr, b"\0" * 6400)
        self.assertEqual(
            str(error.exception), "French voice decoder failed: " + "x" * 500
        )
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()
        self.assertIsNone(self.asr._process)

    async def test_cancel_kills_and_reaps_child(self):
        started = asyncio.Event()
        reads = 0

        async def readline():
            nonlocal reads
            reads += 1
            if reads == 1:
                return b'{"ready": true}\n'
            started.set()
            await asyncio.Event().wait()

        process = Mock(returncode=None)
        process.stdin.drain = AsyncMock()
        process.stdout.readline = AsyncMock(side_effect=readline)
        process.wait = AsyncMock()
        with patch(
            "nabd.asr.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ):
            task = asyncio.create_task(ASR._decode(self.asr, b"\0" * 6400))
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()
        self.assertIsNone(self.asr._process)

    async def test_worker_is_reused_and_pcm_is_framed(self):
        process = Mock(returncode=None)
        process.stdin.drain = AsyncMock()
        process.stdout.readline = AsyncMock(
            side_effect=[
                b'{"ready": true}\n',
                '{"text": "la météo"}\n'.encode(),
                b'{"text": "quelle heure est il"}\n',
            ]
        )
        process.wait = AsyncMock()
        pcm = b"\0" * 6400
        with patch(
            "nabd.asr.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ) as spawn:
            await self.asr.start()
            await self.asr.start()
            self.assertEqual(await ASR._decode(self.asr, pcm), "la météo")
            self.assertEqual(
                await ASR._decode(self.asr, pcm), "quelle heure est il"
            )
            spawn.assert_awaited_once()
            self.assertEqual(process.stdin.write.call_count, 2)
            process.stdin.write.assert_called_with(
                len(pcm).to_bytes(4, "big") + pcm
            )
            await self.asr.close()
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
