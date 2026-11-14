"""The Mac's own voices (the `say` command), rendered to a WAV file.

Browsers can't send their built-in speech to a chosen speaker, but they can play a WAV file
on any speaker, including Bluetooth ones. So when the user's own voice isn't set up, the
sentence is spoken by macOS into a file here and played by the browser on the chosen speaker.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache

_LINE = re.compile(r"^(?P<name>.+?)\s+(?P<lang>[a-z]{2,3}[_-][A-Za-z0-9_]+)\s+#")


def available() -> bool:
    return platform.system() == "Darwin" and shutil.which("say") is not None


def parse_voice_list(output: str) -> list[dict]:
    """Parse `say -v '?'`. Lines look like: 'Samantha            en_US    # Hello, my name is Samantha.'"""
    voices = []
    for line in output.splitlines():
        m = _LINE.match(line.strip())
        if m:
            voices.append({"name": m.group("name").strip(), "lang": m.group("lang").replace("_", "-")})
    return voices


@lru_cache(maxsize=1)
def list_voices() -> list[dict]:
    if not available():
        return []
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    voices = [v for v in parse_voice_list(out) if v["lang"].lower().startswith("en")]
    return sorted(voices, key=lambda v: v["name"].lower())


def speak_to_wav(text: str, voice: str = "", rate: float = 1.0) -> bytes:
    """Render `text` with macOS `say`. rate 1.0 is a normal speaking pace (~180 words a minute)."""
    if not available():
        raise RuntimeError("The Mac voice is only available on macOS.")
    names = {v["name"] for v in list_voices()}
    wpm = int(max(90, min(320, 180 * float(rate or 1.0))))
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "text.txt")
        dst = os.path.join(tmp, "speech.wav")
        with open(src, "w", encoding="utf-8") as f:
            f.write(text)
        cmd = ["say", "-r", str(wpm), "-f", src, "-o", dst, "--file-format=WAVE", "--data-format=LEI16@22050"]
        if voice and voice in names:
            cmd[1:1] = ["-v", voice]
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        with open(dst, "rb") as f:
            return f.read()
