# Commandes vocales natives

Maintenir le bouton de la tête, attendre le bip, parler puis relâcher. La capture
s’arrête après 15 secondes. La reconnaissance est locale et uniquement en français,
quelle que soit la langue choisie pour les sons du lapin. La météo garde son accès
Internet habituel.

Le vocabulaire est limité aux quatre familles ci-dessous. Ces formulations sont
prévues par `nabd/nlu.py` ; les synonymes et les demandes libres ne sont pas
automatiquement compris. La ponctuation ci-dessous sert à la lecture.

| Famille | Formulations prévues |
| --- | --- |
| Heure | « Quelle heure est-il ? », « Il est quelle heure ? », « Donne-moi l’heure », « Dis-moi l’heure » |
| Météo du jour | « La météo », « Donne-moi la météo », « Quelle est la météo ? », « Quel temps fait-il ? », « La météo aujourd’hui », « Quel temps fait-il aujourd’hui ? » |
| Météo du lendemain | « La météo demain », « Donne-moi la météo demain », « Quel temps fait-il demain ? » |
| Humeur | « Comment vas-tu ? », « Comment ça va ? », « Donne-moi ton humeur », « Comment te sens-tu ? » |
| Gourou | « T’en penses quoi Nabaztag ? », « Tu en penses quoi Nabaztag ? » |

Le Gourou répond avec ses réponses enregistrées. La conversation libre de
l’application Mac est une fonction distincte, avec son propre parcours audio.

## Commandes historiques encore absentes

Les anciens modèles Snips couvraient davantage de demandes. Les suivantes ne
figurent pas dans le vocabulaire natif actuel, même lorsque le service existe
encore dans Pynab :

| Demande | Exemples de formulations absentes |
| --- | --- |
| Qualité de l’air | « Qualité de l’air », « C’est pas un peu pollué aujourd’hui » |
| Taï-chi | « Taï-chi », « C’est l’heure du taï-chi » |
| Sommeil | « Dodo », « Au lit », « Dormir » |
| Autres surprises | « Fais-moi rire », « Guili guili », « Surprise », « Humeur » seul |
| Carotte | « Carotte », « Tu veux une carotte » |
| Présentation du lapin | « Que sais-tu faire » |
| Anniversaire | « C’est mon anniversaire » |
| Autres demandes météo | « Météo » seul, demandes de pluie ou de parapluie, prévisions pour le matin ou l’après-midi |
| Autres demandes d’heure | « Horloge », « Aurais-tu l’heure » |
| Autres appels du Gourou | « Dis lapin », « Dis gourou » |

Utiliser « La météo » plutôt que « Météo » seul. La reconnaissance peut parfois
rapprocher une phrase non prévue d’une phrase connue ; ce n’est pas une variante
prise en charge. Aucune commande anglaise n’est prévue.

Cette limite concerne la commande vocale : elle ne désactive pas les boutons de
l’interface web, les programmations ou les interactions RFID des services.
