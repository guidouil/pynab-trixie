"""Check the bounded French commands independently from the recognizer table."""

import datetime
import unittest

from nabd.nlu import NLU


class TestNativeNLUCoverage(unittest.IsolatedAsyncioTestCase):
    async def test_the_28_documented_commands_route_to_all_ten_services(self):
        examples = {
            "nabclockd/clock": ("Quelle heure est-il ?", "Donne-moi l’heure"),
            "nabclockd/sleep": ("Dodo", "Au lit", "Dormir"),
            "nabweatherd/forecast": (
                "Météo",
                "La météo",
                "Donne-moi la météo",
                "Quel temps fait-il ?",
                "La météo aujourd’hui",
                "La météo demain",
            ),
            "nabairqualityd/forecast": ("Qualité de l’air",),
            "nab8balld/8ball": (
                "Dis lapin",
                "T’en penses quoi Nabaztag ?",
                "Tu en penses quoi Nabaztag ?",
            ),
            "nabtaichid/taichi": ("Tai-chi", "C’est l’heure du tai-chi"),
            "nabsurprised/surprise": (
                "Comment vas-tu ?",
                "Comment ça va ?",
                "Donne-moi ton humeur",
                "Fais-moi rire",
                "Guili guili",
            ),
            "nabsurprised/carrot": ("Carotte", "Tu veux une carotte ?"),
            "nabsurprised/autopromo": (
                "Que sais-tu faire ?",
                "Tu sais faire quoi ?",
            ),
            "nabsurprised/birthday": (
                "Anniversaire",
                "C’est mon anniversaire",
            ),
        }
        normalized = set()
        for intent, phrases in examples.items():
            for phrase in phrases:
                normalized.add(NLU.normalize(phrase))
                with self.subTest(phrase=phrase):
                    self.assertEqual(
                        (await NLU("fr_FR").interpret(phrase))["intent"],
                        intent,
                    )
        self.assertEqual(len(normalized), 28)
        self.assertEqual(normalized, set(NLU.PHRASES))
        self.assertEqual(set(examples), set(NLU.INTENTS.values()))

    async def test_today_tomorrow_and_default_weather_dates(self):
        nlu = NLU("fr_FR")
        today = datetime.date.today()
        for phrase, days in (
            ("La météo aujourd’hui", 0),
            ("La météo demain", 1),
        ):
            self.assertEqual(
                await nlu.interpret(phrase),
                {
                    "intent": "nabweatherd/forecast",
                    "date": (
                        today + datetime.timedelta(days=days)
                    ).isoformat(),
                },
            )
        for phrase in ("Météo", "La météo", "Qualité de l’air"):
            self.assertNotIn("date", await nlu.interpret(phrase))

    async def test_input_normalization(self):
        for phrase in (
            "QUELLE HEURE EST-IL ?",
            "  Fais-moi rire !  ",
            "que sais-tu faire ?",
        ):
            self.assertIsNotNone(await NLU("fr_FR").interpret(phrase))
        self.assertEqual(
            NLU.normalize("Donne-moi l’heure"), "donne moi l' heure"
        )

    async def test_names_old_variants_noise_and_multiple_commands_are_rejected(
        self,
    ):
        for phrase in (
            *NLU.NOISE,
            "bonjour lapin",
            "penses quoi",
            "quelle heure est",
            "euh fais moi rire",
            "fais moi rire euh",
            "c’est l’anniversaire d’Émile",
            "c’est l’anniversaire de Jean-Pierre",
            "donne moi la météo demain",
            "quel temps fera-t-il demain matin",
            "c’est pas un peu pollué aujourd’hui",
            "dodo et carotte",
            "quelle heure est-il et la météo",
            "la météo demain et aujourd’hui",
            "dis lapin et fais moi rire",
        ):
            with self.subTest(phrase=phrase):
                self.assertIsNone(await NLU("fr_FR").interpret(phrase))


if __name__ == "__main__":
    unittest.main()
