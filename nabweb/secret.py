"""Keep each installation's Django signing key outside Git."""

import os
import secrets
import tempfile
from pathlib import Path


def installation_secret(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("The Django signing key must be a regular file")
    if not path.exists():
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=path.parent, delete=False
            ) as output:
                temporary = output.name
                output.write(secrets.token_urlsafe(64) + "\n")
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            if temporary is not None:
                os.unlink(temporary)
    if path.is_symlink() or not path.is_file():
        raise ValueError("The Django signing key must be a regular file")
    key = path.read_text().strip()
    if len(key) < 50:
        raise ValueError("The Django signing key is too short")
    return key
