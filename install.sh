#!/usr/bin/env bash

set -euo pipefail
trap 's=$?; echo "$0: Error on line "$LINENO": $BASH_COMMAND"; exit $s' ERR

# makerfaire2018: Paris Maker Faire 2018 card, only fits Nabaztag V1.
# (default): Ulule 2019 card, fits Nabaztag V1 and Nabaztag V2. Features a microphone. Button is on GPIO 17.
makerfaire2018=0

# ci-chroot : we're running in CI to build a release image or run tests
ci_chroot=0

# test : user wants to run tests (good idea, makes sure sounds and leds are functional)
test=0

# upgrade : this script is invoked from upgrade.sh, typically from the button in the web interface.
upgrade=0

min_py_major=3
min_py_minor=13

if [ "${1:-}" == "--makerfaire2018" ]; then
  makerfaire2018=1
  shift
fi

if [ "${1:-}" == "ci-chroot" ]; then
  ci_chroot=1
elif [ "${1:-}" == "ci-chroot-test" ]; then
  ci_chroot=1
  test=1
elif [ "${1:-}" == "test" ]; then
  test=1
elif [ "${1:-}" == "--upgrade" ]; then
  upgrade=1
  # auto-detect Maker Faire card here.
  if [ `sudo aplay -L | grep -c "hifiberry"` -gt 0 ]; then
    makerfaire2018=1
  fi
fi

if [ $ci_chroot -eq 0 ] && [ $test -eq 0 ]; then
  model=$(grep "^Model" /proc/cpuinfo ; true)
  if [[ ! "$model" == *"Raspberry Pi Zero"* ]]; then
    echo "Installation only planned on Raspberry Pi Zero, will cowardly exit"
    exit 1
  fi
fi

if [ "$EUID" -eq 0 ] && [ $upgrade -ne 1 ]; then
  echo "Run installation as a regular user; root is supported only for --upgrade"
  exit 1
fi

cd `dirname "$0"`
root_dir=`pwd`
owner=`stat -c '%U' ${root_dir}`
uid=`stat -c '%u' ${root_dir}`
gid=`stat -c '%g' ${root_dir}`
[[ $uid != 0 && $owner != UNKNOWN ]] || { echo "The checkout must belong to a regular user." >&2; exit 1; }

run_as_owner() {
  if [ "$EUID" -eq 0 ]; then
    sudo -H -u "#$uid" -- "$@"
  else
    "$@"
  fi
}

optional_units=(nabiftttd.service nabmastodond.service nabradio.service nabwebhook.service)

is_optional_unit() {
  [[ " ${optional_units[*]} " == *" $1 "* ]]
}

migrate_optional_units() {
  local unit_dir=$1 wants_dir=$2 name status configured
  local legacy_enabled=() disable_units=()
  for name in "${optional_units[@]}"; do
    if [[ ! -f $unit_dir/$name || ! -L $wants_dir/$name ]]; then
      continue
    fi
    if grep -Fqx "ConditionPathExists=$wants_dir/$name" "$unit_dir/$name"; then
      continue
    else
      status=$?
      [[ $status -eq 1 ]] || return "$status"
    fi
    legacy_enabled+=("$name")
  done
  if [[ ${#legacy_enabled[@]} -eq 0 ]]; then
    return 0
  fi

  configured=$(run_as_owner venv/bin/python manage.py shell -v0 -c \
    'from nabcommon.optional_units import configured_units; print(*configured_units(), sep="\n")') || return
  for name in "${legacy_enabled[@]}"; do
    if ! grep -Fqx "$name" <<< "$configured"; then
      disable_units+=("$name")
    fi
  done
  if [[ ${#disable_units[@]} -gt 0 ]]; then
    sudo systemctl disable "${disable_units[@]}"
  fi
}

inst_dir=$(dirname ${root_dir})
boot_config=/boot/firmware/config.txt
if [ ! -f "$boot_config" ]; then
  boot_config=/boot/config.txt
fi

if [ $ci_chroot -eq 0 -a $makerfaire2018 -eq 0 -a `sudo aplay -L | grep -c "tagtagtagsound"` -eq 0 ]; then
  if [ `sudo aplay -L | grep -c "hifiberry"` -gt 0 ]; then
    echo "Judging from the sound card, this looks likes a Paris Maker Faire 2018 card."
    echo "Please double-check and restart this script with --makerfaire2018"
  else
    echo "Please install and configure sound card driver:"
    echo " https://github.com/pguyot/wm8960/tree/tagtagtag-sound"
  fi
  exit 1
fi

if [ $makerfaire2018 -eq 1 ]; then
  if [ `sudo aplay -L | grep -c "hifiberry"` -eq 0 ]; then
    echo "Please install and configure sound card driver:"
    echo " https://web.archive.org/web/20170914003528/support.hifiberry.com/hc/en-us/articles/205377651-Configuring-Linux-4-x-or-higher"
    exit 1
  fi
fi

# Kernel modules and overlays are installed from the pinned image recipe.
if [ $ci_chroot -eq 0 ] && [ ! -e /dev/ear0 ]; then
  echo "Install the pinned TagTagTag drivers first; see docs/DISTRIBUTION.md."
  exit 1
fi

cd ${root_dir}

if [ -n "${PYNAB_PYTHON:-}" ]; then
  python="${PYNAB_PYTHON}"
else
  python=""
  for candidate in python3.13 python3; do
    if command -v "${candidate}" >/dev/null 2>&1 && "${candidate}" - <<PY
import sys
sys.exit(0 if sys.version_info[:2] == (${min_py_major}, ${min_py_minor}) else 1)
PY
    then
      python="${candidate}"
      break
    fi
  done
fi

if [ -z "${python}" ] || ! command -v "${python}" >/dev/null 2>&1; then
  echo "Please install Python ${min_py_major}.${min_py_minor}+ and its venv module"
  echo "On Debian/Raspberry Pi OS this is typically python3, python3-venv and python3-dev from a recent release."
  exit 1
fi

py_ver=$("${python}" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)
if ! "${python}" - <<PY
import sys
sys.exit(0 if sys.version_info[:2] == (${min_py_major}, ${min_py_minor}) else 1)
PY
then
  echo "This distribution requires Python ${min_py_major}.${min_py_minor}; found ${py_ver}."
  exit 1
fi

venv_cfg="venv/pyvenv.cfg"
if [[ -f "${venv_cfg}" && "$(grep -c version\ =\ ${py_ver} ${venv_cfg})" -eq 0 ]]; then
   echo "Existing venv uses another Python version; inspect it before rebuilding. Nothing removed." >&2
   exit 1
fi
if [ ! -d "venv" ]; then
  echo "Creating Python ${py_ver} virtual environment"
  run_as_owner "${python}" -m venv --system-site-packages venv
fi
if ! grep -q '^include-system-site-packages = true$' "$venv_cfg"; then
  echo "The venv must expose the Raspberry Pi OS GPIO packages; recreate it with --system-site-packages."
  exit 1
fi
if [ "$(uname -m)" = "armv6l" ]; then
  run_as_owner venv/bin/python - <<'PY'
from importlib.metadata import PackageNotFoundError, version

import lgpio
import RPi.GPIO

version("rpi-lgpio")
try:
    version("RPi.GPIO")
except PackageNotFoundError:
    pass
else:
    raise SystemExit("RPi.GPIO conflicts with rpi-lgpio; remove it from this Python environment.")
PY
fi

echo "Installing PyPi requirements"
# Start with wheel which is required to compile some of the other requirements
run_as_owner venv/bin/pip install --no-cache-dir wheel
requirements_file=requirements-runtime.txt
if [ $test -eq 1 ]; then
  requirements_file=requirements.txt
fi
run_as_owner venv/bin/pip install --no-cache-dir -r "$requirements_file"

echo "Tuning PostgreSQL memory settings for Raspberry Pi."
pg_configs=(/etc/postgresql/*/main/postgresql.conf)
if [ "${#pg_configs[@]}" -ne 1 ] || [ ! -f "${pg_configs[0]}" ]; then
  echo "Expected one PostgreSQL main cluster; install PostgreSQL on the test SD first."
  exit 1
fi
pg_config="${pg_configs[0]}"
pg_hba="${pg_config%/postgresql.conf}/pg_hba.conf"
cluster_version=$(basename "$(dirname "$(dirname "$pg_config")")")
sudo sed -i 's/^shared_buffers = .*/shared_buffers = 32MB/' "$pg_config"
sudo sed -i 's/^max_connections = .*/max_connections = 30/' "$pg_config"
if ! sudo grep -qE '^local[[:space:]]+pynab[[:space:]]+pynab[[:space:]]+trust([[:space:]]|$)' "$pg_hba"; then
  echo "Allowing local connections only to the Pynab database as the Pynab role."
  if [ ! -f "${pg_hba}.pynab-before" ]; then
    sudo cp -p "$pg_hba" "${pg_hba}.pynab-before"
  fi
  sudo sed -i '1ilocal pynab pynab trust' "$pg_hba"
fi
if [ $test -eq 1 ] && ! sudo grep -qE '^local[[:space:]]+all[[:space:]]+pynab[[:space:]]+trust([[:space:]]|$)' "$pg_hba"; then
  # Django creates a separate test database and uses postgres for maintenance.
  sudo sed -i '1ilocal all pynab trust' "$pg_hba"
fi
if [ $ci_chroot -eq 1 ]; then
  sudo pg_ctlcluster --skip-systemctl-redirect "$cluster_version" main restart
else
  sudo systemctl restart postgresql
fi

restart_nginx() {
  if [[ -f /etc/systemd/system/comitup.service.d/pynab.conf ]] &&
     ! /usr/bin/timeout 10 /usr/bin/python3 "$root_dir/network/comitup_start.py" --connected; then
    echo "Comitup manages the Wi-Fi portal; leaving nginx state unchanged."
    return
  fi
  sudo systemctl restart nginx
}

sudo sed -e "s|/opt/pynab|${root_dir}|g" < nabweb/nginx-site.conf > /tmp/nginx-site.conf
if [ $upgrade -eq 0 ]; then
  if [ ! -e '/etc/nginx/sites-enabled/pynab' ]; then
    echo "Installing Nginx configuration file"
    if [ -h '/etc/nginx/sites-enabled/default' ]; then
      sudo rm /etc/nginx/sites-enabled/default
    fi
    sudo install -o root -g root -m 0644 /tmp/nginx-site.conf /etc/nginx/sites-enabled/pynab
    if [ $ci_chroot -eq 0 ]; then
      restart_nginx
    fi
  else
    diff -q '/etc/nginx/sites-enabled/pynab' /tmp/nginx-site.conf >/dev/null || {
      echo "Updating Nginx configuration file"
      sudo install -o root -g root -m 0644 /tmp/nginx-site.conf /etc/nginx/sites-enabled/pynab
      if [ $ci_chroot -eq 0 ]; then
        restart_nginx
      fi
    }
  fi
else
  echo "Restarting Nginx"
  if [ -e '/etc/nginx/sites-enabled/pynab' ]; then
    sudo install -o root -g root -m 0644 /tmp/nginx-site.conf /etc/nginx/sites-enabled/pynab
    restart_nginx
  fi
fi
sudo rm -f /tmp/nginx-site.conf

psql -U pynab -c '' 2>/dev/null || {
  echo "Creating PostgreSQL database"
  sudo -u postgres psql -U postgres -c "CREATE USER pynab"
  sudo -u postgres psql -U postgres -c "CREATE DATABASE pynab OWNER=pynab LC_COLLATE='C' LC_CTYPE='C' ENCODING='UTF-8' TEMPLATE template0"
}
if [ $test -eq 1 ]; then
  sudo -u postgres psql -U postgres -c "ALTER ROLE pynab CREATEDB"
fi

echo "Updating data models"
run_as_owner venv/bin/python manage.py migrate

# Older updaters explicitly restart previously active units after installation.
# Disable unused integrations before installing the guard that blocks that start.
if [ $upgrade -eq 1 ]; then
  migrate_optional_units /lib/systemd/system /etc/systemd/system/multi-user.target.wants
fi

all_locales="-l fr_FR -l de_DE -l en_US -l en_GB -l it_IT -l es_ES -l ja_jp -l pt_BR -l de -l en -l es -l fr -l it -l ja -l pt"

echo "Updating localization messages"
if [ $upgrade -eq 0 ]; then
  run_as_owner venv/bin/django-admin compilemessages ${all_locales}
else
  for module in nab*/locale; do
    (
      cd `dirname ${module}`
      run_as_owner ../venv/bin/django-admin compilemessages ${all_locales}
    )
  done
fi

if [ $test -eq 1 ]; then
  echo "Running tests"
  if [ $ci_chroot -eq 1 ]; then
      sudo CI=1 venv/bin/pytest
  else
      sudo venv/bin/pytest
  fi
fi

if [ $ci_chroot -eq 1 ]; then
  sudo pg_ctlcluster --skip-systemctl-redirect "$cluster_version" main stop
fi

if [[ -f /etc/systemd/system/comitup.service.d/pynab.conf ]]; then
  sudo bash "$root_dir/network/install.sh" --no-start
fi

# copy service files
echo "Installing service files"
for service_file in nabd/nabd.socket */*.service ; do
  name=`basename ${service_file}`
  if [ "${name}" = "nabassistd.service" ] || [ "${name}" = "nabhomeassistantd.service" ]; then
    echo "Skipping ${name} on the Zero W migration."
    continue
  fi
  sudo sed -e "s|/opt/pynab|${root_dir}|g" -e "s|/home/pi/pynab|${root_dir}|g" < ${service_file} > /tmp/${name}
  sudo install -o root -g root -m 0644 /tmp/${name} /lib/systemd/system/${name}
  sudo rm -f /tmp/${name}
  if [ $upgrade -eq 0 ] && ! is_optional_unit "$name"; then
    sudo systemctl enable ${name}
  fi
done
if [ $ci_chroot -eq 0 ]; then
  sudo systemctl daemon-reload
fi
sudo sed -e "s|/opt/pynab|${root_dir}|g" < nabboot/nabboot.py > /tmp/nabboot.py
sudo install -d -m 0755 /lib/systemd/system-shutdown
sudo install -o root -g root -m 0755 /tmp/nabboot.py /lib/systemd/system-shutdown/nabboot.py
sudo rm /tmp/nabboot.py

# setup Pynab logs rotation
echo "Setting up Pynab logs rotation"
cat > '/tmp/pynab' <<- END
/var/log/nab*.log {
  weekly
  rotate 4
  missingok
  notifempty
  copytruncate
  delaycompress
  compress
}
END
sudo install -o root -g root -m 0644 /tmp/pynab /etc/logrotate.d/pynab
sudo rm -f /tmp/pynab

# advertise rabbit on local network
if [ ! -f "/etc/avahi/services/pynab.service" ]; then
  echo "Setting up Avahi service for Pynab"
  cat > '/tmp/pynab.service' <<- END
<?xml version="1.0" standalone='no'?><!--*-nxml-*-->
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<!-- See avahi.service(5) for more information about this configuration file -->
<service-group>
  <name replace-wildcards="yes">Nabaztag rabbit (%h)</name>
  <service>
    <type>_http._tcp</type>
    <port>80</port>
    <txt-record>vendor=violet</txt-record>
    <txt-record>model=tag:tag:tag</txt-record>
  </service>
</service-group>
END
  sudo install -o root -g root -m 0644 /tmp/pynab.service /etc/avahi/services/pynab.service
  sudo rm -f /tmp/pynab.service
fi
sudo install -d -o "${uid}" -g "${gid}" -m 0700 /var/lib/pynab/update

# The updater restores only services that were active before the update.
if [ $ci_chroot -eq 0 ] && [ $upgrade -eq 0 ]; then
  echo "Starting services"
  sudo systemctl restart logrotate.service || true
  sudo systemctl start nabboot.service
  sudo systemctl start nabd.socket nabd.service
  for service_file in */*.service; do
    name=$(basename "$service_file")
    case $name in
      nabboot.service|nabd.service|nabweb.service|nabassistd.service|nabhomeassistantd.service) continue ;;
    esac
    if is_optional_unit "$name"; then
      continue
    fi
    sudo systemctl start "$name"
  done
  sudo systemctl start nabweb.service
fi
