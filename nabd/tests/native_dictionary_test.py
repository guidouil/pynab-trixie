import unittest
from pathlib import Path

from nabd.nlu import NLU


class TestNativeFrenchDictionary(unittest.TestCase):
    def test_every_command_word_has_one_nonempty_pronunciation(self):
        path = Path(__file__).resolve().parents[1] / "commands-fr.dict"
        entries = [
            line.split(maxsplit=1)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertTrue(entries)
        self.assertTrue(all(len(entry) == 2 for entry in entries))
        words = [word for word, phones in entries]
        self.assertEqual(len(words), len(set(words)))
        required = {
            word for phrase in NLU.PHRASES for word in phrase.split()
        } | set(NLU.NOISE)
        self.assertFalse(required - set(words), required - set(words))

    def test_every_acoustic_anchor_word_has_a_pronunciation(self):
        try:
            from nabd.asr import ASR
        except ImportError:
            self.skipTest("Optional PocketSphinx is not installed")
        required = {word for phrase in ASR.ANCHORS for word in phrase.split()}
        self.assertFalse(required - ASR.PRONUNCIATIONS.keys())
