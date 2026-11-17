# Pynab Trixie

Version communautaire de Pynab pour **Raspberry Pi Zero W original ARMv6**, carte
TagTagTag (WM8960) et lecteur RFID CR14, sous **Raspberry Pi OS Lite Trixie 32 bits**.

Cette branche `trixie` part de [AntorFr/pynab-ha](https://github.com/AntorFr/pynab-ha)
(`4fb37bd52abf2b40a46f3d43386a798d87d4381d`), lui-même issu de
[nabaztag2018/pynab](https://github.com/nabaztag2018/pynab).
Les pilotes restent issus des projets de Paul Guyot, avec leurs correctifs et
attributions conservés. Aucun dépôt séparé n'est nécessaire pour chaque service.

**Préversion en préparation : aucune image stable à télécharger pour le moment.**
Le son, les oreilles, les LED, le bouton, les annonces natives et la conversation
Mac ont fonctionné sur le lapin de référence. Le nouveau parcours Wi-Fi, les
mises à jour web et une installation sur SD vierge doivent encore être qualifiés
sur le matériel. La lecture réelle d'un badge CR14 et l'endurance de 24 heures
restent à valider. Les autres Pi et le lecteur NFC ST25R391x ne sont pas qualifiés.

## Installer

Suivre [la préparation d'une SD vierge](docs/DISTRIBUTION.md). La recette installe
les pilotes épinglés avant Pynab et crée une base PostgreSQL neuve. Elle ne copie
ni sauvegarde personnelle, ni clés SSH, ni identifiants d'un autre lapin.
Le script historique `setup` n'est plus le parcours d'installation de ce fork.

## Configurer le Wi-Fi

Le lapin crée un point d'accès lorsqu'aucun réseau mémorisé n'est disponible.
Le bouton maintenu au démarrage ouvre aussi ce parcours, sans effacer les réseaux
mémorisés. Se connecter au réseau `Nabaztag-…` depuis un téléphone puis utiliser
le portail pour choisir son Wi-Fi. [Procédure et limites](docs/WIFI.md).

## Commandes vocales françaises

Maintenir le bouton, attendre le bip, parler puis relâcher : « Quelle heure
est-il ? », « La météo », « La météo demain », « Comment vas-tu ? »,
« T’en penses quoi Nabaztag ? », « Fais-moi rire » ou « Que sais-tu faire ? ».
Un vocabulaire court de 28 formulations couvre dix actions : heure, sommeil,
météo, qualité de l’air, taï-chi, Gourou, surprise/humeur, carotte, présentation
et anniversaire. Utiliser une seule formulation de la liste par appui.
PocketSphinx fonctionne localement, sans écoute permanente ; la météo nécessite
son accès Internet habituel. La capture dure au plus 15 secondes.
[Formulations prises en charge et limites](docs/VOICE_COMMANDS.md).
[Installation et qualification du moteur](docs/ZERO_W_TRIXIE.md).

La conversation libre et la radio depuis le Mac utilisent l'application séparée
[Nabaztag IA](https://github.com/guidouil/nabaztag_IA) et les accès de chaque
utilisateur. Snips/Kaldi et Home Assistant ne sont pas activés par
cette préparation Zero W.

## Mettre à jour

L'interface web et `bash upgrade.sh` suivent uniquement
`https://github.com/guidouil/pynab-trixie.git`, branche `trixie`.
Les changements locaux, fichiers non suivis et historiques divergents bloquent
la mise à jour. Une sauvegarde PostgreSQL privée précède l'installation.
[Déroulement et récupération](docs/UPDATES.md).
Le noyau et les pilotes ne sont pas mis à jour par ce bouton : ils doivent
rester un ensemble qualifié selon la procédure de distribution.

## Développer et contribuer

Python 3.13, Django 5.2 LTS ; dépendances de développement dans `requirements.txt`.
La configuration web désactive le mode debug par défaut et génère une clé de
signature propre à chaque installation, ignorée par Git. L'interface reste
prévue pour le réseau local de confiance. [Protocole Pynab](PROTOCOL.md).
Les instructions historiques du portage sont conservées dans
[ZERO_W_TRIXIE.md](docs/ZERO_W_TRIXIE.md).

Pynab conserve sa [licence](LICENSE). Les sources et notices des dépendances,
pilotes, sons et modèles sont conservées ; consulter leur provenance avant
redistribution. [Contribuer](CONTRIBUTING.md).
