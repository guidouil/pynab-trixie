"""Start unmodified Comitup, optionally offering its hotspot before reconnecting."""

import logging
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

SETUP_REQUEST = Path("/run/pynab-wifi-setup")

# Debian keeps Comitup and its metadata outside dist-packages.
DEBIAN_COMITUP = Path("/usr/share/comitup")
if (DEBIAN_COMITUP / "comitup").is_dir():
    sys.path.insert(0, str(DEBIAN_COMITUP))


def connected():
    from comitup.client import CiuClient

    return CiuClient().ciu_state()[0] == "CONNECTED"


def supports_hotspot_override(states, installed_version):
    try:
        major, minor = (int(part) for part in installed_version.split(".")[:2])
    except (ValueError, TypeError):
        return False
    return (
        major == 1
        and 43 <= minor <= 47
        and callable(getattr(states, "init_states", None))
        and isinstance(getattr(states, "startup", None), bool)
        and hasattr(states, "dns_names")
        and callable(
            getattr(getattr(states, "mdns", None), "clear_entries", None)
        )
        and callable(getattr(getattr(states, "mdns", None), "add_hosts", None))
    )


def prefer_hotspot(states):
    initialize = states.init_states

    def initialize_in_hotspot(*args, **kwargs):
        initialize(*args, **kwargs)
        # shortcut: Comitup 1.43–1.47 queues startup; review if its state machine changes.
        states.mdns.clear_entries()
        states.mdns.add_hosts(states.dns_names)
        states.startup = False

    states.init_states = initialize_in_hotspot


def main():
    from comitup import comitup, states

    if SETUP_REQUEST.exists():
        SETUP_REQUEST.unlink()
        try:
            installed_version = version("comitup")
        except PackageNotFoundError:
            installed_version = "unknown"
        if supports_hotspot_override(states, installed_version):
            prefer_hotspot(states)
        else:
            logging.warning(
                "Comitup %s has no qualified startup override; using normal Wi-Fi startup",
                installed_version,
            )
    comitup.main()


if __name__ == "__main__":
    if sys.argv[1:] == ["--connected"]:
        try:
            raise SystemExit(0 if connected() else 1)
        except Exception:
            logging.exception("Cannot query Comitup; leaving nginx unchanged")
            raise SystemExit(1)
    elif sys.argv[1:]:
        raise SystemExit("Usage: comitup_start.py [--connected]")
    else:
        main()
