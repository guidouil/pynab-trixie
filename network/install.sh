#!/usr/bin/env bash
set -euo pipefail
umask 077

[[ $# -eq 0 || ( $# -eq 1 && $1 == --no-start ) ]] || { echo 'Usage: sudo bash network/install.sh [--no-start]' >&2; exit 1; }
[[ $EUID -eq 0 ]] || { echo 'Run this script with sudo.' >&2; exit 1; }
. /etc/os-release
[[ ${VERSION_CODENAME:-} == trixie ]] || { echo 'Raspberry Pi OS Trixie required.' >&2; exit 1; }
for package in comitup network-manager python3-rpi-lgpio; do
    [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null) == 'install ok installed' ]] || {
        echo "Install $package with apt before configuring Wi-Fi onboarding." >&2
        exit 1
    }
done
root_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
[[ $root_dir =~ ^[a-zA-Z0-9_./-]+$ ]] || { echo 'Use an installation path containing only letters, numbers, dot, slash, dash or underscore.' >&2; exit 1; }

python3 - "$root_dir" <<'PY'
from pathlib import Path
import re
import sys

root = sys.argv[1]
path = Path('/etc/comitup.conf')
text = path.read_text() if path.exists() else ''
values = {
    'ap_name': 'Nabaztag-<nnn>',
    'web_service': 'nginx.service',
    'service_name': 'Nabaztag',
    'external_callback': f'{root}/comitup-callback.sh',
    'primary_wifi_device': 'wlan0',
    'enable_appliance_mode': 'false',
    'enable_nuke': 'false',
}
for key, value in values.items():
    pattern = rf'^{re.escape(key)}\s*:.*$'
    if re.search(pattern, text, flags=re.MULTILINE):
        text = re.sub(pattern, f'{key}: {value}', text, flags=re.MULTILINE)
    else:
        text += f'\n{key}: {value}\n'
if path.exists() and not path.with_suffix('.conf.before-pynab').exists():
    path.with_suffix('.conf.before-pynab').write_bytes(path.read_bytes())
    path.with_suffix('.conf.before-pynab').chmod(0o600)
path.write_text(text)
path.chmod(0o600)
PY

install -d -m 0755 /etc/systemd/system/comitup.service.d /etc/systemd/system/nabd.service.d
sed "s|/opt/pynab|$root_dir|g" "$root_dir/network/systemd/pynab-wifi-setup.service" > /etc/systemd/system/pynab-wifi-setup.service
cat > /etc/systemd/system/comitup.service.d/pynab.conf <<EOF
[Unit]
Wants=pynab-wifi-setup.service
After=pynab-wifi-setup.service

[Service]
ExecStart=
ExecStart=/usr/bin/python3 $root_dir/network/comitup_start.py
EOF
cat > /etc/systemd/system/nabd.service.d/wifi.conf <<'EOF'
[Unit]
Wants=pynab-wifi-setup.service
After=pynab-wifi-setup.service
EOF
chmod 0644 /etc/systemd/system/pynab-wifi-setup.service /etc/systemd/system/comitup.service.d/pynab.conf /etc/systemd/system/nabd.service.d/wifi.conf
chmod 0755 "$root_dir/comitup-callback.sh"
systemctl enable NetworkManager.service comitup.service pynab-wifi-setup.service
# Comitup owns port 80 and starts nginx only after the upstream connection succeeds.
if systemctl list-unit-files nginx.service --no-legend --no-pager | grep -q '^nginx.service'; then
    systemctl disable nginx.service
fi
if [[ -d /run/systemd/system ]]; then
    systemctl daemon-reload
fi
echo 'Wi-Fi onboarding configured for the next boot; no network service was restarted.'
