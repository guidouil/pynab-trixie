"""French voice commands, restored from the historical JSGF and service YAML."""

import datetime
import itertools
import re
import unicodedata

# Source: 80d3633^:asr/nabaztag-grammar-fr.jsgf and nab*/nlu/intent_fr.yaml.
FIRST_NAMES = tuple("""
adrien agnès alain alan alban albert alex alexander alexandre alexis alice
alix alyson amanda amar amaury anaïs andré andrée anna anne annick annie
anthony antoine antonin armand armando arnaud arthur audrey aurélie aurélien
axel bastien béatrice benjamin benoît bernadette bernard bertrand blaise
boris brian brice brigitte brize bruce bruno camille candice carine carole
caroline catherine cécile cécilien cédric célia céline chantal charles
charles-édouard charlotte chloé christelle christian christiane christine
christophe claire clara claude claudine clément clothilde colette corinne
coumba cyrielle cyril cyrille damien daniel danielle dante david delphine
denis denise diane didier dimitri dirk dominique ed éliane élie élisa
élisabeth élise elsa émeline émile émilie emma emmanuel emmanuelle enzo éric
étienne évelyne fabien fabrice fernand flavien florence florent florian
france francis francisco franck fred gabriel gaël gaëtan geneviève georges
georgette gérard germaine gerry ghislain gilbert gilles ginette gisèle greg
guillaume guy harold hélène henri henriette hervé hugo isa isabelle
jacqueline jacques james jan jean jean-baptiste jean-christophe jean-claude
jean-jacques jean-luc jean-marc jean-michel jean-pascal jean-philippe
jean-pierre jean-yves jeanne jeannine jennifer jérémie jérémy jocelyn
jocelyne joël johnny jonathan joseph josette josiane jules julie julien
juliette kari karine kevin laetitia laura laurence laurent léa léon léonard
liliane lionel loïc louis louise luc lucas lucie lucien lucienne ludivine
ludovic madeleine maeva manon manuel marc marcel marcelle marco marguerite
maria marie marine marion mark marthe martin martine mathias mathieu
mathilde matthieu maud maurice max maxime maÿlis mélanie michaël michel
michèle michelle mickael mickaël mireille monique muriel nadine natacha
nathalie nicolas nicole nils odette olivier pascal patrice patricia patrick
paul paulette pauline philémon philippe pierre pierre-olivier quentin rafi
raymond raymonde rémi renaud rené renée richard robert rodolphe roger roland
romain romuald ronan sandrine sarah serge séverine simon simone sonia sophie
steve steven suzanne sylvain sylvie tanguy théo thérèse thibault thibaut
thierry thomas tony tristan valentin valérie véronique victor vincent
violette virginie vivien xavier yann yannick yoann yolande yvan yves yvette
yvonne zélie
""".split())
ELIDED_NAMES = tuple("""
adrien agnès alain alan alban albert alex alexander alexandre alexis alice
alix alyson amanda amar amaury anaïs andré andrée anna anne annick annie
anthony antoine antonin armand armando arnaud arthur audrey aurélie aurélien
axel élisabeth émile émilie emma emmanuelle éric étienne évelyne hélène
henri henriette hervé hugo inès isa isabelle iskander ivor odette olivier
oskar yves yvette yvonne
""".split())


def _normalize(text):
    text = unicodedata.normalize("NFC", text.lower()).replace("’", "'")
    text = text.replace("-", " ")
    text = re.sub(r"(?<!aujourd)'", "' ", text)
    return " ".join(text.strip(" ?!.,").split())


def _commands():
    phrases, slots = {}, {}

    def add(phrase, kind, date=None, firstname=None):
        phrase = _normalize(phrase)
        for prefix, suffix in itertools.product(("", "euh "), ("", " euh")):
            command = prefix + phrase + suffix
            phrases[command] = kind
            if date is not None:
                slots[command] = {"date": date}
            elif firstname is not None:
                slots[command] = {"firstname": firstname}

    dates = (
        "",
        "aujourd'hui",
        "demain",
        "ce matin",
        "demain matin",
        "cet après-midi",
        "dans l'heure",
    )

    def dated(phrase, kind="weather", please=False, variants=dates):
        for date in variants:
            offset = int("demain" in date) if date else None
            command = "tomorrow" if kind == "weather" and offset == 1 else kind
            for end in (("", " s'il-te-plait") if please else ("",)):
                add(f"{phrase} {date}{end}", command, date=offset)

    giveme = (
        "tu me donnerais",
        "donne-moi",
        "tu peux me donner",
        "tu pourrais me donner",
        "est-ce que tu peux me donner",
        "est-ce que tu pourrais me donner",
    )
    dated("météo")
    for request, noun in itertools.product(giveme, ("la", "les prévisions")):
        dated(
            f"{request} {noun} météo",
            please=True,
            variants=(
                "",
                "d'aujourd'hui",
                "de demain",
                "pour aujourd'hui",
                "pour demain",
            ),
        )
    dated(
        "donne-moi les prévisions météos",
        variants=("pour aujourd'hui", "pour demain"),
    )
    forecasts = (
        "pleuvra",
        "va pleuvoir",
        "va faire chaud",
        "va faire froid",
        "fera chaud",
        "fera froid",
        "va faire beau",
        "y aura des éclaircies",
    )
    for forecast in forecasts:
        dated(f"dis-moi s'il {forecast}", please=True)
        for request in ("est-ce qu'il", "est-ce que il"):
            dated(f"{request} {forecast}")
    for forecast in ("pleut", "fait chaud", "fait froid", "fera beau"):
        dated(f"est-ce qu'il {forecast}")
    for subject, clothing in itertools.product(
        ("j'ai", "j'aurai"),
        ("parapluie", "pull", "imper", "k-way", "imperméable", "blouson"),
    ):
        dated(f"est-ce que {subject} besoin d'un {clothing}")
    # Parentheses were missing around the clothing alternatives in the JSGF.
    for clothing in ("t-shirt", "chemise", "short"):
        dated(f"est-ce que je peux sortir en {clothing}")
    dated("est-ce que je peux mettre un short")
    for tense, place in itertools.product(
        ("fera-t-il", "fait-il", "il fait", "il va faire"),
        ("", "dehors", "à l'extérieur"),
    ):
        dated(f"quel temps {tense} {place}")
    for tense in ("est", "sera"):
        dated(f"quelle {tense} la météo")
    for forecast in (
        "faire beau",
        "faire froid",
        "faire chaud",
        "neiger",
        "pleuvoir",
    ):
        dated(f"va-t-il {forecast}")

    add("air", "airquality")
    for noun, article in (("qualité de l'air", "la"), ("taux de CO2", "le")):
        dated(noun, "airquality")
        for request in giveme:
            dated(f"{request} {article} {noun}", "airquality")
        question = "quelle est la" if article == "la" else "quel est le"
        for date, place in itertools.product(
            dates, ("", "dehors", "à l'extérieur")
        ):
            add(
                f"{question} {noun} {date} {place}",
                "airquality",
                date=int("demain" in date) if date else None,
            )
    for place in ("dehors", "à l'extérieur"):
        add(
            f"est-ce que je peux aller {place} ou c'est trop pollué",
            "airquality",
        )
    dated("c'est pas un peu pollué", "airquality")

    add("gourou", "8ball")
    for name in ("gourou", "lapin", "nabaztag"):
        for request in ("dis", "dis-moi"):
            add(f"{request} {name}", "8ball")
        add(f"dis {name} qu'est-ce que t'en penses", "8ball")
        add(f"et toi {name} qu'en penses-tu", "8ball")
        add(f"t'en penses quoi {name}", "8ball")
        add(f"dis {name} tu y crois ou pas", "8ball")
        for request in ("dis", "à ton avis"):
            add(f"{request} {name} est-ce que c'est une bonne idée", "8ball")
            add(f"{request} {name} j'y vais ou j'y vais pas", "8ball")
            for positive, negative in itertools.product(
                ("je le", "j'le"), ("je ne le", "je le", "j'le")
            ):
                add(
                    f"{request} {name} {positive} fais ou {negative} fais pas",
                    "8ball",
                )
    add("tu en penses quoi nabaztag", "8ball")

    for phrase in (
        "guili-guili",
        "chatouille",
        "fais-moi rire",
        "raconte un truc",
        "raconte-moi un truc",
        "surprise",
        "surprise surprise",
        "humeur",
        "comment vas-tu",
        "comment ça va",
        "donne-moi ton humeur",
        "comment te sens-tu",
    ):
        add(phrase, "mood")
    for phrase in ("carotte", "tu veux une carotte", "aimes-tu les carottes"):
        add(phrase, "carrot")
    for request, name in itertools.product(
        ("que sais-tu faire", "tu sais faire quoi"), ("", "nabaztag", "lapin")
    ):
        add(f"{request} {name}", "autopromo")
    for phrase in (
        "anniversaire",
        "c'est mon anniversaire",
        "c'est ton anniversaire",
        "c'est son anniversaire",
    ):
        add(phrase, "birthday")
    for name in FIRST_NAMES:
        add(f"c'est l'anniversaire de {name}", "birthday", firstname=name)
    for name in ELIDED_NAMES:
        add(f"c'est l'anniversaire d'{name}", "birthday", firstname=name)

    for phrase in (
        "horloge",
        "est-ce que c'est l'heure",
        "il est quelle heure",
        "quelle heure est-il",
        "aurais-tu l'heure",
        "dis-moi l'heure",
    ):
        add(phrase, "clock")
    for request in giveme:
        add(f"{request} l'heure", "clock")
    add("tai-chi", "taichi")
    for article in ("du", "de ton"):
        add(f"c'est l'heure {article} tai-chi", "taichi")
    for article in ("le", "ton"):
        add(f"tu me referais {article} tai-chi", "taichi")
        add(f"j'adore {article} tai-chi tu me le referais", "taichi")
    for phrase in (
        "dormir",
        "dodo",
        "c'est l'heure de faire dodo",
        "c'est l'heure de se coucher",
        "c'est l'heure",
        "c'est l'heure d'aller au lit",
        "c'est l'heure de dormir",
        "au lit",
    ):
        add(phrase, "sleep")

    # Keep every command already supported by the native backend.
    for phrase in (
        "la météo",
        "donne-moi la météo",
        "quelle est la météo",
        "quel temps fait-il",
        "la météo aujourd'hui",
        "quel temps fait-il aujourd'hui",
        "la météo demain",
        "donne-moi la météo demain",
        "quel temps fait-il demain",
    ):
        date = (
            1 if "demain" in phrase else 0 if "aujourd'hui" in phrase else None
        )
        add(phrase, "tomorrow" if date == 1 else "weather", date=date)
    return phrases, slots


class NLU:
    DEFAULT_LOCALE = "fr_FR"
    PHRASES, SLOTS = _commands()
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
    FIRST_NAMES = FIRST_NAMES
    ELIDED_NAMES = ELIDED_NAMES
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
    normalize = staticmethod(_normalize)

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
        for slot, value in self.SLOTS.get(phrase, {}).items():
            result[slot] = (
                (
                    datetime.date.today() + datetime.timedelta(days=value)
                ).isoformat()
                if slot == "date"
                else value
            )
        return result
