# Distribution Trixie : préparation de la première image

Cette branche conserve Pynab Python/Django/PostgreSQL et ALSA. La seule cible
qualifiée dans le projet est le **Raspberry Pi Zero W original ARMv6**, carte
TagTagTag WM8960 et lecteur CR14. Le Zero 2 W, les cartes Maker Faire 2018 et
le lecteur NFC ST25R391x ne sont pas couverts par cette recette.

Les scripts ci-dessous préparent une **SD neuve**. Ils ne constituent pas encore
une image publiée ni un constructeur d'image hors ligne complet. Aucun script
ne flashe de support, ne copie de sauvegarde privée ou ne redémarre le lapin.

## Sources et base

`image/sources.lock.json` fixe l'image officielle Raspberry Pi OS Lite Trixie
armhf du **6 octobre 2026**, son SHA-256, les trois révisions de pilotes et
les SHA-256 des archives et patches. L'empreinte de l'image a été comparée au
fichier `.sha256` publié par downloads.raspberrypi.com le 17 novembre 2026.
La base officielle est distincte de la SD personnelle utilisée pendant les
essais ; sa provenance ne prétend pas identifier cette ancienne installation.

Les pilotes viennent de `pguyot/tagtagtag-ears`, `pguyot/wm8960` (branche
`tagtagtag-sound`) et `pguyot/cr14`. Les patches de modernisation dérivent de
`guilhem/pynab@2624411f8f81fc4e17aee3b46fd38594021a49e5/image/patches`, avec
les adaptations de timer de notre migration pour Linux 6.12/6.18. Les licences
des sources sont conservées dans les archives extraites. La recette ne reprend
pas la réécriture Rust/Go, U-Boot ou RAUC de ce fork.

Le téléchargement vérifié se fait avec Python 3.13 ou plus récent :

```sh
python3 image/fetch.py /chemin/cache --base
```

Sans `--base`, seules les petites archives pilotes sont récupérées. Un cache
corrompu est refusé ; il faut l'inspecter ou le déplacer avant de recommencer.
L'option `--prepare /chemin/vide` extrait les sources de manière filtrée,
vérifie les patches puis les applique.

Les paquets APT ne sont pas encore issus d'un snapshot figé et les dépendances
Python transitives ne sont pas toutes verrouillées. Le manifeste installé
enregistre leurs versions effectives ; cette recette ne garantit donc pas une
reconstruction identique octet pour octet.

## Préparer une SD neuve sur le lapin

1. Flasher la base vérifiée, avec Raspberry Pi Imager ou un outil équivalent.
   Créer son propre compte administrateur et son accès initial, et choisir
   explicitement le **pays Wi-Fi du lieu d’utilisation dans Imager**. Le chemin
   Imager complet et le premier démarrage public restent à qualifier.
2. Placer notre dépôt, branche `trixie`, sous `/opt/pynab`, propriété de ce
   compte. Le remote `origin` doit être
   `https://github.com/guidouil/pynab-trixie.git`, l'arbre Git doit être propre.
   Depuis le compte propriétaire, le clone suivant établit aussi le suivi
   `origin/trixie` :

   ```sh
   sudo install -d -o "$(id -un)" -g "$(id -gn)" /opt/pynab
   git clone --branch trixie https://github.com/guidouil/pynab-trixie.git /opt/pynab
   cd /opt/pynab
   git rev-parse --abbrev-ref '@{upstream}'
   git rev-parse HEAD
   ```

   Le premier résultat doit être `origin/trixie`. Pour un checkout existant,
   vérifier ce suivi en plus de son nom de branche et de son remote.
3. Depuis ce répertoire, installer les prérequis, les pilotes et la
   configuration Wi-Fi pour le prochain démarrage :

   ```sh
   sudo bash image/provision.sh drivers
   ```

   Cette phase empêche temporairement les démarrages automatiques des services
   par APT, puis installe les unités réseau avec `network/install.sh --no-start`.
   Le noyau est sélectionné explicitement depuis le paquet installé
   `linux-image-rpi-v6`, jamais depuis le `uname` d'un éventuel hôte de build.
   Après validation des pilotes pour ce noyau, la recette retire les seules
   familles de paquets v7/v7l/v8/2712 déjà installées. Elle simule d'abord APT
   et refuse toute suppression hors liste ou toute installation supplémentaire.
   Les paquets v6 et leurs en-têtes restent explicitement installés ; aucun
   `autoremove` ni changement des architectures APT n'est effectué. Les images
   du noyau et de l'initramfs de démarrage doivent correspondre au v6 choisi.
4. Redémarrer manuellement puis vérifier son, micro, oreilles et CR14. Installer
   ensuite Pynab et les ressources vocales françaises depuis le compte propriétaire :

   ```sh
   sudo bash image/provision.sh pynab
   ```

   La phase refuse une base ou un rôle PostgreSQL Pynab préexistants, ainsi
   qu'une installation déjà préparée. Elle n'importe aucune base personnelle.
   Les modèles ont été installés après le premier démarrage de `nabd` :

   ```sh
   sudo systemctl restart nabd.service
   sudo tail -n 50 /var/log/nabd.log
   ```

   Attendre `Native French voice ready` avant les essais au bouton ; le
   premier chargement peut prendre jusqu’à 120 secondes sur le Zero W.

Les métadonnées sont écrites dans `/var/lib/pynab-trixie/` : commit Pynab,
noyau des pilotes, manifeste des sources, paquets système et Python. Le journal
système persiste entre les démarrages, avec une limite de 32 Mio sur disque
et 8 Mio en mémoire, pour pouvoir examiner un redémarrage ou une erreur OOM.

Les téléchargements vocaux vérifiés peuvent être préchargés dans
`/var/cache/pynab-trixie/native-asr/`. La phase `pynab` réutilise ce cache,
contrôle de nouveau ses SHA-256 et télécharge seulement les fichiers absents.

## Calibrage

La recette installe le fichier `mixer.conf.default` provenant de la révision
WM8960 vérifiée, uniquement si aucun calibrage n'existe. Ses tests du mixeur
doivent passer lors de la compilation ; ils ne valident pas le niveau sonore
ou la qualité du micro sur chaque lapin.

Pour importer le **propre** calibrage d'un propriétaire sur une SD neuve :

```sh
sudo bash image/provision.sh drivers /chemin/prive/mixer.conf
```

Le fichier doit être régulier et non vide ; un calibrage existant n'est jamais
écrasé. Ne pas embarquer le calibrage, le volume logiciel ou l'état ALSA d'un
autre lapin dans l'image publique.

## Construction dans un environnement Linux

`image/install-drivers.sh KERNEL [CACHE [MIXER_CALIBRATION]]` peut être exécuté
en root **dans le système cible armhf Trixie**, natif ou chroot. Les en-têtes
doivent correspondre exactement à `KERNEL`. La compilation utilise un seul
job, contrôle noms et ABI des cinq modules, compile les trois overlays et
exécute les assertions du mixeur avant installation. Aucun module n'est chargé
et aucun service n'est lancé.
Le nettoyage `image/trim-kernels.sh KERNEL` accepte également ce chroot cible armhf.

Une VM Linux ou un environnement Docker privilégié avec les montages requis
peut héberger un futur constructeur ; le Mac seul ne fournit pas le chroot
Linux. La recette native `provision.sh` exige volontairement le vrai Zero W.
Un constructeur hors ligne devra séparer l'initialisation PostgreSQL, les
migrations et le premier démarrage matériel ; il ne doit pas simplement appeler
cette recette native dans un chroot.

Les pilotes ne sont pas encore DKMS. Une livraison lie **noyau et pilotes**.
Après changement du noyau, reconstruire pour sa version exacte et qualifier
le démarrage avant de l'annoncer supporté. La mise à jour Git Pynab ne met à
jour ni le noyau ni les pilotes ; ne pas utiliser les anciens wrappers flottants.

## Avant une image partageable

Construire sur une base officielle vierge, avec une base PostgreSQL neuve.
Ne pas nettoyer puis publier une copie de la SD utilisée quotidiennement.
Au premier démarrage, les clés hôte SSH, l'identité réseau et les secrets
doivent appartenir au nouvel appareil. En particulier, supprimer du squelette
d'image tout fichier `.pynab-secret-key` créé pendant la préparation : la
configuration Django génère ensuite une nouvelle clé persistante.

Exclure clés privées, `authorized_keys` personnels, profils Wi-Fi, mots de passe,
jetons, dumps PostgreSQL, modèles expérimentaux, historiques, journaux et
enregistrements. Préserver les sons natifs et les notices des modèles français.
L'accès Mac se configure avec les identifiants de chaque propriétaire.

Une première alpha nécessite encore un flash indépendant et la vérification
du portail Wi-Fi automatique, du bouton de configuration au démarrage, de la
connexion SSH propre, du calibrage, des commandes humaines, du relais Mac et
des redémarrages. La lecture d'un badge CR14 réel et une endurance complète
de 24 heures après la dernière correction restent nécessaires avant stable.

Vérification sans matériel :

```sh
python3 -m unittest discover -s image -p test_recipe.py
bash -n image/install-drivers.sh image/provision.sh
```
