# Historique du portage Zero W / Trixie 32 bits

Base : `AntorFr/pynab-ha`, commit
`4fb37bd52abf2b40a46f3d43386a798d87d4381d`.
Préparation initiale : `codex/zero-w-trixie`. Le fork maintenu est désormais
`guidouil/pynab-trixie`, branche `trixie`. Pour une installation neuve et les
mises à jour, suivre [DISTRIBUTION.md](DISTRIBUTION.md) et le README actuel.

Cet essai exclut Snips/Kaldi et les deux démons Home Assistant. Le port TCP
`127.0.0.1:10543`, le bouton, les sons natifs, les messages et chorégraphies
restent les interfaces utilisées par le relais Mac. La conversation libre reste
sur le Mac. Les pages Home Assistant du fork existent encore, mais leurs services
et dépendances optionnelles ne sont pas installés.

## Avant installation

- Utiliser uniquement la seconde SD, après sauvegarde complète de l'originale.
- Qualifier d'abord les pilotes avec le noyau installé : son, oreilles, LED,
  bouton, capture et lecture. Ce lapin utilise le lecteur **CR14**.
- Ne pas utiliser `setup pi-zero` : ce script historique supprime l'installation
  existante et récupère des pilotes depuis des branches distantes.
- Ne pas lancer la mise à jour web ni `upgrade.sh` sur cet essai : leurs mises à
  jour Git et pilotes ne sont pas épinglées à cette préparation.

Sur la SD Trixie 32 bits, les prérequis de compilation et fonctionnement sont :

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends build-essential device-tree-compiler linux-headers-rpi-v6 git python3 python3-venv python3-dev python3-rpi-lgpio python3-lgpio postgresql libpq5 gettext nginx libmpg123-dev libasound2-dev libmagic1t64 alsa-utils xz-utils avahi-daemon curl mpg123 netcat-openbsd
```

Les paquets GPIO doivent provenir de Raspberry Pi OS pour ARMv6. Ne pas installer
`RPi.GPIO` dans le même environnement que `rpi-lgpio`. Le venv expose les paquets
Python système ; Psycopg utilise `libpq5`, sans wheel binaire ARM64/ARMv7.

Les annonces natives gardent leurs MP3 d'origine. Le petit binding
`nabd/mpg123.py` utilise la bibliothèque système **libmpg123 1.32 ou plus
récente**, avec ses interfaces `decode_frame64` et `length64`. Il remplace le
paquet Python `mpg123==0.4`, incompatible avec les symboles time64 de Trixie
32 bits. Chaque lecteur libère son décodeur à la fin, même en cas d'erreur.

Placer cette branche préparée dans `/opt/pynab`, avec un propriétaire utilisateur
normal autorisé à utiliser sudo. Après qualification des pilotes, lancer depuis
ce répertoire, **sans sudo devant l'installateur** :

```sh
bash install.sh
venv/bin/python manage.py check
venv/bin/python -c 'import RPi.GPIO, lgpio, alsaaudio, rpi_ws281x, psycopg; print("Imports matériels et PostgreSQL OK")'
```

L'installation n'installe que `requirements-runtime.txt`. Elle exige un seul
cluster PostgreSQL `main`, garde une copie initiale de `pg_hba.conf`, et ajoute
uniquement la connexion locale du rôle `pynab` à la base `pynab`. Elle ne restaure
aucune sauvegarde : la restauration PostgreSQL se fait séparément, puis les
migrations sont rejouées avant les essais fonctionnels.

## Commandes françaises sans Mac

Le remplacement facultatif de Snips/Kaldi utilise PocketSphinx 5.1.1 et un
modèle français 16 kHz. Depuis `/opt/pynab`, en utilisateur propriétaire du checkout Pynab :

```sh
bash install-native-asr.sh
sudo systemctl restart nabd.service
```

Les téléchargements sont épinglés par SHA-256. Un dossier de téléchargements
préexistants peut être fourni en argument. Le modèle reste hors Git sous
`nabd/asr-fr/`, avec ses licences. Les sons et le calibrage ALSA restent ceux
de l'installation. Aucun serveur ni écoute permanente n'est ajouté.

Maintenir le bouton, attendre le bip, dire « Quelle heure est-il ? », « La
météo », « La météo demain », « Comment vas-tu ? » ou
« T’en penses quoi Nabaztag ? », puis relâcher. La capture
est limitée à 15 secondes. Le clic court du relais Mac reste disponible.
Le microphone est configuré avant le bip ; capture et lecture utilisent des
futures distinctes. Les échantillons du bip sont ignorés, puis la parole est
acceptée jusqu'au relâchement.
Les dix intentions historiques françaises sont rétablies : heure, sommeil,
météo, qualité de l'air, taï-chi, Gourou, surprise/humeur, carotte, présentation
et anniversaire. Les formulations et les limites des services sont décrites dans
[VOICE_COMMANDS.md](VOICE_COMMANDS.md). La reconnaissance fonctionne sans Internet,
mais la météo et la qualité de l'air gardent leur accès Internet habituel.
Les prévisions météo restent limitées à aujourd'hui ou demain, sans détail par
heure ; la qualité de l'air annonce toujours aujourd'hui. L'anniversaire accepte
les prénoms historiques, mais sa réponse reste générique. Les commandes anglaises
et la conversation libre de l'application Mac sont hors de ce parcours natif.

La grammaire est confirmée par un détecteur acoustique de mots de commande :
une grammaire seule forcerait des phrases hors sujet vers une commande.
La précision doit être validée avec une voix humaine et le micro du lapin.

## Personnalisation conservée

Le lapin source exécute Pynab
`9c5dc139038eb2fea1189232d9c56ad8e7c48ebd` avec deux appels
`pulse(Led.BOTTOM, (0, 0, 0))` : après rechargement de configuration et au retour
au repos. Cette personnalisation est reprise ici. Le déplacement des oreilles
au retour au repos reste cyan ; les alertes réseau rouge et orange restent
actives.

## Vérification sans matériel

```sh
bash -n install.sh
python -m unittest nabd.tests.zero_w_idle_test
python -m unittest nabd.tests.mpg123_test
python -m unittest nabd.tests.native_asr_test nabd.tests.native_voice_test nabd.tests.native_capture_test
```

Le test isolé nécessite Python 3.13, Django, python-dateutil et lockfile. Il
contrôle l'extinction au repos et le maintien des alertes réseau, sans base de
données et sans mouvement réel. Il ne qualifie ni les modules du noyau ni le
son, le RFID, les performances ou la stabilité de la nouvelle installation.
Les tests MP3 n'utilisent que la bibliothèque standard : ils contrôlent les
types ABI 64 bits, la reprise du flux après manque de données et la libération
des ressources après erreur. Le décodage de vrais MP3 et l'audition des annonces
doivent aussi être vérifiés sur le Pi.
