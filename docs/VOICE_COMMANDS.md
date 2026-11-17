# Commandes vocales natives

Maintenir le bouton de la tête, attendre le bip, parler puis relâcher. La capture
s’arrête après 15 secondes. La reconnaissance est locale et uniquement en français,
quelle que soit la langue choisie pour les sons du lapin. La météo et la qualité
de l’air gardent leur accès Internet habituel.

## Les 28 formulations

Le vocabulaire court couvre dix actions. Utiliser une seule des formulations
ci-dessous par appui. Les synonymes, les phrases libres et les ajouts de prénoms
ne sont pas reconnus automatiquement. La ponctuation sert à la lecture.

| Action | Formulations prises en charge |
| --- | --- |
| Heure | « Quelle heure est-il ? », « Donne-moi l’heure » |
| Météo | « Météo », « La météo », « Donne-moi la météo », « Quel temps fait-il ? », « La météo aujourd’hui », « La météo demain » |
| Surprise et humeur | « Comment vas-tu ? », « Comment ça va ? », « Donne-moi ton humeur », « Fais-moi rire », « Guili guili » |
| Gourou | « Dis lapin », « T’en penses quoi Nabaztag ? », « Tu en penses quoi Nabaztag ? » |
| Qualité de l’air | « Qualité de l’air » |
| Taï-chi | « Tai-chi », « C’est l’heure du tai-chi » |
| Sommeil | « Dodo », « Au lit », « Dormir » |
| Carotte | « Carotte », « Tu veux une carotte » |
| Présentation | « Que sais-tu faire ? », « Tu sais faire quoi ? » |
| Anniversaire | « Anniversaire », « C’est mon anniversaire » |

Les longues variantes historiques, les prénoms d’anniversaire et les demandes
combinées ont été retirés du vocabulaire pour limiter le travail du décodeur sur
le Zero W. La précision et le délai doivent être vérifiés avec la voix de
l’utilisateur et le micro du lapin ; les essais synthétiques sur Mac ne les
garantissent pas.

## Délai mesuré

Sur le Zero W original de référence, deux prises réelles du micro (« Fais-moi
rire » et « Que sais-tu faire ») ont été décodées en environ 2,4 et 2,8 secondes,
modèle déjà chargé. Le délai varie avec la longueur, le bruit et la charge du Pi.
Les services météo et qualité de l’air ajoutent leur accès Internet habituel.

Le son d’acquisition de deux secondes et les respirations précédant une surprise
vocale ont été retirés pour répondre directement. Le bip de début est conservé.

## Limites des réponses

La météo annonce uniquement le bulletin d’aujourd’hui ou de demain, sans détail
par heure. La qualité de l’air annonce le bulletin d’aujourd’hui.

Le Gourou et les anniversaires utilisent les réponses enregistrées existantes.
L’anniversaire reste générique ; les prénoms ne font pas partie du vocabulaire.

La conversation libre utilise l’application distincte
[Nabaztag IA](https://github.com/guidouil/nabaztag_IA) sur le Mac. Les réglages,
programmations, boutons web et interactions RFID des services gardent leur
propre fonctionnement.

## Source de référence

La liste active et les intentions correspondantes figurent dans
[`nabd/nlu.py`](../nabd/nlu.py). Cette liste de commandes ne rétablit pas toutes
les variantes des anciens modèles Snips. Aucune commande anglaise n’est prévue
par ce parcours natif.
