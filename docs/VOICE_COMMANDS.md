# Commandes vocales natives

Maintenir le bouton de la tête, attendre le bip, parler puis relâcher. La capture
s’arrête après 15 secondes. La reconnaissance est locale et uniquement en français,
quelle que soit la langue choisie pour les sons du lapin. La météo et la qualité
de l’air gardent leur accès Internet habituel.

## Les dix intentions françaises

Les commandes historiques françaises sont rétablies. Les formulations natives
déjà présentes sont conservées, notamment « La météo », « Comment vas-tu ? »
et « Tu en penses quoi Nabaztag ? ».

| Intention | Exemples de phrases |
| --- | --- |
| Heure | « Quelle heure est-il ? », « Il est quelle heure ? », « Donne-moi l’heure », « Aurais-tu l’heure », « Horloge » |
| Sommeil | « Dodo », « Au lit », « Dormir », « C’est l’heure de dormir », « C’est l’heure d’aller au lit » |
| Météo | « Météo », « La météo demain », « Quel temps fait-il aujourd’hui ? », « Est-ce qu’il va pleuvoir aujourd’hui ? », « Est-ce que j’aurai besoin d’un parapluie demain ? » |
| Qualité de l’air | « Air », « Qualité de l’air », « Donne-moi la qualité de l’air », « C’est pas un peu pollué aujourd’hui » |
| Taï-chi | « Tai-chi », « C’est l’heure du tai-chi », « Tu me referais le tai-chi », « J’adore le tai-chi tu me le referais » |
| Gourou | « Gourou », « Dis lapin », « Dis-moi gourou », « T’en penses quoi Nabaztag ? », « À ton avis gourou est-ce que c’est une bonne idée » |
| Surprise et humeur | « Guili guili », « Chatouille », « Fais-moi rire », « Raconte-moi un truc », « Surprise », « Humeur », « Comment vas-tu ? » |
| Carotte | « Carotte », « Tu veux une carotte », « Aimes-tu les carottes » |
| Présentation | « Que sais-tu faire », « Que sais-tu faire Nabaztag », « Tu sais faire quoi lapin » |
| Anniversaire | « Anniversaire », « C’est mon anniversaire », « C’est ton anniversaire », « C’est son anniversaire », « C’est l’anniversaire de Thomas » |

## Variantes prévues

- Les demandes d’heure, de météo et de qualité de l’air acceptent les tournures
  historiques « donne-moi », « tu me donnerais », « tu peux me donner »,
  « tu pourrais me donner », « est-ce que tu peux me donner » et
  « est-ce que tu pourrais me donner », avec le complément correspondant.
- La météo accepte les demandes de pluie, neige, beau temps, chaleur, froid,
  éclaircies, parapluie et vêtements (pull, imperméable, blouson, t-shirt,
  chemise ou short), selon les tournures historiques.
- Les indications temporelles historiques sont « aujourd’hui », « demain »,
  « ce matin », « demain matin », « cet après-midi » et « dans l’heure ».
  Les demandes météo acceptent aussi « d’aujourd’hui », « de demain »,
  « pour aujourd’hui » et « pour demain » dans les tournures prévues.
- Le Gourou accepte « lapin », « Nabaztag » ou « gourou » dans ses appels
  historiques : « dis », « dis-moi », « qu’est-ce que t’en penses »,
  « et toi … qu’en penses-tu », « t’en penses quoi … », « à ton avis … est-ce
  que c’est une bonne idée », « tu y crois ou pas », « j’y vais ou j’y vais
  pas » et « je le fais ou je le fais pas ».
- Le taï-chi accepte « le » ou « ton » dans les demandes historiques.
  Le sommeil accepte aussi « faire dodo » et « se coucher » dans
  « c’est l’heure de … ».
- La présentation peut se terminer par « lapin » ou « Nabaztag ».
  L’anniversaire accepte les 315 prénoms historiques, avec « de » ou « d’ »
  selon la formulation, ainsi que les quatre élisions supplémentaires du JSGF :
  « d’Inès », « d’Iskander », « d’Ivor » et « d’Oskar ». La réponse ne prononce
  pas le prénom.
- Un « euh » peut précéder ou suivre une commande. Les mots isolés de bruit
  comme « bonjour » ne déclenchent aucune action.

Le vocabulaire reste fermé : cette couverture ne signifie pas que toute demande
libre ou tout synonyme est compris. La ponctuation des exemples sert à la lecture.

## Limites des réponses

La météo annonce uniquement le bulletin d’aujourd’hui ou de demain. Une demande
pour le matin ou l’après-midi ne produit pas de prévision par heure :
« demain matin » conduit au bulletin de demain.

La qualité de l’air annonce toujours le bulletin d’aujourd’hui, même si la demande
contient une autre date. La formulation historique « taux de CO2 » est un alias de
ce même service ; elle n’ajoute pas de mesure de CO2 aux données AQI ou PM 2.5.

Le Gourou et les anniversaires utilisent les réponses enregistrées existantes.
L’anniversaire reste générique même lorsqu’un prénom est reconnu.

Aucune commande anglaise n’est rétablie dans ce parcours. La conversation libre
de l’application Mac est une fonction distincte, avec son propre parcours audio.
Les réglages, programmations, boutons web et interactions RFID restent ceux des
services existants.

## Sources de référence

Le vocabulaire actif et ses correspondances avec les services figurent dans
[`nabd/nlu.py`](../nabd/nlu.py), y compris les listes `FIRST_NAMES` et
`ELIDED_NAMES`. Les intentions sont
`nabclockd/clock`, `nabclockd/sleep`, `nabweatherd/forecast`,
`nabairqualityd/forecast`, `nabtaichid/taichi`, `nab8balld/8ball`,
`nabsurprised/surprise`, `nabsurprised/carrot`, `nabsurprised/autopromo`
et `nabsurprised/birthday`.

La référence historique est le commit
`7ee4dec726e4caac400e1f7015057732e6a031c8` (`80d3633^`) :
`asr/nabaztag-grammar-fr.jsgf` décrit les variantes de reconnaissance et les
six fichiers `nab*/nlu/intent_fr.yaml` décrivent les intentions et les paramètres
`date` et `firstname`. Ils contiennent 77 exemples d’entraînement et une liste
de 315 prénoms distincts. Les services météo, air et anniversaire gardent les
limites décrites ci-dessus malgré ces paramètres.
