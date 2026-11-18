#!/bin/bash
set -euo pipefail

if (( EUID == 0 )); then
  echo "Lance ce script avec le compte utilisé par Nabaztag IA. Il demandera sudo." >&2
  exit 1
fi

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
target=/usr/local/lib/nabaztag-mac
for command in python3 aplay arecord amixer curl mpg123; do
  if ! command -v "$command" >/dev/null; then
    echo "Commande requise sur le Pi : $command" >&2
    exit 1
  fi
done

if [[ ! -r /opt/pynab/nabd/sounds/asr/listen.mp3 ]]; then
  echo "Le signal d'écoute de Pynab est introuvable dans /opt/pynab." >&2
  exit 1
fi

sudo -v
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import bridge_remote as bridge

with bridge.reserve():
    bridge.run_audio(
        ["aplay", "-q", "-D", bridge.PLAYBACK_DEVICE, "-t", "raw",
         "-f", "S16_LE", "-r", "24000", "-c", "2", "-s", "1", "/dev/zero"],
        timeout=5,
    )
bridge.volume()
PY

sudo alsactl store tagtagtagsound
sudo install -d -o root -g root -m 0755 "$target"
sudo install --backup=numbered -o root -g root -m 0644 alsa.conf "$target/"
sudo install --backup=numbered -o root -g root -m 0755 bridge_remote.py "$target/"
echo "Relais Nabaztag IA installé dans $target."
