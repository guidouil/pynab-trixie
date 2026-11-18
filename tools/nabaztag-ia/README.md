# Relais SSH pour Nabaztag IA

Ces fichiers permettent à [Nabaztag IA v0.14](https://github.com/guidouil/nabaztag_IA/releases/tag/v0.14)
d'utiliser le bouton, le microphone, la sortie audio, la radio et le volume
d'un lapin déjà opérationnel sous Pynab Trixie avec une carte TagTagTag.

Sur le Pi, depuis le dépôt Pynab, lancer cette commande avec le compte SSH
utilisé par l'application et capable d'utiliser `sudo`.

```sh
bash tools/nabaztag-ia/install.sh
```

Le script vérifie les outils audio, initialise silencieusement le volume
logiciel dédié et enregistre son état ALSA. Il installe `bridge_remote.py` et
`alsa.conf` ensemble dans `/usr/local/lib/nabaztag-mac/`. Un fichier remplacé
est sauvegardé à côté avec un suffixe numéroté. Si un outil manque sur une
installation manuelle, les paquets requis sont `python3`, `alsa-utils`,
`curl` et `mpg123`.

Le relais est facultatif. Configure la connexion SSH et vérifie l'empreinte
du lapin dans l'application en suivant
[le guide Nabaztag IA](https://github.com/guidouil/nabaztag_IA/blob/v0.14/DISTRIBUTION.md#connecter-son-lapin).
L'installateur utilise les accès en place. Clique sur **Vérifier**, puis sur
**Diagnostic → Tester la voix** dans l'application.

Sources issues de [Nabaztag IA v0.14, révision 953ebc1](https://github.com/guidouil/nabaztag_IA/tree/953ebc18ab5f2f75850fa43d7852a6929b245d88).
Le relais Python suit la mise en forme de Pynab Trixie.
