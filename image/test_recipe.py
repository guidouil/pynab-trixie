"""Checks for pinned source integrity and safe fresh-card provisioning."""

import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from nabcommon.optional_units import configured_units, url_configured

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


class OptionalUnitsTest(unittest.TestCase):
    unit_names = (
        "nabiftttd.service",
        "nabmastodond.service",
        "nabradio.service",
        "nabwebhook.service",
    )

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.units, self.wants = root / "units", root / "wants"
        self.units.mkdir()
        self.wants.mkdir()

    def install_fixture_unit(self, name, enabled=True, guarded=False):
        unit = self.units / name
        unit.write_text(
            f"ConditionPathExists={self.wants / name}\n" if guarded else ""
        )
        if enabled:
            (self.wants / name).symlink_to(unit)

    def migrate(self, configured="", database_status=0, systemctl_status=0):
        installer = (HERE.parent / "install.sh").read_text()
        helpers = installer.split("\noptional_units=", 1)[1].split(
            "\ninst_dir=", 1
        )[0]
        return subprocess.run(
            [
                "bash",
                "-c",
                "set -eu\n"
                "legacy_configured=$3\ndatabase_status=$4\nsystemctl_status=$5\n"
                'run_as_owner() { printf "%s\n" "$legacy_configured"; return "$database_status"; }\n'
                'sudo() { printf "%s\n" "$@"; return "$systemctl_status"; }\n'
                "optional_units="
                + helpers
                + '\nmigrate_optional_units "$1" "$2"\nprintf "continued\n"',
                "bash",
                str(self.units),
                str(self.wants),
                configured,
                str(database_status),
                str(systemctl_status),
            ],
            capture_output=True,
            text=True,
        )

    def test_fresh_or_guarded_install_skips_legacy_migration(self):
        result = self.migrate(database_status=17)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "continued\n")
        for name in self.unit_names:
            self.install_fixture_unit(name, guarded=True)
        result = self.migrate(database_status=17)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "continued\n")

    def test_upgrade_leaves_configured_or_manually_disabled_units_alone(self):
        ifttt, mastodon, radio, webhook = self.unit_names
        self.install_fixture_unit(ifttt)
        self.install_fixture_unit(mastodon)
        self.install_fixture_unit(radio)
        self.install_fixture_unit(webhook, enabled=False)
        result = self.migrate(configured=f"{ifttt}\n{radio}")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["systemctl", "disable", mastodon, "continued"],
        )

    def test_upgrade_stops_before_replacing_units_on_failure(self):
        self.install_fixture_unit(self.unit_names[0])
        result = self.migrate(database_status=17)
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(result.stdout, "")
        result = self.migrate(systemctl_status=23)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertNotIn("continued", result.stdout)

    def test_manual_start_requires_persistent_enable_link(self):
        for name in self.unit_names:
            unit = (HERE.parent / Path(name).stem / name).read_text()
            self.assertIn(
                f"ConditionPathExists=/etc/systemd/system/multi-user.target.wants/{name}",
                unit,
            )
            self.assertIn("WantedBy=multi-user.target", unit)

    def test_legacy_url_configuration_recognizes_stored_tag_urls(self):
        for url, tags, expected in (
            ("", "", False),
            ("", "{}", False),
            ("", "invalid JSON", False),
            ("", '{"123":"https://example.invalid"}', True),
            ("https://example.invalid", "", True),
        ):
            with self.subTest(url=url, tags=tags):
                self.assertEqual(url_configured(url, tags), expected)

    def test_legacy_database_uses_existing_configuration_without_writes(self):
        records = (
            SimpleNamespace(ifttt_key="configured"),
            SimpleNamespace(access_token=None),
            SimpleNamespace(
                streaming_url="",
                json_data_base='{"123":"https://example.invalid"}',
            ),
            SimpleNamespace(
                webhook_url="https://example.invalid",
                json_data_base="",
            ),
        )
        modules = {}
        for name, record in zip(self.unit_names, records):
            model = Mock()
            model.objects.filter.return_value.first.return_value = record
            modules[Path(name).stem + ".models"] = SimpleNamespace(
                Config=model
            )
        with patch.dict(sys.modules, modules):
            self.assertEqual(
                list(configured_units()),
                [
                    "nabiftttd.service",
                    "nabradio.service",
                    "nabwebhook.service",
                ],
            )
        for module in modules.values():
            module.Config.objects.filter.assert_called_once_with(pk=1)


if __name__ == "__main__":
    unittest.main()
