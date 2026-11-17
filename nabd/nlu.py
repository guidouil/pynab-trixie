"""Small French command vocabulary for the autonomous voice backend."""

import datetime


class NLU:
    DEFAULT_LOCALE = "fr_FR"
    PHRASES = {
        "quelle heure est il": "clock",
        "il est quelle heure": "clock",
        "donne moi l' heure": "clock",
        "dis moi l' heure": "clock",
        "la météo": "weather",
        "donne moi la météo": "weather",
        "quelle est la météo": "weather",
        "quel temps fait il": "weather",
        "la météo aujourd'hui": "weather",
        "quel temps fait il aujourd'hui": "weather",
        "la météo demain": "tomorrow",
        "donne moi la météo demain": "tomorrow",
        "quel temps fait il demain": "tomorrow",
        "comment vas tu": "mood",
        "comment ça va": "mood",
        "donne moi ton humeur": "mood",
        "comment te sens tu": "mood",
        "t' en penses quoi nabaztag": "8ball",
        "tu en penses quoi nabaztag": "8ball",
    }
    INTENTS = {
        "clock": "nabclockd/clock",
        "weather": "nabweatherd/forecast",
        "tomorrow": "nabweatherd/forecast",
        "mood": "nabsurprised/surprise",
        "8ball": "nab8balld/8ball",
    }
    # Older installed dictionaries lack these words; Nabaztag is not in fr.dict.
    EXTRA_PRONUNCIATIONS = {
        "t'": "tt",
        "en": "an",
        "penses": "pp an ss",
        "quoi": "kk ww aa",
        "nabaztag": "nn aa bb aa zz tt aa gg",
    }

    @staticmethod
    def get_locale(locale):
        return NLU.DEFAULT_LOCALE

    def __init__(self, locale):
        pass

    async def interpret(self, string):
        command = self.PHRASES.get(string)
        if command is None:
            return None
        result = {"intent": self.INTENTS[command]}
        if command == "tomorrow":
            result["date"] = (
                datetime.date.today() + datetime.timedelta(days=1)
            ).isoformat()
        return result
