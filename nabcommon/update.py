"""Git updates for the Trixie distribution, shared by the web UI and CLI."""

import contextlib
import datetime
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPOSITORY_URL = "https://github.com/guidouil/pynab-trixie.git"
BRANCH = "trixie"
UPSTREAM = "origin/trixie"
STATE_DIR = Path("/var/lib/pynab/update")


class UpdateError(Exception):
    pass


class Repository:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.owner = self.root.stat().st_uid
        if self.owner == 0:
            raise UpdateError(
                "The Pynab checkout must belong to a regular user."
            )

    def owner_command(self, command):
        if os.geteuid() != self.owner:
            return ["sudo", "-n", "-u", f"#{self.owner}", *command]
        return command

    def git(self, *args):
        try:
            result = subprocess.run(
                self.owner_command(["git", "-C", str(self.root), *args]),
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError) as error:
            raise UpdateError(
                "Git check failed or timed out. Check the repository and "
                "Internet connection over SSH."
            ) from error

    def inspect(self, fetch=True):
        if self.git("rev-parse", "--show-toplevel") != str(self.root):
            raise UpdateError("Pynab must be the root of its Git checkout.")
        if self.git("branch", "--show-current") != BRANCH:
            raise UpdateError(
                "Only the trixie distribution branch is supported."
            )
        if (
            self.git("config", "--get-all", "remote.origin.url")
            != REPOSITORY_URL
        ):
            raise UpdateError(
                "Origin is not the official Pynab Trixie repository."
            )
        if self.git("remote", "get-url", "--all", "origin") != REPOSITORY_URL:
            raise UpdateError(
                "Git URL rewriting is not supported for updates."
            )
        if self.git("rev-parse", "--abbrev-ref", "@{upstream}") != UPSTREAM:
            raise UpdateError("The trixie branch must track origin/trixie.")
        if self.git("status", "--porcelain", "--untracked-files=all"):
            raise UpdateError(
                "Local changes or untracked files must be saved before updating."
            )
        if fetch:
            self.git(
                "fetch",
                "--no-tags",
                "origin",
                "refs/heads/trixie:refs/remotes/origin/trixie",
            )
        ahead, behind = map(
            int,
            self.git(
                "rev-list",
                "--left-right",
                "--count",
                "HEAD..." + UPSTREAM,
            ).split(),
        )
        if ahead:
            raise UpdateError(
                "Local commits or divergent history prevent a fast-forward update."
            )
        return {
            "status": "ok",
            "head": self.git("rev-parse", "HEAD"),
            "target": self.git("rev-parse", UPSTREAM),
            "branch": BRANCH,
            "upstream_branch": UPSTREAM,
            "url": REPOSITORY_URL,
            "tracks_expected_upstream": True,
            "local_changes": False,
            "commits_count": behind,
            "local_commits_count": ahead,
            "tag": self.git("describe", "--long", "--tags", "--always"),
        }


def write_status(directory, status, message, **details):
    directory = Path(directory)
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=directory,
        prefix=".status-",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        try:
            if os.geteuid() == 0:
                owner = directory.stat()
                os.fchown(stream.fileno(), owner.st_uid, owner.st_gid)
            json.dump(
                {
                    "status": status,
                    "message": message,
                    "updated_at": time.time(),
                    **details,
                },
                stream,
            )
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, directory / "status.json")
        finally:
            temporary.unlink(missing_ok=True)


def read_status(directory=STATE_DIR):
    try:
        with (Path(directory) / "status.json").open() as stream:
            result = json.load(stream)
        if (
            result["status"] == "ok"
            and time.time() - result.get("updated_at", 0) > 5
        ):
            try:
                with update_lock(directory):
                    return {
                        **result,
                        "status": "error",
                        "message": "The update was interrupted. Check the update log over SSH.",
                    }
            except UpdateError:
                pass
        return result
    except FileNotFoundError:
        return {"status": "done", "message": "No update in progress."}
    except (OSError, ValueError, TypeError, KeyError):
        return {"status": "error", "message": "Cannot read update status."}


@contextlib.contextmanager
def update_lock(directory=STATE_DIR, wait=False):
    directory = Path(directory)
    try:
        stream = (directory / "lock").open("a")
        if os.geteuid() == 0:
            owner = directory.stat()
            os.fchown(stream.fileno(), owner.st_uid, owner.st_gid)
        os.fchmod(stream.fileno(), 0o600)
    except OSError as error:
        raise UpdateError(
            "Update state directory is missing or inaccessible."
        ) from error
    try:
        try:
            flags = fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB)
            fcntl.flock(stream.fileno(), flags)
        except BlockingIOError as error:
            raise UpdateError("An update is already running.") from error
        yield
    finally:
        stream.close()


def run_upgrade(root, directory=STATE_DIR):
    directory = Path(directory)
    repo = Repository(root)
    if os.geteuid() not in {0, repo.owner}:
        raise UpdateError(
            "Run upgrade.sh as root or the Pynab checkout owner."
        )
    # The child waits for the short launch lock held by the web request.
    with update_lock(directory, wait=True):
        previous = None
        backup = None
        active_services = []
        try:
            write_status(
                directory, "ok", "Checking the distribution repository"
            )
            info = repo.inspect()
            previous = info["head"]
            if not info["commits_count"]:
                write_status(directory, "done", "Pynab is already up to date.")
                return
            if os.geteuid() != 0:
                try:
                    subprocess.run(
                        ["sudo", "-n", "true"],
                        check=True,
                        timeout=15,
                        capture_output=True,
                    )
                except (OSError, subprocess.SubprocessError) as error:
                    raise UpdateError(
                        "CLI updates require non-interactive sudo; use the "
                        "root web service or run sudo bash upgrade.sh. "
                        "No code or service has been changed."
                    ) from error
            write_status(directory, "ok", "Backing up the Pynab database")
            backups = directory / "backups"
            backups.mkdir(mode=0o700, exist_ok=True)
            if os.geteuid() == 0:
                os.chown(backups, repo.owner, repo.root.stat().st_gid)
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y%m%dT%H%M%SZ"
            )
            backup_path = backups / f"{stamp}-{previous[:12]}.dump"
            partial = backup_path.with_suffix(".dump.partial")
            with partial.open("xb") as output:
                os.chmod(partial, 0o600)
                if os.geteuid() == 0:
                    os.fchown(
                        output.fileno(), repo.owner, repo.root.stat().st_gid
                    )
                subprocess.run(
                    [
                        "pg_dump",
                        "--no-password",
                        "--username=pynab",
                        "--format=custom",
                    ],
                    stdout=output,
                    check=True,
                    timeout=180,
                )
            partial.rename(backup_path)
            backup = backup_path
            # Complete every network/Git operation before stopping the rabbit.
            write_status(
                directory,
                "ok",
                "Applying the fast-forward update",
                previous_head=previous,
                database_backup=str(backup),
            )
            repo.inspect(fetch=False)
            repo.git("merge", "--ff-only", "--no-edit", info["target"])
            write_status(
                directory,
                "ok",
                "Installing the Pynab runtime",
                previous_head=previous,
                database_backup=str(backup),
            )
            services = [
                "nabd.socket",
                "nabweb.service",
                *[
                    path.name
                    for path in repo.root.glob("nab*/*.service")
                    if path.name
                    not in {
                        "nabboot.service",
                        "nabweb.service",
                        "nabassistd.service",
                        "nabhomeassistantd.service",
                    }
                ],
            ]
            states = subprocess.run(
                ["systemctl", "is-active", *services],
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.splitlines()
            if len(states) != len(services):
                raise UpdateError(
                    "Cannot determine which Pynab services are active."
                )
            web_active = states[1] == "active"
            active_services = [
                name
                for name, state in zip(services, states)
                if state == "active" and name != "nabweb.service"
            ]
            if active_services:
                subprocess.run(
                    ["sudo", "-n", "systemctl", "stop", *active_services],
                    check=True,
                    timeout=90,
                )
            subprocess.run(
                ["bash", "install.sh", "--upgrade"],
                cwd=repo.root,
                check=True,
                timeout=1800,
            )
            if active_services:
                subprocess.run(
                    ["sudo", "-n", "systemctl", "start", *active_services],
                    check=True,
                    timeout=120,
                )
            write_status(
                directory,
                "done",
                "Pynab update complete.",
                previous_head=previous,
                database_backup=str(backup),
            )
            if web_active:
                subprocess.run(
                    ["sudo", "-n", "systemctl", "restart", "nabweb.service"],
                    check=True,
                    timeout=90,
                )
        except (OSError, subprocess.SubprocessError, UpdateError) as error:
            message = (
                str(error)
                if isinstance(error, UpdateError)
                else (
                    "Update failed. Check /var/lib/pynab/update/upgrade.log over SSH; "
                    "completed database backups and the previous Git revision are retained. "
                    "Pynab services may remain stopped."
                )
            )
            write_status(
                directory,
                "error",
                message,
                previous_head=previous,
                database_backup=str(backup) if backup else None,
            )
            raise UpdateError(message) from error


def start_upgrade(root, directory=STATE_DIR):
    directory = Path(directory)
    repo = Repository(root)
    if os.geteuid() not in {0, repo.owner}:
        raise UpdateError("Start updates as root or the Pynab checkout owner.")
    with update_lock(directory):
        info = repo.inspect()
        if not info["commits_count"]:
            raise UpdateError("Pynab is already up to date.")
        write_status(directory, "ok", "Starting the Pynab update")
        try:
            with (directory / "upgrade.log").open("w") as log:
                if os.geteuid() == 0:
                    os.fchown(
                        log.fileno(), repo.owner, repo.root.stat().st_gid
                    )
                os.chmod(directory / "upgrade.log", 0o600)
                subprocess.Popen(
                    [
                        "/usr/bin/python3",
                        "-m",
                        "nabcommon.update",
                        "upgrade",
                    ],
                    cwd=repo.root,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except OSError as error:
            write_status(
                directory, "error", "Could not start the update process."
            )
            raise UpdateError("Could not start the update process.") from error


if __name__ == "__main__":
    if sys.argv[1:] != ["upgrade"]:
        raise SystemExit("Usage: python3 -m nabcommon.update upgrade")
    try:
        run_upgrade(Path(__file__).resolve().parent.parent)
    except UpdateError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
