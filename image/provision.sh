#!/bin/bash
# Fresh-card provisioning only; does not clone a user's existing installation.
set -euo pipefail
export LC_ALL=C
fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 && $# -ge 1 && $# -le 2 ]] || fail 'Usage: sudo bash image/provision.sh drivers|pynab [MIXER_CALIBRATION]'
phase=$1
[[ $phase == drivers || $phase == pynab ]] || fail 'Expected drivers or pynab.'
[[ $phase == drivers || $# == 1 ]] || fail 'Calibration is accepted only in the drivers phase.'
. /etc/os-release
[[ ${VERSION_CODENAME:-} == trixie && ${VERSION_ID:-} == 13 && -f /etc/rpi-issue ]] || fail 'Raspberry Pi OS Trixie required.'
[[ $(dpkg --print-architecture) == armhf && $(uname -m) == armv6l ]] || fail 'Original Zero W ARMv6 required.'
model=$(tr -d '\0' < /proc/device-tree/model)
[[ $model == 'Raspberry Pi Zero W Rev '* ]] || fail 'Only original Raspberry Pi Zero W is qualified.'
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
[[ $root == /opt/pynab ]] || fail 'Place this checkout under /opt/pynab first.'
owner=$(stat -c '%U' "$root")
[[ $(stat -c '%u' "$root") != 0 && $owner != UNKNOWN ]] || fail 'The checkout must belong to a normal sudo-enabled user.'
[[ $(sudo -H -u "$owner" git -C "$root" remote get-url origin) == https://github.com/guidouil/pynab-trixie.git ]] || fail 'Expected our HTTPS distribution remote.'
[[ $(sudo -H -u "$owner" git -C "$root" branch --show-current) == trixie ]] || fail 'Expected the trixie distribution branch.'
[[ -z $(sudo -H -u "$owner" git -C "$root" status --porcelain --untracked-files=all) ]] || fail 'Source checkout has local changes; inspect before provisioning.'
[[ ! -e /var/lib/pynab-trixie/provisioned && ! -d $root/venv ]] || fail 'Fresh installation required; existing Pynab will not be replaced.'
cd -- "$root"
if [[ $phase == drivers ]]; then
  [[ ! -e /usr/sbin/policy-rc.d ]] || fail 'Existing policy-rc.d requires manual review.'
  cleanup() { rm -f /usr/sbin/policy-rc.d; }
  trap cleanup EXIT
  printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
  chmod 755 /usr/sbin/policy-rc.d
  apt-get update
  apt-get install -y --no-install-recommends build-essential device-tree-compiler linux-image-rpi-v6 linux-headers-rpi-v6 git python3 python3-venv python3-dev python3-rpi-lgpio python3-lgpio postgresql libpq5 gettext nginx libmpg123-dev libasound2-dev libmagic1t64 alsa-utils xz-utils avahi-daemon curl mpg123 netcat-openbsd comitup network-manager
  cleanup
  trap - EXIT
  kernel_package=$(dpkg-query -W -f='${Depends}' linux-image-rpi-v6 | grep -oE 'linux-image-[0-9][^ ,()]+' | head -n 1)
  [[ -n $kernel_package ]] || fail 'Cannot determine installed boot kernel.'
  kernel=${kernel_package#linux-image-}
  args=("$kernel" /var/cache/pynab-trixie)
  [[ $# == 1 ]] || args+=("$2")
  bash image/install-drivers.sh "${args[@]}"
  bash image/trim-kernels.sh "$kernel"
  bash network/install.sh --no-start
  install -d -m 755 /etc/systemd/journald.conf.d
  printf '[Journal]\nStorage=persistent\nSystemMaxUse=32M\nRuntimeMaxUse=8M\n' > /etc/systemd/journald.conf.d/pynab-trixie.conf
  printf 'Drivers and Wi-Fi provisioning installed for %s. Reboot manually, then run the pynab phase.\n' "$kernel"
  exit
fi
[[ -s /var/lib/pynab-trixie/drivers-kernel ]] || fail 'Run the drivers phase first.'
[[ $(cat /var/lib/pynab-trixie/drivers-kernel) == "$(uname -r)" ]] || fail 'Reboot into the provisioned kernel first.'
[[ -c /dev/ear0 && -c /dev/ear1 && -c /dev/rfid0 ]] || fail 'Qualify ears and CR14 devices before installing Pynab.'
aplay -l | grep -q tagtagtagsound || fail 'Qualify TagTagTag audio before installing Pynab.'
systemctl start postgresql
[[ $(sudo -u postgres psql --dbname=postgres --tuples-only --no-align --command="SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='pynab') OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname='pynab')") == f ]] || fail 'A Pynab database or role already exists; no data will be replaced.'
sudo -H -u "$owner" bash install.sh
install -d -o "$owner" -g "$(stat -c '%G' "$root")" /var/cache/pynab-trixie/native-asr
sudo -H -u "$owner" bash install-native-asr.sh /var/cache/pynab-trixie/native-asr
sudo -H -u "$owner" venv/bin/python manage.py check
sudo -H -u "$owner" git rev-parse HEAD > /var/lib/pynab-trixie/source-commit
dpkg-query -W -f='${binary:Package}\t${Version}\n' > /var/lib/pynab-trixie/packages.tsv
sudo -H -u "$owner" venv/bin/pip freeze > /var/lib/pynab-trixie/python-packages.txt
cp image/sources.lock.json /var/lib/pynab-trixie/sources.lock.json
date -u '+%Y-%m-%dT%H:%M:%SZ' > /var/lib/pynab-trixie/provisioned
printf 'Fresh Pynab provisioned. Restart nabd when ready to enable native voice, then perform hardware qualification.\n'
