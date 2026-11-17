"""Checks for pinned source integrity and safe fresh-card provisioning."""

import importlib.util
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("image_fetch", HERE / "fetch.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


class RecipeTest(unittest.TestCase):
    def test_module_priority_uses_the_canonical_merged_usr_path(self):
        lines = (HERE / "install-drivers.sh").read_text().splitlines()
        destination = next(s for s in lines if s.startswith("destination="))
        priority = next(
            s for s in lines if "Installed module priority differs:" in s
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernel = "6.18.60+rpt-rpi-v6"
            modules = root / "usr/lib/modules" / kernel
            installed = modules / "updates/nabaztag/tagtagtag-ears.ko"
            other = modules / "kernel/tagtagtag-ears.ko"
            for module in (installed, other):
                module.parent.mkdir(parents=True, exist_ok=True)
                module.write_bytes(b"module fixture")
            (root / "lib").symlink_to("usr/lib", target_is_directory=True)
            calculation = destination.replace(
                "/lib/modules/", str(root / "lib/modules") + "/"
            )
            script = (
                "set -eu\nkernel=$1\nfixture_module=$2\nname=tagtagtag_ears\n"
                'modinfo() { printf "%s\\n" "$fixture_module"; }\n'
                "fail() { exit 1; }\n" + calculation + "\n" + priority
            )
            for selected, expected in ((installed, 0), (other, 1)):
                with self.subTest(module=selected):
                    modinfo_path = (
                        root
                        / "lib/modules"
                        / kernel
                        / selected.relative_to(modules)
                    )
                    result = subprocess.run(
                        [
                            "bash",
                            "-c",
                            script,
                            "bash",
                            kernel,
                            str(modinfo_path),
                        ],
                        text=True,
                        capture_output=True,
                    )
                    self.assertEqual(
                        result.returncode, expected, result.stderr
                    )

    def test_kernel_trim_selects_only_reviewed_installed_families(self):
        packages = """ii linux-image-rpi-v6:armhf
ii linux-headers-6.18.60+rpt-rpi-v6
ii linux-image-rpi-v7:armhf
ii linux-headers-6.18.60+rpt-rpi-v7l:armhf
ii linux-image-6.18.60+rpt-rpi-v8:arm64
ii linux-base-rpi-2712:arm64
rc linux-image-6.12.1-rpi-v7
ii linux-image-armmp
ii raspberrypi-utils
"""
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; kernel_candidates',
                "bash",
                str(HERE / "trim-kernels.sh"),
            ],
            input=packages,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "linux-image-rpi-v7:armhf",
                "linux-headers-6.18.60+rpt-rpi-v7l:armhf",
                "linux-image-6.18.60+rpt-rpi-v8:arm64",
                "linux-base-rpi-2712:arm64",
            ],
        )

    def test_kernel_trim_refuses_any_unlisted_apt_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates, plan = root / "candidates", root / "plan"
            candidates.write_text(
                "linux-image-rpi-v7:armhf\nlinux-image-rpi-v8:arm64\n"
            )
            for removals, accepted in (
                (
                    "Remv linux-image-rpi-v7 [1]\nRemv linux-image-rpi-v8:arm64 [1]\n",
                    True,
                ),
                ("Remv linux-image-rpi-v6 [1]\n", False),
                ("Remv openssh-server [1]\n", False),
                ("Remv linux-image-rpi-v8 [1]\n", False),
                ("Inst linux-image-rpi-v6 [1]\n", False),
            ):
                with self.subTest(plan=removals):
                    plan.write_text(removals)
                    result = subprocess.run(
                        [
                            "bash",
                            "-c",
                            'source "$1"; validate_removals "$2" "$3"',
                            "bash",
                            str(HERE / "trim-kernels.sh"),
                            str(candidates),
                            str(plan),
                        ],
                        text=True,
                        capture_output=True,
                    )
                    self.assertEqual(
                        result.returncode == 0, accepted, result.stderr
                    )
            candidates.write_text("")
            plan.write_text("Remv linux-image-rpi-v6 [1]\n")
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'source "$1"; validate_removals "$2" "$3"',
                    "bash",
                    str(HERE / "trim-kernels.sh"),
                    str(candidates),
                    str(plan),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_manifest_matches_driver_patches(self):
        lock = json.loads(fetch.LOCK.read_text())
        self.assertEqual(set(lock["drivers"]), {"ears", "sound", "cr14"})
        self.assertTrue(
            lock["base"]["url"].startswith(
                "https://downloads.raspberrypi.com/"
            )
        )
        self.assertNotIn("latest", lock["base"]["url"])
        self.assertIn("raspios_lite_armhf-", lock["base"]["url"])
        self.assertRegex(lock["base"]["sha256"], r"^[0-9a-f]{64}$")
        for name, source in lock["drivers"].items():
            self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
            self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
            self.assertIn(source["commit"], source["url"])
            self.assertEqual(
                fetch.digest(HERE / "patches" / f"{name}.patch"),
                source["patch_sha256"],
            )

    def test_corrupt_cache_is_refused_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cached.tar.gz"
            path.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "Cached input differs"):
                fetch.download(
                    {
                        "url": "https://example.invalid/source",
                        "sha256": "0" * 64,
                    },
                    path,
                )
            self.assertEqual(path.read_bytes(), b"corrupt")

    def test_archive_cannot_escape_work_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                entry = tarfile.TarInfo("../escaped")
                entry.size = 3
                output.addfile(entry, io.BytesIO(b"bad"))
            with self.assertRaises(tarfile.FilterError):
                fetch.unpack(archive, root / "work")
            self.assertFalse((root / "escaped").exists())

    def test_driver_build_uses_explicit_kernel_and_no_private_restore(self):
        drivers = (HERE / "install-drivers.sh").read_text()
        self.assertNotIn("uname -r", drivers)
        self.assertIn("kernel=$1", drivers)
        provision = (HERE / "provision.sh").read_text()
        for private_path in (
            "/home/pi/",
            "migration/restore",
            "pynab.dump",
            "nabaztag-609",
            "authorized_keys",
        ):
            self.assertNotIn(private_path, drivers + provision)
        self.assertIn("SystemMaxUse=32M", provision)


if __name__ == "__main__":
    unittest.main()
