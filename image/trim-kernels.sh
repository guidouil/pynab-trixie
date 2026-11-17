#!/bin/bash
set -euo pipefail
export LC_ALL=C
fail() { printf '%s\n' "$*" >&2; exit 1; }
kernel_candidates() {
  awk '$1 == "ii" && $2 ~ /^linux-(base|headers|image)-(.+-)?rpi-(v7l?|v8|2712)(:armhf|:arm64)?$/ { print $2 }'
}
validate_removals() {
  awk '
    FILENAME == ARGV[1] {
      package = $1; sub(/:armhf$/, "", package)
      allowed[package] = 1; next
    }
    $1 == "Remv" {
      package = $2; sub(/:armhf$/, "", package)
      if (!(package in allowed)) {
        print "Refusing unexpected removal: " $2 > "/dev/stderr"
        bad = 1
      }
    }
    $1 == "Inst" {
      print "Refusing unexpected installation: " $2 > "/dev/stderr"
      bad = 1
    }
    END { exit bad }
  ' "$1" "$2"
}
main() {
  [[ $EUID -eq 0 && $# == 1 ]] || fail 'Usage: sudo bash image/trim-kernels.sh KERNEL'
  [[ $(uname -s) == Linux && $(uname -m) == armv6l ]] || fail 'Native Linux ARMv6 required.'
  . /etc/os-release
  [[ ${VERSION_CODENAME:-} == trixie && ${VERSION_ID:-} == 13 && -f /etc/rpi-issue ]] || fail 'Raspberry Pi OS Trixie required.'
  [[ $(dpkg --print-architecture) == armhf ]] || fail 'Native armhf required.'
  local kernel=$1 package status audit boot_image
  [[ $kernel =~ ^6\.(12|18)\.[a-zA-Z0-9.+_-]+-rpi-v6$ ]] || fail 'Explicit reviewed rpi-v6 kernel required.'
  mountpoint -q /boot/firmware || fail 'Boot partition is not mounted.'
  for package in linux-image-rpi-v6 linux-headers-rpi-v6 "linux-image-$kernel"; do
    [[ $(dpkg-query -W -f='${Status}' "$package") == 'install ok installed' ]] || fail "Missing installed v6 package: $package"
  done
  [[ -s /lib/modules/$kernel/build/Module.symvers ]] || fail 'Matching v6 headers required.'
  cmp -s "/boot/vmlinuz-$kernel" /boot/firmware/kernel.img || fail 'The boot image differs from the target v6 kernel.'
  cmp -s "/boot/initrd.img-$kernel" /boot/firmware/initramfs || fail 'The boot initramfs differs from the target v6 kernel.'
  audit=$(dpkg --audit)
  [[ -z $audit ]] || fail "Finish the current APT operation first: $audit"
  work=$(mktemp -d /var/tmp/pynab-kernel-trim.XXXXXX)
  trap 'rm -rf -- "$work"' EXIT
  status=$(dpkg-query -W -f='${db:Status-Abbrev}\t${binary:Package}\n')
  local -a candidates
  mapfile -t candidates < <(kernel_candidates <<< "$status")
  if (( ${#candidates[@]} > 0 )); then
    printf '%s\n' "${candidates[@]}" > "$work/candidates"
    apt-get -s -o APT::Get::AutomaticRemove=false remove "${candidates[@]}" > "$work/plan"
    cat "$work/plan"
    validate_removals "$work/candidates" "$work/plan" || fail 'APT removal plan requires review.'
  fi
  apt-mark manual linux-image-rpi-v6 linux-headers-rpi-v6
  if (( ${#candidates[@]} > 0 )); then
    DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=120 -o APT::Get::AutomaticRemove=false remove -y "${candidates[@]}"
  fi
  audit=$(dpkg --audit)
  [[ -z $audit ]] || fail "dpkg needs attention after removal: $audit"
  for package in linux-image-rpi-v6 linux-headers-rpi-v6 "linux-image-$kernel"; do
    [[ $(dpkg-query -W -f='${Status}' "$package") == 'install ok installed' ]] || fail "Missing v6 package after removal: $package"
  done
  status=$(dpkg-query -W -f='${db:Status-Abbrev}\t${binary:Package}\n')
  [[ -z $(kernel_candidates <<< "$status") ]] || fail 'Non-v6 kernel packages remain.'
  [[ -z $(awk '$1 == "ii" && $2 ~ /^linux-image-/ && $2 !~ /^linux-image-(.+-)?rpi-v6(:armhf)?$/ { print $2 }' <<< "$status") ]] || fail 'An unreviewed kernel image remains; inspect installed packages.'
  cmp -s "/boot/vmlinuz-$kernel" /boot/firmware/kernel.img || fail 'Inspect the v6 boot image after removal.'
  cmp -s "/boot/initrd.img-$kernel" /boot/firmware/initramfs || fail 'Inspect the v6 boot initramfs after removal.'
  [[ -s /lib/modules/$kernel/build/Module.symvers ]] || fail 'Matching v6 headers disappeared.'
  for boot_image in kernel7.img kernel7l.img kernel8.img kernel_2712.img initramfs7 initramfs7l initramfs8 initramfs_2712; do
    [[ ! -e /boot/firmware/$boot_image ]] || fail "An unused boot image remains; inspect its package ownership: $boot_image"
  done
  [[ -s /boot/firmware/bcm2708-rpi-zero-w.dtb && -s /boot/firmware/overlays/vc4-kms-v3d.dtbo ]] || fail 'Missing Zero W boot device tree.'
  printf 'Only reviewed non-v6 kernel families removed; v6 target %s preserved. No autoremove.\n' "$kernel"
}
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
