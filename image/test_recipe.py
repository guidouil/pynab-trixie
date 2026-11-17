"""Checks for pinned source integrity and safe fresh-card provisioning."""

import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("image_fetch", HERE / "fetch.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


class RecipeTest(unittest.TestCase):
    def test_manifest_matches_driver_patches(self):
        lock = json.loads(fetch.LOCK.read_text())
        self.assertEqual(set(lock["drivers"]), {"ears", "sound", "cr14"})
        self.assertTrue(
            lock["base"]["url"].startswith(
                "https://downloads.raspberrypi.com/"
            )
        )
        self.assertNotIn("latest", lock["base"]["url"])
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
