"""Check the historical service commands against the autonomous French NLU."""

import datetime
import itertools
import re
import unittest
from pathlib import Path

from nabd.nlu import NLU


class TestNativeNLUCoverage(unittest.IsolatedAsyncioTestCase):
    async def test_each_historical_service_intent(self):
        examples = {
            "nabclockd/clock": (
                "horloge",
                "aurais-tu l'heure",
                "tu pourrais me donner l'heure",
            ),
            "nabclockd/sleep": (
                "dodo",
                "c'est l'heure de dormir",
                "c'est l'heure de se coucher",
                "au lit",
            ),
            "nabweatherd/forecast": (
                "météo",
                "est-ce qu'il fera beau",
                "est-ce que je peux sortir en chemise",
            ),
            "nabairqualityd/forecast": (
                "air",
                "quel est le taux de CO2",
                "est-ce que je peux aller dehors ou c'est trop pollué",
            ),
            "nab8balld/8ball": (
                "gourou",
                "dis-moi lapin",
                "et toi nabaztag qu'en penses-tu",
                "dis lapin j'le fais ou je ne le fais pas",
            ),
            "nabtaichid/taichi": (
                "tai-chi",
                "tu me referais ton tai-chi",
                "j'adore le tai-chi tu me le referais",
            ),
            "nabsurprised/surprise": (
                "guili guili",
                "fais-moi rire",
                "raconte-moi un truc",
                "surprise surprise",
                "comment ça va",
            ),
            "nabsurprised/carrot": (
                "carotte",
                "aimes-tu les carottes",
                "tu veux une carotte",
            ),
            "nabsurprised/autopromo": (
                "que sais-tu faire",
                "tu sais faire quoi nabaztag",
            ),
            "nabsurprised/birthday": (
                "anniversaire",
                "c'est mon anniversaire",
                "c'est l'anniversaire de simon",
            ),
        }
        nlu = NLU("fr_FR")
        for intent, phrases in examples.items():
            for phrase in phrases:
                with self.subTest(phrase=phrase):
                    self.assertEqual(
                        (await nlu.interpret(phrase))["intent"], intent
                    )
        self.assertEqual(set(examples), set(NLU.INTENTS.values()))

    async def test_weather_dates_and_air_quality_slot_compatibility(self):
        nlu = NLU("fr_FR")
        today = datetime.date.today()
        for service, request in (
            ("nabweatherd/forecast", "est-ce qu'il va pleuvoir"),
            ("nabairqualityd/forecast", "c'est pas un peu pollué"),
        ):
            for date, days in (
                ("aujourd'hui", 0),
                ("ce matin", 0),
                ("cet après-midi", 0),
                ("dans l'heure", 0),
                ("demain", 1),
                ("demain matin", 1),
            ):
                with self.subTest(service=service, date=date):
                    self.assertEqual(
                        await nlu.interpret(f"{request} {date}"),
                        {
                            "intent": service,
                            "date": (
                                today + datetime.timedelta(days=days)
                            ).isoformat(),
                        },
                    )
        self.assertEqual(
            await nlu.interpret("météo"), {"intent": "nabweatherd/forecast"}
        )

    async def test_historical_birthday_names_and_elisions(self):
        nlu = NLU("fr_FR")
        self.assertEqual(len(NLU.FIRST_NAMES), 315)
        for names, preposition in (
            (NLU.FIRST_NAMES, "de "),
            (NLU.ELIDED_NAMES, "d'"),
        ):
            for name in names:
                with self.subTest(name=name, preposition=preposition):
                    self.assertEqual(
                        await nlu.interpret(
                            f"c'est l'anniversaire {preposition}{name}"
                        ),
                        {
                            "intent": "nabsurprised/birthday",
                            "firstname": name,
                        },
                    )
        self.assertIn("jean-pierre", NLU.FIRST_NAMES)
        self.assertNotIn("jean-", NLU.FIRST_NAMES)
        self.assertTrue(
            {"inès", "iskander", "ivor", "oskar"}.issubset(NLU.ELIDED_NAMES)
        )

    async def test_current_service_yaml_utterances_are_covered(self):
        # Read this simple training corpus without adding a YAML dependency.
        corpus = Path(__file__).resolve().parents[2]
        checked = 0
        for filename in corpus.glob("nab*/nlu/intent_fr.yaml"):
            intent, mode = None, None
            for line in filename.read_text().splitlines():
                if line.startswith("name: "):
                    intent = line[6:]
                elif line in ("utterances:", "values:"):
                    mode = line
                elif (
                    line.startswith("  - ")
                    and mode == "values:"
                    and intent == "nabaztag/firstname"
                ):
                    self.assertIn(line[4:], NLU.FIRST_NAMES)
                elif line.startswith("  - ") and mode == "utterances:":
                    phrase = re.sub(r"\[[^]]+\]\(([^)]+)\)", r"\1", line[4:])
                    # Correct the historical YAML typo in the date annotation.
                    phrase = phrase.replace("aujourd'hui'", "aujourd'hui")
                    with self.subTest(phrase=phrase, source=filename.name):
                        result = await NLU("fr_FR").interpret(phrase)
                        self.assertIsNotNone(result)
                        self.assertEqual(result["intent"], intent)
                    checked += 1
        self.assertGreater(checked, 60)

    async def test_optional_hesitations_and_input_normalization(self):
        for prefix, suffix in itertools.product(("", "euh "), ("", " euh")):
            self.assertEqual(
                await NLU("fr_FR").interpret(
                    prefix + "T’en penses quoi Nabaztag" + suffix + " ?"
                ),
                {"intent": "nab8balld/8ball"},
            )
        self.assertEqual(
            await NLU("fr_FR").interpret("QUELLE HEURE EST-IL ?"),
            {"intent": "nabclockd/clock"},
        )

    async def test_noise_partial_unknown_and_multi_intent_are_rejected(self):
        for phrase in (
            *NLU.NOISE,
            "bonjour lapin",
            "penses quoi",
            "c'est l'heure de",
            "c'est l'anniversaire de personne",
            "météo et air",
            "dodo et carotte",
            "météo demain et aujourd'hui",
            "dis-moi lapin et fais-moi rire",
        ):
            with self.subTest(phrase=phrase):
                self.assertIsNone(await NLU("fr_FR").interpret(phrase))


if __name__ == "__main__":
    unittest.main()
