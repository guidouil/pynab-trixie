# Mises à jour de Pynab Trixie

Le bouton **Mise à jour** de l'interface web et `bash upgrade.sh` suivent
uniquement `origin/trixie`, depuis
`https://github.com/guidouil/pynab-trixie.git`. Cette branche est le canal de
distribution ; les développements non qualifiés doivent rester sur d'autres
branches.

Les services Pynab restent dans ce dépôt. Les pilotes audio, oreilles et CR14
sont des sources upstream épinglées accompagnées de patches dans `image/` ;
ils ne nécessitent pas de forks indépendants pour cette version. Le bouton
web ne met à jour ni noyau, ni pilotes.

## Avant une mise à jour

Le checkout doit être sur `trixie`, suivre `origin/trixie` et être propre :
aucun fichier modifié, ajouté à l'index ou non suivi. Les commits locaux,
historiques divergents, autres branches et autres adresses de dépôt sont
refusés, y compris si la requête est envoyée directement sans le bouton web.
Le service web Pynab existant tourne sous root. Une mise à jour lancée depuis
cette interface conserve ce contexte pour l'orchestration et l'installateur ;
les commandes Git et les opérations du venv restent exécutées par le
propriétaire du checkout. Le compte `pi` n'a donc pas besoin de sudo sans mot
de passe pour utiliser le bouton web. Aucune règle sudoers ni autorisation
utilisateur n'est modifiée.

En ligne de commande, `bash upgrade.sh` exige le sudo non interactif requis
par l'installateur (`sudo -n true`). À défaut, lancer `sudo bash upgrade.sh`
et saisir son mot de passe dans le terminal. Le contrôle précède toute
modification du code ou des services.
Les fichiers ignorés par Git, notamment le venv et les modèles téléchargés,
restent en place.

Une ancienne installation avec des correctifs non commités doit d'abord être
sauvegardée et rapprochée de notre version. Changer seulement son adresse
`origin` ne constitue pas une migration. La procédure privée sous `Migration/`
du projet Mac n'est pas un installateur générique.

## Déroulement

1. Un verrou dans `/var/lib/pynab/update/` sérialise les mises à jour.
2. Le dépôt est vérifié et seule la branche distante `trixie` est récupérée,
   avec un délai réseau borné. Aucun service n'est arrêté à cette étape.
3. `pg_dump` crée une sauvegarde cohérente de la base `pynab`, privée au
   propriétaire du checkout, sous `backups/`. Statuts, journal et sauvegardes
   restent lisibles par ce propriétaire même si le processus tourne sous
   root, sans accès pour les autres utilisateurs. Un échec bloque la suite.
4. Git applique uniquement une avance rapide vers le commit vérifié, sans
   réinitialisation forcée ni fusion des modifications locales.
5. Les services Pynab actifs sont arrêtés, sauf le serveur web et `nabboot`.
   Le runtime et les migrations sont installés, puis seules les unités
   initialement actives sont relancées. Le serveur web redémarre en dernier.

`nabboot` n'est jamais rejoué par la mise à jour : son animation utilise les
mêmes ressources LED que `nabd`. La configuration réseau reste active.

## En cas d'échec

L'interface conserve l'erreur. Le journal est
`/var/lib/pynab/update/upgrade.log` ; `status.json` conserve le commit précédent
et le chemin d'une sauvegarde de base terminée, si elle existe. Une coupure
du processus est signalée comme interruption lors du prochain contrôle.

Après un échec d'installation, des services peuvent rester arrêtés. Ne pas
considérer le nouveau commit Git comme une installation réussie. Aucune
restauration automatique de la base n'est tentée : restaurer du code ancien
avec un schéma déjà migré peut être incorrect. Examiner le journal et
choisir explicitement la réparation ou la restauration correspondante.

Les sauvegardes ne sont pas effacées automatiquement. Surveiller l'espace
libre et conserver une sauvegarde externe avant une maintenance importante.

## Vérification sans lapin

```sh
python -m unittest nabweb.tests.update_test
bash -n upgrade.sh
```

Ces tests utilisent des dépôts Git locaux et de faux services. Ils vérifient
les refus, l'avance rapide, les sauvegardes, les erreurs et les vues web. Ils
ne qualifient pas une mise à jour réelle sur le Zero W ni une migration de
base avec les données d'un utilisateur.
