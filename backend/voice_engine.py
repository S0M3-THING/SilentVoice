"""Local voice-cloning engines.

Default: Qwen3-TTS (Alibaba, Apache 2.0) through mlx-audio, running on the Mac's
Apple Silicon GPU. It clones a voice from a few seconds of reference audio plus the
transcript of that audio. Nothing is sent over the network after the first model
download from Hugging Face.

The engine sits behind a tiny interface so another open model (for example Chatterbox,
MIT) can be dropped in later without touching the rest of the app.

Environment overrides:
  SILENTVOICE_VOICE_MODEL   default mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16
                            (higher quality, slower: mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16)
  SILENTVOICE_STT_MODEL     default mlx-community/whisper-large-v3-turbo-asr-fp16
"""

from __future__ import annotations

import os
import platform
import threading
from typing import Protocol

import numpy as np

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
        self._lock = threading.Lock()  # MLX models are not safe to call from two threads at once

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


def default_engine() -> VoiceEngine:
    return Qwen3MLXEngine()
