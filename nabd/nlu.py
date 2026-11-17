"""Small French command vocabulary for responsive voice on the original Zero W."""

import datetime
import re
import unicodedata


class NLU:
    DEFAULT_LOCALE = "fr_FR"
    PHRASES = {
        "quelle heure est il": "clock",
        "donne moi l' heure": "clock",
        "météo": "weather",
        "la météo": "weather",
        "donne moi la météo": "weather",
        "quel temps fait il": "weather",
        "la météo aujourd'hui": "weather",
        "la météo demain": "tomorrow",
        "comment vas tu": "mood",
        "comment ça va": "mood",
        "donne moi ton humeur": "mood",
        "fais moi rire": "mood",
        "guili guili": "mood",
        "dis lapin": "8ball",
        "t' en penses quoi nabaztag": "8ball",
        "tu en penses quoi nabaztag": "8ball",
        "qualité de l' air": "airquality",
        "tai chi": "taichi",
        "c' est l' heure du tai chi": "taichi",
        "dodo": "sleep",
        "au lit": "sleep",
        "dormir": "sleep",
        "carotte": "carrot",
        "tu veux une carotte": "carrot",
        "que sais tu faire": "autopromo",
        "tu sais faire quoi": "autopromo",
        "anniversaire": "birthday",
        "c' est mon anniversaire": "birthday",
    }
    NOISE = (
        "euh",
        "attends",
        "bonjour",
        "coucou",
        "dis",
        "hein",
        "lapin",
        "nabaztag",
    )
    INTENTS = {
        "clock": "nabclockd/clock",
        "sleep": "nabclockd/sleep",
        "weather": "nabweatherd/forecast",
        "tomorrow": "nabweatherd/forecast",
        "airquality": "nabairqualityd/forecast",
        "mood": "nabsurprised/surprise",
        "8ball": "nab8balld/8ball",
        "taichi": "nabtaichid/taichi",
        "carrot": "nabsurprised/carrot",
        "autopromo": "nabsurprised/autopromo",
        "birthday": "nabsurprised/birthday",
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
    def normalize(text):
        text = unicodedata.normalize("NFC", text.lower()).replace("’", "'")
        text = text.replace("-", " ")
        text = re.sub(r"(?<!aujourd)'", "' ", text)
        return " ".join(text.strip(" ?!.,").split())

    @staticmethod
    def get_locale(locale):
        return NLU.DEFAULT_LOCALE

    def __init__(self, locale):
        pass

    async def interpret(self, string):
        phrase = self.normalize(string)
        command = self.PHRASES.get(phrase)
        if command is None:
            return None
        result = {"intent": self.INTENTS[command]}
        if command == "tomorrow" or phrase == "la météo aujourd'hui":
            result["date"] = (
                datetime.date.today()
                + datetime.timedelta(days=int(command == "tomorrow"))
            ).isoformat()
        return result
