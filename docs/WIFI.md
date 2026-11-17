# Configuration Wi-Fi de l'image Trixie

Cette préparation cible le **Zero W original et la carte TagTagTag 2019**
(bouton GPIO 17). Elle n'est pas qualifiée pour les cartes Maker Faire 2018.

Au premier démarrage, ou si aucun réseau mémorisé n'est joignable, Comitup
crée le réseau **Nabaztag-123** (le nombre est propre à l'installation).
S'y connecter avec un téléphone ou un ordinateur, puis utiliser le portail
automatique ou ouvrir **http://10.41.0.1/** pour choisir son Wi-Fi 2,4 GHz et
saisir son mot de passe. Le réseau de configuration disparaît une fois la
connexion établie et l'interface Pynab redevient disponible.

Pour proposer ce portail même si le réseau habituel fonctionne, maintenir le
bouton de la tête en mettant le lapin sous tension. Le conserver appuyé
pendant le démarrage Linux, jusqu'aux **LED bleues**, puis le relâcher.
Le bouton est lu pendant deux secondes avant que `nabd` ne prenne le GPIO.
Le mode Wi-Fi ne modifie pas le rôle de l'appui long une fois Pynab démarré.

Les réseaux enregistrés sont conservés. Si personne ne rejoint le point
d'accès, Comitup reprend normalement ses essais de connexion après environ
trois minutes. Un appareil connecté au portail suspend ce retour automatique.
Le choix d'un réseau dans le portail reste géré par Comitup ; sélectionner un
réseau déjà connu peut remplacer ses paramètres par ceux que l'on saisit.

Le point d'accès est ouvert par défaut, comme celui de Pynab historique.
Une valeur `ap_password` déjà définie dans `/etc/comitup.conf` est préservée.
Le pays Wi-Fi doit être configuré pour le lieu d'utilisation avant le premier
démarrage ; ce script ne le force pas à la France.

## Installation dans une image fraîche

Installer depuis les dépôts Trixie `comitup`, `network-manager` et
`python3-rpi-lgpio` avec les autres prérequis de Pynab, puis exécuter :

```sh
sudo bash network/install.sh --no-start
```

Le script configure et active les unités pour le prochain démarrage. Il ne
redémarre ni NetworkManager, ni Comitup, ni le Wi-Fi courant. L'installation
APT des paquets doit également se faire sans démarrage de services lors de
la construction de l'image (`policy-rc.d`). Ne pas exécuter cette préparation
à l'aveugle sur une installation quotidienne dont l'accès réseau est unique.

Comitup arrête nginx pendant le portail puis le redémarre après connexion.
Son service et le contrôle du bouton utilisent Python système et les paquets
GPIO de Raspberry Pi OS. Le signal bleu utilise le venv Pynab lorsqu'il est
déjà installé ; il est facultatif pendant la préparation initiale. Le contrôle
LED est ordonné après `nabboot` et avant `nabd`, sans animation concurrente.

L'API officielle de Comitup propose uniquement une suppression du réseau
courant pour demander le portail (`delete_connection`). Nous n'utilisons ni
cette API ni la réinitialisation d'usine. Un petit lanceur modifie seulement
son indicateur de démarrage pour offrir HOTSPOT avant les réseaux mémorisés.
Il ne change ni les sources installées ni les profils NetworkManager.
Cette adaptation a été vérifiée dans les sources des versions 1.43 et 1.47 ;
elle devra être revue si la machine d'états de Comitup change. Une version
hors de la plage 1.43–1.47 ou une API absente conserve le démarrage Comitup
normal et produit un avertissement dans le journal.

Sources : [Comitup](https://davesteele.github.io/comitup/),
[machine d'états 1.43](https://github.com/davesteele/comitup/blob/d205d680e295129ebe6e2ccc6ff790ca63602ea9/comitup/states.py),
[configuration](https://github.com/davesteele/comitup/blob/main/doc/comitup-conf.5.md).

## Vérification

```sh
python3 -m unittest network.tests.test_wifi
bash -n network/install.sh
```

Avant diffusion : démarrer une SD vierge, joindre le portail, configurer un
réseau, redémarrer normalement, puis redémarrer avec le bouton. Vérifier que
le portail forcé fonctionne et que les réseaux connus restent présents.
Tester aussi le retour après trois minutes sans client et après un mot de
passe erroné. Aucun de ces essais physiques n'est validé par les tests sans
matériel.
