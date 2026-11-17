#!/bin/bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "$0")"
[[ $(uname -m) == armv6l ]] || { echo 'Original Zero W ARMv6 required.' >&2; exit 1; }
. /etc/os-release
[[ ${VERSION_CODENAME:-} == trixie && ${VERSION_ID:-} == 13 && $EUID -ne 0 ]] || { echo 'Run as the Pynab checkout owner on Trixie, without sudo.' >&2; exit 1; }
[[ $(venv/bin/python -c 'import sys; print(sys.version_info[:2] == (3, 13))') == True ]]
[[ ! -e nabd/asr-fr ]] || { echo 'French model already exists; inspect it before replacing it.' >&2; exit 1; }

downloads=${1:-$(mktemp -d)}
stage=$(mktemp -d "$PWD/nabd/.asr-fr.XXXXXX")
cleanup() {
    rm -rf -- "$stage"
    if [[ $temporary_downloads == yes ]]; then rm -rf -- "$downloads"; fi
}
temporary_downloads=no
[[ $# -gt 0 ]] || temporary_downloads=yes
trap cleanup EXIT
mkdir -p -- "$downloads"
downloads=$(cd -- "$downloads" && pwd)
fetch() {
    local name=$1 url=$2 digest=$3
    if [[ ! -f $downloads/$name ]]; then
        curl --fail --location --silent --show-error --connect-timeout 15 --max-time 300 \
            "$url" -o "$downloads/$name"
    fi
    printf '%s  %s\n' "$digest" "$downloads/$name" | sha256sum --check --status
}
base=https://downloads.sourceforge.net/project/cmusphinx/Acoustic%20and%20Language%20Models/French
wheel=pocketsphinx-5.1.1-cp313-cp313-linux_armv6l.whl
fetch "$wheel" "https://www.piwheels.org/simple/pocketsphinx/$wheel" c4ffb06b4a21aca0127e77dee734a0a18fe6d3edcbed6db8452488ddc7e56d87
fetch cmusphinx-fr-ptm-5.2.tar.gz "$base/cmusphinx-fr-ptm-5.2.tar.gz" 6f07f5eaf9b90a1b011c2f8c12a778098325c7e749a6a99357c157f3666f77fd
fetch fr.dict "$base/fr.dict" 40b31d1b22c4e93eb35a742dc5bf0cd4243c5966f3f306b600016a43ff55e5ec
fetch LICENSE "$base/LICENSE" 11e3c35cb4439d0086b5cc9309b31ab00185a7b10bb1f584e042769d0d78302c
# Stream this pinned wheel to keep installation memory bounded on the Zero W.
venv/bin/python - "$downloads" "$stage" <<'PY'
import asyncio
import os
import pathlib
import shutil
import sys
import sysconfig
import tarfile
import zipfile

downloads, stage = map(pathlib.Path, sys.argv[1:])
site = pathlib.Path(sysconfig.get_path("platlib"))
with zipfile.ZipFile(downloads / "pocketsphinx-5.1.1-cp313-cp313-linux_armv6l.whl") as archive:
    for info in archive.infolist():
        path = pathlib.PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or path.parts[0] not in (
            "pocketsphinx", "pocketsphinx-5.1.1.dist-info"
        ):
            raise RuntimeError("Unexpected wheel path")
        destination = site / path
        if info.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".partial")
        with archive.open(info) as source, temporary.open("wb") as output:
            shutil.copyfileobj(source, output, length=128 * 1024)
        os.replace(temporary, destination)

from nabd.asr import ASR
from nabd.nlu import NLU

(stage / "DICTIONARY-LICENSE").write_bytes((downloads / "LICENSE").read_bytes())
with tarfile.open(downloads / "cmusphinx-fr-ptm-5.2.tar.gz") as archive:
    archive.extractall(stage, filter="data")
(stage / "cmusphinx-fr-ptm-5.2").rename(stage / "acoustic")
words = set(" ".join([*NLU.PHRASES, "et"]).split())
entries = [
    line for line in (downloads / "fr.dict").read_text(encoding="utf-8").splitlines()
    if line and line.split()[0].split("(")[0] in words
]
pronunciations = {}
for line in entries:
    word, phones = line.split(maxsplit=1)
    pronunciations.setdefault(word.split("(")[0], []).append(phones)
for word, phones in ASR.PRONUNCIATIONS.items():
    if word not in pronunciations:
        entries.append(f"{word} {phones}")
        pronunciations[word] = [phones]
if words - pronunciations.keys():
    raise RuntimeError(f"Missing French pronunciations: {words - pronunciations.keys()}")
(stage / "commands.dict").write_text("\n".join(entries) + "\n", encoding="utf-8")
# KWS uses only the first pronunciation, including liaison in 'est-il'.
preferred = {"est": 3, "moi": 1, "ton": 2, "météo": 1}
(stage / "keywords.dict").write_text("".join(
    word + " " + ASR.PRONUNCIATIONS.get(word, phones[preferred.get(word, 0)]) + "\n"
    for word, phones in pronunciations.items()
), encoding="utf-8")
ASR.MODEL_PATH = stage
async def check():
    asr = ASR("fr_FR")
    try:
        await asr.start()
    finally:
        await asr.close()
asyncio.run(check())
stage.rename(stage.with_name("asr-fr"))
print("French offline voice model ready. Restart nabd to enable it.")
PY
