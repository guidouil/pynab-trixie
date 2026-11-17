import unittest
from unittest.mock import patch

from nabd.nlu import NLU

try:
    from nabd.asr import ASR
except ImportError:
    ASR = None


@unittest.skipIf(ASR is None, "Optional PocketSphinx is not installed")
class TestNativeCommandGrammar(unittest.TestCase):
    def test_each_documented_request_is_a_complete_alternative(self):
        alternatives = ASR._command_grammar().split(" | ")
        self.assertEqual(set(alternatives), set(NLU.PHRASES))
        self.assertEqual(len(alternatives), len(set(alternatives)))

    def test_a_short_command_does_not_inherit_another_commands_tail(self):
        phrases = {"a": 1, "a b": 1, "d c": 1}
        with patch.object(NLU, "PHRASES", phrases):
            alternatives = set(ASR._command_grammar().split(" | "))
        self.assertEqual(alternatives, {"a", "a b", "d c"})
        self.assertNotIn("a c", alternatives)
        self.assertNotIn("d b", alternatives)
