"""Distribution updates are tested against local repositories, never GitHub."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nabcommon import update


class RepositoryTest(unittest.TestCase):
    def git(self, directory, *arguments):
        return subprocess.run(
            ["git", "-C", str(directory), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.seed = self.base / "seed"
        self.seed.mkdir()
        self.git(self.seed, "init", "--initial-branch=trixie")
        self.git(self.seed, "config", "user.name", "Update test")
        self.git(self.seed, "config", "user.email", "test@example.invalid")
        (self.seed / "value").write_text("one")
        for service in ("nabd", "nabboot", "nabradio", "nabweb"):
            (self.seed / service).mkdir()
            (self.seed / service / f"{service}.service").write_text("test")
        self.git(self.seed, "add", ".")
        self.git(self.seed, "commit", "-m", "Initial")
        self.remote = self.base / "remote.git"
        self.git(
            self.base, "clone", "--bare", str(self.seed), str(self.remote)
        )
        self.git(self.seed, "remote", "add", "origin", str(self.remote))
        self.checkout = self.base / "installed with spaces"
        self.git(self.base, "clone", str(self.remote), str(self.checkout))
        self.git(self.checkout, "config", "user.name", "Update test")
        self.git(self.checkout, "config", "user.email", "test@example.invalid")
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(update, "REPOSITORY_URL", str(self.remote)).start()
        self.repo = update.Repository(self.checkout)

    def publish(self):
        (self.seed / "value").write_text("two")
        self.git(self.seed, "commit", "-am", "Second")
        self.git(self.seed, "push", "origin", "trixie")
        return self.git(self.seed, "rev-parse", "HEAD")

    def test_clean_checkout_and_fast_forward(self):
        self.assertEqual(self.repo.inspect()["commits_count"], 0)
        target = self.publish()
        info = self.repo.inspect()
        self.assertEqual(info["commits_count"], 1)
        self.assertEqual(info["target"], target)
        self.repo.git("merge", "--ff-only", "--no-edit", target)
        self.assertEqual((self.checkout / "value").read_text(), "two")
        self.assertEqual(self.repo.inspect()["commits_count"], 0)

    def test_refuses_untracked_staged_and_modified_files(self):
        for mode in ("untracked", "staged", "modified"):
            with self.subTest(mode=mode):
                file = self.checkout / (
                    "private" if mode == "untracked" else "value"
                )
                original = file.read_text() if file.exists() else None
                file.write_text("personal data")
                if mode == "staged":
                    self.git(self.checkout, "add", "value")
                with self.assertRaisesRegex(
                    update.UpdateError, "Local changes"
                ):
                    self.repo.inspect()
                if mode == "staged":
                    self.git(self.checkout, "restore", "--staged", "value")
                if original is None:
                    file.unlink()
                else:
                    file.write_text(original)

    def test_refuses_other_branch_remote_and_upstream(self):
        self.git(self.checkout, "switch", "-c", "other")
        with self.assertRaisesRegex(update.UpdateError, "distribution branch"):
            self.repo.inspect()
        self.git(self.checkout, "switch", "trixie")
        self.git(
            self.checkout,
            "remote",
            "set-url",
            "origin",
            "https://example.invalid/pynab.git",
        )
        with self.assertRaisesRegex(update.UpdateError, "Origin"):
            self.repo.inspect()
        self.git(
            self.checkout, "remote", "set-url", "origin", str(self.remote)
        )
        self.git(self.checkout, "branch", "--unset-upstream")
        with self.assertRaises(update.UpdateError):
            self.repo.inspect()

    def test_refuses_local_or_divergent_commits(self):
        (self.checkout / "local").write_text("keep")
        self.git(self.checkout, "add", "local")
        self.git(self.checkout, "commit", "-m", "Local")
        with self.assertRaisesRegex(update.UpdateError, "Local commits"):
            self.repo.inspect()
        self.publish()
        with self.assertRaisesRegex(update.UpdateError, "divergent"):
            self.repo.inspect()
        self.assertEqual((self.checkout / "local").read_text(), "keep")

    def test_refuses_git_url_rewriting(self):
        self.git(
            self.checkout,
            "config",
            "url.https://example.invalid/.insteadOf",
            str(self.remote),
        )
        with self.assertRaisesRegex(update.UpdateError, "URL rewriting"):
            self.repo.inspect()

    def test_fetch_failure_keeps_head_and_files(self):
        before = self.git(self.checkout, "rev-parse", "HEAD")
        self.remote.rename(self.base / "unavailable.git")
        with self.assertRaises(update.UpdateError):
            self.repo.inspect()
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), before)
        self.assertEqual((self.checkout / "value").read_text(), "one")

    def exercise_upgrade(self, installation_fails=False):
        target = self.publish()
        state = self.base / "state"
        state.mkdir()
        commands = []
        real_run = subprocess.run

        def run(command, **kwargs):
            if command[0] == "git":
                return real_run(command, **kwargs)
            commands.append(command)
            if command[0] == "pg_dump":
                kwargs["stdout"].write(b"PGDMP-test")
            if command[:2] == ["systemctl", "is-active"]:
                states = [
                    (
                        "active"
                        if name
                        in {"nabd.socket", "nabd.service", "nabweb.service"}
                        else "inactive"
                    )
                    for name in command[2:]
                ]
                return subprocess.CompletedProcess(
                    command, 3, "\n".join(states) + "\n"
                )
            if command[:2] == ["bash", "install.sh"] and installation_fails:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        with mock.patch.object(update.subprocess, "run", side_effect=run):
            if installation_fails:
                with self.assertRaises(update.UpdateError):
                    update.run_upgrade(self.checkout, state)
            else:
                update.run_upgrade(self.checkout, state)
        result = update.read_status(state)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), target)
        backup = Path(result["database_backup"])
        self.assertEqual(backup.read_bytes(), b"PGDMP-test")
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(commands[0], ["sudo", "-n", "true"])
        self.assertEqual(commands[1][0], "pg_dump")
        stop = next(
            command
            for command in commands
            if command[:4] == ["sudo", "-n", "systemctl", "stop"]
        )
        self.assertEqual(set(stop[4:]), {"nabd.socket", "nabd.service"})
        self.assertFalse(
            any("nabboot.service" in command for command in commands)
        )
        return result, commands

    def test_upgrade_backs_up_and_restarts_only_active_services(self):
        result, commands = self.exercise_upgrade()
        self.assertEqual(result["status"], "done")
        self.assertIn(
            ["sudo", "-n", "systemctl", "restart", "nabweb.service"], commands
        )
        self.assertIn(
            [
                "sudo",
                "-n",
                "systemctl",
                "start",
                "nabd.socket",
                "nabd.service",
            ],
            commands,
        )

    def test_installation_error_remains_visible_without_restarting_web(self):
        result, commands = self.exercise_upgrade(installation_fails=True)
        self.assertEqual(result["status"], "error")
        self.assertIn("failed", result["message"])
        self.assertFalse(
            any(
                command[:4] == ["sudo", "-n", "systemctl", "restart"]
                for command in commands
            )
        )

    def test_lock_prevents_a_second_launch(self):
        state = self.base / "state"
        state.mkdir()
        with update.update_lock(state):
            with self.assertRaisesRegex(update.UpdateError, "already running"):
                update.start_upgrade(self.checkout, state)

    def test_web_launch_gives_log_to_checkout_owner(self):
        state = self.base / "state"
        state.mkdir()
        with (
            mock.patch.object(
                update.Repository, "inspect", return_value={"commits_count": 1}
            ),
            mock.patch.object(update.os, "geteuid", return_value=0),
            mock.patch.object(update.os, "fchown") as chown,
            mock.patch.object(update.subprocess, "Popen"),
        ):
            update.start_upgrade(self.checkout, state)
        account = self.checkout.stat()
        chown.assert_any_call(mock.ANY, account.st_uid, account.st_gid)
        self.assertEqual((state / "upgrade.log").stat().st_mode & 0o777, 0o600)

    def test_corrupt_status_is_reported_as_error(self):
        state = self.base / "state"
        state.mkdir()
        (state / "status.json").write_text("[]")
        self.assertEqual(update.read_status(state)["status"], "error")

    def test_failed_database_backup_does_not_change_code_or_stop_services(
        self,
    ):
        self.publish()
        state = self.base / "state"
        state.mkdir()
        before = self.git(self.checkout, "rev-parse", "HEAD")
        real_run = subprocess.run

        def run(command, **kwargs):
            if command[0] == "git":
                return real_run(command, **kwargs)
            if command == ["sudo", "-n", "true"]:
                return subprocess.CompletedProcess(command, 0)
            self.assertEqual(command[0], "pg_dump")
            raise subprocess.CalledProcessError(1, command)

        with mock.patch.object(update.subprocess, "run", side_effect=run):
            with self.assertRaises(update.UpdateError):
                update.run_upgrade(self.checkout, state)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), before)
        result = update.read_status(state)
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["database_backup"])
        self.assertFalse(list((state / "backups").glob("*.dump")))

    def test_missing_sudo_permission_does_not_change_code(self):
        self.publish()
        state = self.base / "state"
        state.mkdir()
        before = self.git(self.checkout, "rev-parse", "HEAD")
        real_run = subprocess.run

        def run(command, **kwargs):
            if command[0] == "git":
                return real_run(command, **kwargs)
            self.assertEqual(command, ["sudo", "-n", "true"])
            raise subprocess.CalledProcessError(1, command)

        with mock.patch.object(update.subprocess, "run", side_effect=run):
            with self.assertRaisesRegex(update.UpdateError, "sudo"):
                update.run_upgrade(self.checkout, state)
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), before)
        self.assertEqual(update.read_status(state)["status"], "error")

    def test_interrupted_update_is_not_reported_as_running_forever(self):
        state = self.base / "state"
        state.mkdir()
        with mock.patch.object(update.time, "time", return_value=1):
            update.write_status(state, "ok", "Installing")
        result = update.read_status(state)
        self.assertEqual(result["status"], "error")
        self.assertIn("interrupted", result["message"])


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nabweb.settings")
import django  # noqa: E402

django.setup()
from django.test import RequestFactory, SimpleTestCase  # noqa: E402

from nabweb.views import (  # noqa: E402
    GitInfo,
    NabWebUpgradeNowView,
    NabWebUpgradeRepositoryInfoView,
)


class UpgradeViewTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_unknown_repository_is_404(self):
        from django.http import Http404

        with self.assertRaises(Http404):
            NabWebUpgradeRepositoryInfoView.as_view()(
                self.factory.get("/upgrade/info/unknown"),
                repository="unknown",
            )

    def test_post_checks_server_even_when_button_was_enabled(self):
        with mock.patch(
            "nabweb.views.update.start_upgrade",
            side_effect=update.UpdateError("Local changes"),
        ):
            response = NabWebUpgradeNowView.as_view()(
                self.factory.post("/upgrade/now")
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.content)["status"], "error")

    def test_get_reports_failure_instead_of_completion(self):
        with mock.patch(
            "nabweb.views.update.read_status",
            return_value={"status": "error", "message": "Installation failed"},
        ):
            response = NabWebUpgradeNowView.as_view()(
                self.factory.get("/upgrade/now")
            )
        self.assertEqual(json.loads(response.content)["status"], "error")

    def test_wrong_remote_cannot_be_shown_as_updatable(self):
        with mock.patch(
            "nabweb.views.update.Repository.inspect",
            side_effect=update.UpdateError("Wrong origin"),
        ):
            result = GitInfo.do_get_repository_info("pynab", ".")
        self.assertFalse(result["updatable"])
        self.assertEqual(result["status"], "error")

    def test_template_renders_without_database(self):
        from django.template.loader import render_to_string

        html = render_to_string(
            "nabweb/upgrade/index.html",
            {
                "pynab": {"name": "Pynab Trixie", "status": "ok"},
                "update_state": {
                    "status": "error",
                    "message": "Installation failed",
                },
            },
        )
        self.assertIn("Installation failed", html)
        self.assertIn("disabled", html)


if __name__ == "__main__":
    unittest.main()
