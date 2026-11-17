#!/bin/bash
# Build inside the target armhf system/chroot; never use the build host's uname.
set -euo pipefail
export LC_ALL=C
fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ $# -ge 1 && $# -le 3 ]] || fail 'Usage: install-drivers.sh KERNEL [CACHE [MIXER_CALIBRATION]]'
[[ $EUID -eq 0 ]] || fail 'Run as root inside the target system.'
. /etc/os-release
[[ ${VERSION_CODENAME:-} == trixie && $(dpkg --print-architecture) == armhf && -f /etc/rpi-issue ]] || fail 'Raspberry Pi OS Trixie armhf required.'
kernel=$1
[[ $kernel =~ ^6\.(12|18)\.[a-zA-Z0-9.+_-]+-rpi-v6$ ]] || fail 'Reviewed rpi-v6 kernel (6.12 or 6.18) required.'
headers=/lib/modules/$kernel/build
[[ -s $headers/Makefile && -s $headers/Module.symvers && -f /boot/firmware/config.txt ]] || fail 'Target kernel headers and boot configuration required.'
[[ $(make -s -C "$headers" ARCH=arm kernelrelease) == "$kernel" ]] || fail 'Header release differs from the explicit target kernel.'
cache=${2:-/var/cache/pynab-trixie}
calibration=${3:-}
if [[ -n $calibration ]]; then
  [[ -s $calibration && -f $calibration && ! -L $calibration ]] || fail 'Calibration must be a nonempty regular file.'
  [[ ! -e /var/lib/tagtagtag-sound/mixer.conf ]] || fail 'Existing calibration will not be overwritten.'
fi
here=$(cd -- "$(dirname -- "$0")" && pwd)
work=$(mktemp -d /var/tmp/pynab-drivers.XXXXXX)
trap 'rm -rf -- "$work"' EXIT
python3 "$here/fetch.py" "$cache" --prepare "$work"
for driver in ears sound cr14; do
  case $driver in
    ears) overlay=tagtagtag-ears ;;
    sound) overlay=tagtagtag-sound ;;
    cr14) overlay=cr14 ;;
  esac
  make -C "$headers" ARCH=arm M="$work/$driver" -j1 modules
  cpp -nostdinc -undef -D__DTS__ -x assembler-with-cpp -I "$headers/include" \
    "$work/$driver/$overlay-overlay.dts" |
    dtc -@ -I dts -O dtb -o "$work/$driver/$overlay.dtbo"
done
make -C "$work/sound" tagtagtag-mixerd test
modules=(ears/tagtagtag-ears.ko sound/snd-soc-wm8960.ko sound/snd-soc-max9759.ko sound/snd-soc-volume-gpio.ko cr14/cr14.ko)
names=(tagtagtag_ears snd_soc_wm8960 snd_soc_max9759 snd_soc_volume_gpio cr14)
for index in "${!modules[@]}"; do
  module=$work/${modules[$index]}
  readelf -h "$module" | grep -qE 'Machine:[[:space:]]+ARM([[:space:]]|$)' || fail "Not an ARM module: $module"
  readelf -h "$module" | grep -qE 'Class:[[:space:]]+ELF32' || fail "Not an ARM32 module: $module"
  [[ $(modinfo -F name "$module") == "${names[$index]}" ]] || fail "Unexpected module name: $module"
  [[ $(modinfo -F vermagic "$module") == "$kernel "* ]] || fail "Wrong kernel ABI: $module"
done
for overlay in ears/tagtagtag-ears sound/tagtagtag-sound cr14/cr14; do
  fdtget -p "$work/$overlay.dtbo" /__fixups__ >/dev/null || fail 'Invalid device-tree overlay.'
done
python3 - /boot/firmware/config.txt "$work/config.txt" <<'PY'
from pathlib import Path
import sys

source, target = map(Path, sys.argv[1:])
data = source.read_bytes()
block = b"""
# BEGIN PYNAB TRIXIE
[all]
gpu_mem=16
dtparam=audio=off
dtparam=i2c_arm=on
dtparam=i2s=on
dtoverlay=tagtagtag-sound
dtoverlay=tagtagtag-ears
dtoverlay=cr14
# END PYNAB TRIXIE
"""
if b"# BEGIN PYNAB TRIXIE" in data or b"# END PYNAB TRIXIE" in data:
    if data.count(block) != 1:
        raise SystemExit("Existing boot block differs; inspect before replacing it.")
else:
    data += block
target.write_bytes(data)
PY
destination=/lib/modules/$kernel/updates/nabaztag
install -d -m 755 "$destination" /boot/firmware/overlays /var/lib/tagtagtag-sound /var/lib/pynab-trixie
for module in "${modules[@]}"; do install -m 644 "$work/$module" "$destination/"; done
depmod -a "$kernel"
for name in "${names[@]}"; do
  [[ $(readlink -f "$(modinfo -k "$kernel" -n "$name")") == "$destination/"* ]] || fail "Installed module priority differs: $name"
done
for overlay in ears/tagtagtag-ears sound/tagtagtag-sound cr14/cr14; do
  install -m 644 "$work/$overlay.dtbo" /boot/firmware/overlays/
done
install -m 755 "$work/sound/tagtagtag-mixerd" /usr/local/sbin/tagtagtag-mixerd
install -m 644 "$work/sound/tagtagtag-mixerd.service" /usr/lib/systemd/system/
install -m 644 "$work/sound/mixer.conf.default" /var/lib/tagtagtag-sound/mixer.conf.default
if [[ -n $calibration ]]; then
  install -m 644 "$calibration" /var/lib/tagtagtag-sound/mixer.conf
elif [[ ! -e /var/lib/tagtagtag-sound/mixer.conf ]]; then
  install -m 644 "$work/sound/mixer.conf.default" /var/lib/tagtagtag-sound/mixer.conf
fi
printf 'i2c-dev\n' > /etc/modules-load.d/pynab-i2c.conf
[[ -e /boot/firmware/config.txt.before-pynab-trixie ]] || cp -p /boot/firmware/config.txt /boot/firmware/config.txt.before-pynab-trixie
install -m 644 "$work/config.txt" /boot/firmware/config.txt.pynab-new
mv /boot/firmware/config.txt.pynab-new /boot/firmware/config.txt
systemctl enable tagtagtag-mixerd.service
printf '%s\n' "$kernel" > /var/lib/pynab-trixie/drivers-kernel
printf 'Installed for %s; no module loaded, no service started, no reboot requested.\n' "$kernel"
