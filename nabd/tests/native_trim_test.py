import unittest
from array import array
from unittest.mock import patch

try:
    from nabd.asr import ASR
except ImportError:
    ASR = None


class FakeVad:
    frame_bytes = 960
    sample_rate = 16000

    def __init__(self, **kwargs):
        pass

    def is_speech(self, frame):
        return True


@unittest.skipIf(ASR is None, "Optional PocketSphinx is not installed")
class TestNativeVoiceTrimming(unittest.TestCase):
    def pcm(self, levels):
        return b"".join(
            array("h", [level] * 480).tobytes() for level in levels
        )

    def trim(self, pcm):
        with patch("nabd.asr.Vad", FakeVad):
            return ASR._trim_silence(pcm)

    def test_room_hum_and_button_click_do_not_extend_the_speech(self):
        levels = [100] * 120
        levels[30:40] = [1000] * 10
        levels[110] = 5000
        pcm = self.pcm(levels)
        self.assertEqual(self.trim(pcm), pcm[22400:44800])

    def test_both_commands_and_the_pause_between_them_are_preserved(self):
        levels = [100] * 120
        levels[20:30] = [1000] * 10
        levels[65:70] = [500] * 5
        pcm = self.pcm(levels)
        self.assertEqual(self.trim(pcm), pcm[12800:73600])

    def test_zero_frames_are_not_counted_as_speech_when_vad_hangs_over(self):
        levels = [0] * 120
        levels[30:40] = [1000] * 10
        pcm = self.pcm(levels)
        self.assertEqual(self.trim(pcm), pcm[22400:44800])

    def test_short_gap_within_a_command_does_not_drop_its_first_word(self):
        levels = [100] * 100
        levels[20:24] = [1000] * 4
        levels[29:38] = [1000] * 9
        pcm = self.pcm(levels)
        self.assertEqual(self.trim(pcm), pcm[12800:42880])

    def test_uncertain_or_short_speech_is_left_unchanged(self):
        for levels in ([1000] * 100, [100] * 50 + [1000] * 6 + [100] * 50):
            with self.subTest(levels=levels):
                pcm = self.pcm(levels)
                self.assertEqual(self.trim(pcm), pcm)

    def test_silence_is_empty_and_partial_frame_is_unchanged(self):
        self.assertEqual(self.trim(b"\0" * 9600), b"")
        self.assertEqual(self.trim(b"\x01\0" * 100), b"\x01\0" * 100)
