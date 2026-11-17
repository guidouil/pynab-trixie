import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CALLBACK = "/usr/lib/pynab/comitup-callback"


class CallbackTests(unittest.TestCase):
    def test_installed_callback_and_parent_are_owned_by_root(self):
        source = (ROOT / "network/install.sh").read_text()
        commands = [
            shlex.split(line)
            for line in source.splitlines()
            if line.startswith("install ") and "/usr/lib/pynab" in line
        ]
        self.assertEqual(len(commands), 2)
        self.assertEqual(
            {args[-1] for args in commands}, {"/usr/lib/pynab", CALLBACK}
        )
        for args in commands:
            self.assertEqual(args[args.index("-o") + 1], "root")
            self.assertEqual(args[args.index("-g") + 1], "root")
            self.assertEqual(args[args.index("-m") + 1], "0755")

    def test_network_configuration_uses_root_copy_and_preserves_password(self):
        source = (ROOT / "network/install.sh").read_text()
        config = source.split("python3 - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comitup.conf"
            original = (
                "ap_password: fixture-password\n"
                "external_callback: /opt/pynab/comitup-callback.sh\n"
            )
            path.write_text(original)
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    config.replace("/etc/comitup.conf", str(path)),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = path.read_text()
            self.assertIn("external_callback: " + CALLBACK + "\n", result)
            self.assertIn("ap_password: fixture-password\n", result)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                path.with_suffix(".conf.before-pynab").read_text(), original
            )

    def test_connected_callback_signals_services_without_sudo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "commands"
            for command in ("systemctl", "nc", "sudo"):
                script = root / command
                script.write_text(
                    "#!/bin/sh\nprintf '%s\\n' "
                    + shlex.quote(command)
                    + '" $*" >> '
                    + shlex.quote(str(log))
                    + "\n"
                    + ("cat >/dev/null\n" if command == "nc" else "")
                )
                script.chmod(0o755)
            subprocess.run(
                ["bash", str(ROOT / "comitup-callback.sh"), "CONNECTED"],
                env={
                    **os.environ,
                    "PATH": str(root) + os.pathsep + os.defpath,
                },
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            commands = log.read_text().splitlines()
            self.assertNotIn("sudo", " ".join(commands))
            self.assertIn("systemctl kill -s SIGUSR1 nabairqualityd", commands)
            self.assertIn("systemctl kill -s SIGUSR1 nabweatherd", commands)


if __name__ == "__main__":
    unittest.main()
