"""Exercise installer ownership without installing packages or touching hardware."""

import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class InstallOwnerTest(unittest.TestCase):
    def helper(self):
        source = (
            Path(__file__).resolve().parents[2] / "install.sh"
        ).read_text()
        body = source.split("run_as_owner() {\n", 1)[1].split("\n}\n", 1)[0]
        return "run_as_owner() {\n" + body + "\n}\n"

    def exercise(self, privileged):
        owner = int(os.environ.get("SUDO_UID", os.getuid()))
        if owner == 0:
            self.skipTest("Requires a regular checkout owner")
        prefix = []
        if privileged and os.geteuid() != 0:
            sudo = shutil.which("sudo")
            try:
                allowed = (
                    sudo
                    and subprocess.run(
                        [sudo, "-n", "true"], capture_output=True
                    ).returncode
                    == 0
                )
            except OSError:
                allowed = False
            if not allowed:
                self.skipTest(
                    "Root ownership check requires non-interactive test sudo"
                )
            prefix = [sudo, "-n"]
        with tempfile.TemporaryDirectory() as directory:
            if os.geteuid() == 0:
                os.chown(directory, owner, pwd.getpwuid(owner).pw_gid)
            target = Path(directory) / "owned"
            command = (
                self.helper()
                + '\nuid="$1"\nrun_as_owner "$2" -c \'from pathlib import Path; import sys; Path(sys.argv[1]).touch()\' "$3"\n'
            )
            subprocess.run(
                [
                    *prefix,
                    "bash",
                    "-c",
                    command,
                    "ownership-test",
                    str(owner),
                    sys.executable,
                    str(target),
                ],
                check=True,
            )
            self.assertEqual(target.stat().st_uid, owner)

    def test_normal_install_writes_as_owner(self):
        self.exercise(privileged=False)

    def test_root_upgrade_writes_as_owner(self):
        self.exercise(privileged=True)
