"""Local voice-cloning engines.

Default: Qwen3-TTS (Alibaba, Apache 2.0) through mlx-audio, running on the Mac's
Apple Silicon GPU. It clones a voice from a few seconds of reference audio plus the
transcript of that audio. Nothing is sent over the network after the first model
download from Hugging Face.

Second engine: CosyVoice 2 (Alibaba FunAudioLLM, Apache 2.0) through mlx-audio-plus. Its
package clashes with mlx-audio, so it runs in its own environment (backend/.venv-cosyvoice)
as a helper process; see cosyvoice_worker.py. The user picks one in Settings > Voice.

Environment overrides:
  SILENTVOICE_VOICE_MODEL   default mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16
                            (higher quality, slower: mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16)
  SILENTVOICE_STT_MODEL     default mlx-community/whisper-large-v3-turbo-asr-fp16
  SILENTVOICE_COSYVOICE_MODEL  default mlx-community/CosyVoice2-0.5B-fp16
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Protocol

import numpy as np

from mlx_guard import MLX_LOCK

BACKEND_DIR = Path(__file__).resolve().parent
COSYVOICE_PYTHON = BACKEND_DIR / ".venv-cosyvoice" / "bin" / "python"
DEFAULT_COSYVOICE_MODEL = "mlx-community/CosyVoice2-0.5B-fp16"

DEFAULT_VOICE_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
DEFAULT_STT_MODEL = "mlx-community/whisper-large-v3-turbo-asr-fp16"


class EngineUnavailable(RuntimeError):
    pass


class VoiceEngine(Protocol):
    name: str
    model_id: str

    def availability(self) -> tuple[bool, str]: ...

    def load(self) -> None: ...

    def synthesize(self, text: str, ref_wav: str, ref_text: str) -> tuple[np.ndarray, int]: ...

    def transcribe(self, wav_path: str) -> str: ...


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


class Qwen3MLXEngine:
    """Qwen3-TTS Base model via mlx-audio (Apple Silicon only)."""

    name = "Qwen3-TTS"

    def __init__(self, model_id: str | None = None, stt_model_id: str | None = None):
        self.model_id = model_id or os.environ.get("SILENTVOICE_VOICE_MODEL", DEFAULT_VOICE_MODEL)
        self.stt_model_id = stt_model_id or os.environ.get("SILENTVOICE_STT_MODEL", DEFAULT_STT_MODEL)
        self._model = None
        self._stt = None
        self._lock = MLX_LOCK  # MLX models are not safe to call from two threads at once

    def availability(self) -> tuple[bool, str]:
        if not _is_apple_silicon():
            return False, "Your own voice runs on Apple Silicon Macs (M1 or newer)."
        try:
            import mlx_audio  # noqa: F401
        except Exception:
            return False, "The voice package isn’t installed. Run ./setup.sh again."
        return True, ""

    def load(self) -> None:
        ok, why = self.availability()
        if not ok:
            raise EngineUnavailable(why)
        with self._lock:
            if self._model is None:
                from mlx_audio.tts.utils import load_model

                self._model = load_model(self.model_id)

    def synthesize(self, text: str, ref_wav: str, ref_text: str) -> tuple[np.ndarray, int]:
        self.load()
        with self._lock:
            results = list(self._model.generate(text=text, ref_audio=ref_wav, ref_text=ref_text))
        if not results:
            raise RuntimeError("The voice model returned no audio.")
        audio = np.concatenate([np.asarray(r.audio, dtype=np.float32).reshape(-1) for r in results])
        return audio, int(results[0].sample_rate)

    def transcribe(self, wav_path: str) -> str:
        ok, why = self.availability()
        if not ok:
            raise EngineUnavailable(why)
        with self._lock:
            if self._stt is None:
                from mlx_audio.stt import load

                self._stt = load(self.stt_model_id)
            result = self._stt.generate(wav_path)
        return " ".join(str(getattr(result, "text", "")).split())


class CosyVoiceEngine:
    """CosyVoice 2 via mlx-audio-plus, in a helper process with its own Python environment."""

    name = "CosyVoice 2"

    def __init__(self, model_id: str | None = None, python: str | Path | None = None, transcriber=None, fake: bool = False):
        self.model_id = model_id or os.environ.get("SILENTVOICE_COSYVOICE_MODEL", DEFAULT_COSYVOICE_MODEL)
        self.python = Path(python or COSYVOICE_PYTHON)
        self.fake = fake
        self._transcriber = transcriber or Qwen3MLXEngine()  # Whisper from the main environment
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def availability(self) -> tuple[bool, str]:
        if not self.fake and not _is_apple_silicon():
            return False, "CosyVoice runs on Apple Silicon Macs (M1 or newer)."
        if not self.python.exists():
            return False, "CosyVoice isn’t installed yet. Run ./setup.sh again to add it."
        return True, ""

    def _request(self, payload: dict, timeout: float = 600) -> dict:
        if self._proc is None or self._proc.poll() is not None:
            cmd = [str(self.python), str(BACKEND_DIR / "cosyvoice_worker.py")] + (["--fake"] if self.fake else [])
            env = {**os.environ, "SILENTVOICE_COSYVOICE_MODEL": self.model_id}
            self._proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, bufsize=1, env=env
            )
        assert self._proc.stdin and self._proc.stdout
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError("The CosyVoice helper stopped. Check the server window for details.")
        reply = json.loads(line)
        if not reply.get("ok"):
            raise RuntimeError(reply.get("error") or "CosyVoice failed.")
        return reply

    def load(self) -> None:
        ok, why = self.availability()
        if not ok:
            raise EngineUnavailable(why)
        # The helper is a separate process, but it still uses the same GPU: take turns.
        with self._lock, MLX_LOCK:
            self._request({"cmd": "load"})

    def synthesize(self, text: str, ref_wav: str, ref_text: str) -> tuple[np.ndarray, int]:
        import wave

        self.load()
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "out.wav")
            with self._lock, MLX_LOCK:
                self._request({"cmd": "synth", "text": text, "ref_wav": ref_wav, "ref_text": ref_text, "out": out})
            with wave.open(out, "rb") as w:
                rate = w.getframerate()
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        return pcm.astype(np.float32) / 32767.0, rate

    def transcribe(self, wav_path: str) -> str:
        return self._transcriber.transcribe(wav_path)

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


ENGINES = {"qwen3": Qwen3MLXEngine, "cosyvoice": CosyVoiceEngine}


def default_engine() -> VoiceEngine:
    return Qwen3MLXEngine()
