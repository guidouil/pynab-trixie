import re
import unittest
from unittest.mock import patch

from nabd.nlu import NLU

try:
    from nabd.asr import ASR
except ImportError:
    ASR = None


def expanded_phrases(grammar):
    expression, *definitions = grammar.split(";")
    rules = dict(
        definition.strip().split(" = ", 1) for definition in definitions
    )
    cache = {}

    def expand(expression):
        tokens = iter(re.findall(r"[()[\]|]|[^()[\]|\s]+", expression))

        def alternatives(closing=None):
            choices = []
            sequence = [()]
            for token in tokens:
                if token == closing:
                    return choices + sequence
                if token == "|":
                    choices.extend(sequence)
                    sequence = [()]
                    continue
                if token in ("(", "["):
                    tail = alternatives(")" if token == "(" else "]")
                    if token == "[":
                        tail.append(())
                elif token in (")", "]"):
                    raise AssertionError("Unbalanced command grammar")
                elif token in rules:
                    if token not in cache:
                        cache[token] = expand(rules[token])
                    tail = cache[token]
                else:
                    tail = [(token,)]
                sequence = [
                    prefix + suffix for prefix in sequence for suffix in tail
                ]
            if closing is not None:
                raise AssertionError("Unclosed command grammar group")
            return choices + sequence

        return alternatives()

    return [" ".join(words) for words in expand(expression)]


@unittest.skipIf(ASR is None, "Optional PocketSphinx is not installed")
class TestNativeCommandGrammar(unittest.TestCase):
    def test_prefix_command_is_optional_without_crossing_branches(self):
        phrases = {"a": 1, "a b": 1, "a c": 1, "d": 1}
        with patch.object(NLU, "PHRASES", phrases):
            grammar = ASR._command_grammar()
        self.assertEqual(set(expanded_phrases(grammar)), set(phrases))

    def test_equivalent_suffixes_share_a_rule_without_crossing_branches(self):
        phrases = {"a b c": 1, "a b": 1, "d b c": 1, "d b": 1, "x": 1}
        with patch.object(NLU, "PHRASES", phrases):
            grammar = ASR._command_grammar()
        self.assertEqual(set(expanded_phrases(grammar)), set(phrases))
        self.assertEqual(len(re.findall(r"\bb\b", grammar)), 1)

    def test_factored_grammar_preserves_exactly_the_supported_phrases(self):
        grammar = ASR._command_grammar()
        self.assertLess(len(grammar), 15000)
        expanded = expanded_phrases(grammar)
        self.assertEqual(set(expanded), set(NLU.PHRASES))
        self.assertEqual(len(expanded), len(set(expanded)))
