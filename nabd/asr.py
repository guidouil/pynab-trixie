"""Bounded, offline French commands using PocketSphinx on the original Zero W."""

import asyncio
import json
import struct
import sys
import tempfile
import threading
from pathlib import Path

from pocketsphinx import Decoder

from .nlu import NLU


class ASR:
    MODEL_PATH = Path(__file__).with_name("asr-fr")
    MAX_BYTES = (
        16 * 16000 * 2
    )  # Allow the final audio period after the 15s timer.
    ANCHORS = {
        "quelle heure": ("clock", 1e-20),
        "heure": ("clock", 1e-5),
        "météo": ("weather", 1e-5),
        "quel temps": ("weather", 1e-20),
        "comment vas": ("mood", 1e-20),
        "comment ça va": ("mood", 1e-20),
        "humeur": ("mood", 1e-5),
        "penses quoi": ("8ball", 1e-20),
    }

    @staticmethod
    def get_locale(locale):
        return NLU.DEFAULT_LOCALE

    def __init__(self, locale):
        self._buffer_lock = threading.Lock()
        self._worker_lock = asyncio.Lock()
        self._process = None
        self.reset()
        model = self.MODEL_PATH
        if not (model / "acoustic").is_dir() or not all(
            (model / name).is_file()
            for name in ("commands.dict", "keywords.dict")
        ):
            raise ImportError(
                "Run install-native-asr.sh to install the French voice model"
            )

    def _load_decoders(self):
        model = self.MODEL_PATH
        options = {
            "hmm": str(model / "acoustic"),
            "lm": None,
            "loglevel": "FATAL",
        }
        self._grammar = Decoder(dict=str(model / "commands.dict"), **options)
        self._keywords = Decoder(dict=str(model / "keywords.dict"), **options)
        for decoder in (self._grammar, self._keywords):
            for word, phones in NLU.EXTRA_PRONUNCIATIONS.items():
                if decoder.lookup_word(word) is None:
                    decoder.add_word(word, phones)
        grammar = (
            "#JSGF V1.0; grammar commands; public <request> = "
            "<command> | <command> et <command>; <command> = "
            + " | ".join(NLU.PHRASES)
            + ";"
        )
        self._grammar.add_jsgf_string("commands", grammar)
        self._grammar.activate_search("commands")
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8"
        ) as keywords:
            for phrase, (_, threshold) in self.ANCHORS.items():
                keywords.write(f"{phrase} /{threshold}/\n")
            keywords.flush()
            self._keywords.add_kws("commands", keywords.name)
        self._keywords.activate_search("commands")

    def reset(self):
        with self._buffer_lock:
            self._pcm = bytearray()
            self._valid = True
            self._finalized = False

    def decode_chunk(self, samples, finalize):
        with self._buffer_lock:
            if (
                self._finalized
                or len(samples) % 2
                or len(self._pcm) + len(samples) > self.MAX_BYTES
            ):
                self._valid = False
            if self._valid:
                self._pcm.extend(samples)
            self._finalized = finalize

    async def get_decoded_string(self, sync=True):
        with self._buffer_lock:
            pcm = bytes(self._pcm) if self._valid and self._finalized else b""
            self._pcm.clear()
            self._valid = False
        if len(pcm) < 6400:
            return ""
        return await self._decode(pcm)

    async def start(self):
        async with self._worker_lock:
            await self._start_worker()

    async def _start_worker(self):
        if self._process is not None:
            if self._process.returncode is None:
                return
            await self._stop_worker()
        # PocketSphinx holds the GIL; a child keeps nabd responsive.
        self._process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "nabd.asr",
            str(self.MODEL_PATH.resolve()),
            cwd=str(Path(__file__).resolve().parent.parent),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            limit=4096,
        )
        try:
            line = await asyncio.wait_for(
                self._process.stdout.readline(), timeout=120
            )
            response = json.loads(line)
            if response != {"ready": True}:
                raise RuntimeError(
                    f"French voice decoder failed: {str(response)[:500]}"
                )
        except BaseException:
            await self._stop_worker()
            raise

    async def _decode(self, pcm):
        async with self._worker_lock:
            await self._start_worker()
            try:
                async with asyncio.timeout(60):
                    self._process.stdin.write(
                        struct.pack("!I", len(pcm)) + pcm
                    )
                    await self._process.stdin.drain()
                    line = await self._process.stdout.readline()
                response = json.loads(line)
                if "error" in response:
                    detail = str(response["error"])[:500]
                    raise RuntimeError(
                        f"French voice decoder failed: {detail}"
                    )
                text = response["text"]
                if not isinstance(text, str) or (
                    text and text not in NLU.PHRASES
                ):
                    raise RuntimeError("Invalid French voice decoder response")
                return text
            except BaseException:
                await self._stop_worker()
                raise

    async def _stop_worker(self):
        process, self._process = self._process, None
        if process is None:
            return
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.wait()

    async def close(self):
        async with self._worker_lock:
            await self._stop_worker()

    def _decode_sync(self, pcm):
        if len(pcm) > self.MAX_BYTES or len(pcm) % 2 or len(pcm) < 6400:
            return ""
        if not hasattr(self, "_grammar"):
            self._load_decoders()
        # KWS needs initial silence and a final delay to detect boundary words.
        padded = b"\0" * 9600 + pcm + b"\0" * 9600
        for decoder in (self._grammar, self._keywords):
            decoder.start_utt()
            try:
                decoder.process_raw(padded, False, True)
            finally:
                decoder.end_utt()
        hypothesis = self._grammar.hyp()
        text = hypothesis.hypstr if hypothesis else ""
        command = NLU.PHRASES.get(text)
        if command is None:
            return ""
        kind = "weather" if command == "tomorrow" else command
        detected = {
            self.ANCHORS[segment.word.strip()][0]
            for segment in self._keywords.seg() or []
            if segment.word.strip() in self.ANCHORS
        }
        # A grammar alone forces unrelated speech into a valid command.
        return text if kind in detected else ""


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m nabd.asr MODEL_PATH")
    ASR.MODEL_PATH = Path(sys.argv[1])
    try:
        asr = ASR("fr_FR")
        asr._load_decoders()
        asr._decode_sync(b"\0" * 6400)
    except Exception as error:
        print(json.dumps({"error": str(error)[:500]}), flush=True)
        return 1
    print(json.dumps({"ready": True}), flush=True)
    while True:
        header = sys.stdin.buffer.read(4)
        if not header:
            return 0
        if len(header) != 4:
            raise SystemExit("Truncated PCM header")
        length = struct.unpack("!I", header)[0]
        if length > ASR.MAX_BYTES or length % 2:
            raise SystemExit("Invalid PCM length")
        pcm = sys.stdin.buffer.read(length)
        if len(pcm) != length:
            raise SystemExit("Truncated PCM data")
        try:
            response = {"text": asr._decode_sync(pcm)}
        except Exception as error:
            response = {"error": str(error)[:500]}
        del pcm
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
