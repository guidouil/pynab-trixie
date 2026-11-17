#!/usr/bin/env python3
"""Download and verify the pinned public inputs; optionally unpack driver sources."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK = HERE / "sources.lock.json"


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download(spec, target):
    if not spec["url"].startswith("https://") or not re.fullmatch(
        r"[0-9a-f]{64}", spec["sha256"]
    ):
        raise ValueError("HTTPS and SHA-256 are required")
    if target.exists():
        if target.is_symlink() or digest(target) != spec["sha256"]:
            raise ValueError(f"Cached input differs: {target}")
        return
    partial = target.with_name(target.name + ".partial")
    try:
        with urllib.request.urlopen(spec["url"], timeout=120) as source:
            with partial.open("xb") as output:
                shutil.copyfileobj(source, output, length=128 * 1024)
        if digest(partial) != spec["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {target.name}")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def unpack(archive, target):
    if target.exists():
        raise ValueError(f"Source destination must be new: {target}")
    target.mkdir()
    with tarfile.open(archive, "r:gz") as source:
        source.extractall(target, filter="data")
    roots = list(target.iterdir())
    if len(roots) != 1 or not roots[0].is_dir() or roots[0].is_symlink():
        raise ValueError("Expected one source directory")
    return roots[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument(
        "--base", action="store_true", help="also fetch official OS image"
    )
    parser.add_argument(
        "--prepare", type=Path, help="new or empty driver work directory"
    )
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text())
    args.cache.mkdir(parents=True, exist_ok=True)
    if args.base:
        download(lock["base"], args.cache / "raspios.img.xz")
    if args.prepare:
        args.prepare.mkdir(parents=True, exist_ok=True)
        if any(args.prepare.iterdir()):
            raise ValueError("Driver work directory must be empty")
    for name, spec in lock["drivers"].items():
        archive = args.cache / f"{name}.tar.gz"
        download(spec, archive)
        patch = HERE / "patches" / f"{name}.patch"
        if digest(patch) != spec["patch_sha256"]:
            raise ValueError(f"Patch checksum differs: {name}")
        if args.prepare:
            parent = args.prepare / f".{name}"
            root = unpack(archive, parent)
            subprocess.run(
                ["git", "apply", "--check", str(patch)], cwd=root, check=True
            )
            subprocess.run(["git", "apply", str(patch)], cwd=root, check=True)
            root.rename(args.prepare / name)
            parent.rmdir()
    print("Pinned inputs verified")


if __name__ == "__main__":
    main()
