import stat
import tempfile
import unittest
from pathlib import Path

from nabweb.secret import installation_secret


class InstallationSecretTest(unittest.TestCase):
    def test_unique_persistent_private_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            key = installation_secret(first)
            self.assertEqual(installation_secret(first), key)
            self.assertNotEqual(installation_secret(second), key)
            self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o600)

    def test_invalid_key_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret"
            path.write_text("short")
            with self.assertRaises(ValueError):
                installation_secret(path)
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                installation_secret(link)
