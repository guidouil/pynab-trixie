"""Read the boot button before nabd owns GPIO and the LEDs."""

import logging
import os
import subprocess
import time
from pathlib import Path

BUTTON_CHANNEL = 17
SETUP_REQUEST = Path("/run/pynab-wifi-setup")
ROOT_DIR = Path(__file__).resolve().parent.parent


def button_held(gpio, duration=2.0):
    gpio.setwarnings(False)
    gpio.setmode(gpio.BCM)
    gpio.setup(BUTTON_CHANNEL, gpio.IN)
    try:
        deadline = time.monotonic() + duration
        while gpio.input(BUTTON_CHANNEL) == gpio.LOW:
            if time.monotonic() >= deadline:
                return True
            time.sleep(0.05)
        return False
    finally:
        gpio.cleanup(BUTTON_CHANNEL)


def show_setup_leds():
    python = ROOT_DIR / "venv/bin/python"
    if python.exists():
        subprocess.run(
            [
                str(python),
                "-c",
                "from nabboot.nabboot import Color, set_leds; set_leds(Color(0, 0, 255))",
            ],
            cwd=ROOT_DIR,
            timeout=10,
            check=True,
        )


def main():
    import RPi.GPIO as GPIO

    if not button_held(GPIO):
        return
    descriptor = os.open(SETUP_REQUEST, os.O_WRONLY | os.O_CREAT, 0o600)
    os.close(descriptor)
    logging.warning("Boot button held: requesting Wi-Fi setup for this boot")
    try:
        show_setup_leds()
    except Exception:
        logging.exception("Cannot show Wi-Fi setup LEDs; request is retained")


if __name__ == "__main__":
    main()
