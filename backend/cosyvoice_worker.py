"""CosyVoice helper process.

CosyVoice's Apple Silicon port (mlx-audio-plus) installs a Python module with the same
name as the package the main server uses for Qwen3-TTS (mlx_audio), so the two can't live
in one environment. setup.sh gives CosyVoice its own: backend/.venv-cosyvoice. The server
starts this script with that Python and talks to it one JSON line at a time:

  -> {"cmd": "load"}
  <- {"ok": true}
  -> {"cmd": "synth", "text": "...", "ref_wav": "/path/ref.wav", "ref_text": "...", "out": "/path/out.wav"}
  <- {"ok": true, "sample_rate": 24000}
  <- {"ok": false, "error": "..."}            on any failure

Run with --fake to answer with a short tone instead of loading the model (used by tests).
"""

from __future__ import annotations

import json
import os
import sys
import wave

DEFAULT_MODEL = "mlx-community/CosyVoice2-0.5B-fp16"


def _write_wav(path: str, audio, rate: int) -> None:
    import numpy as np

    pcm = (np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm.tobytes())


class FakeModel:
    def synth(self, text, ref_wav, ref_text):
        import numpy as np

        t = np.arange(int(24000 * 0.3)) / 24000
        return 0.2 * np.sin(2 * np.pi * 220 * t), 24000


class CosyVoiceModel:
    def __init__(self, model_id: str):
        from mlx_audio.tts.utils import load_model

        self.model = load_model(model_id)

    def synth(self, text, ref_wav, ref_text):
        import mlx.core as mx
        import numpy as np
        import soundfile as sf

        audio, rate = sf.read(ref_wav, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if rate != 24000:  # CosyVoice wants its reference at 24 kHz
            from scipy.signal import resample

            audio = resample(audio, int(len(audio) * 24000 / rate)).astype("float32")
        results = list(
            self.model.generate(text=text, ref_audio=mx.array(audio), ref_text=ref_text or None, verbose=False)
        )
        if not results:
            raise RuntimeError("CosyVoice returned no audio.")
        out = np.concatenate([np.asarray(r.audio, dtype=np.float32).reshape(-1) for r in results])
        return out, int(results[0].sample_rate)


def main() -> None:
    # Keep the reply channel clean: anything the model prints goes to stderr instead.
    reply = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1)
    sys.stdout = sys.stderr
    fake = "--fake" in sys.argv
    model_id = os.environ.get("SILENTVOICE_COSYVOICE_MODEL", DEFAULT_MODEL)
    model = None

    def send(obj):
        reply.write(json.dumps(obj) + "\n")
        reply.flush()

    for line in sys.stdin:
        try:
            req = json.loads(line)
            if model is None:
                model = FakeModel() if fake else CosyVoiceModel(model_id)
            if req.get("cmd") == "load":
                send({"ok": True})
            elif req.get("cmd") == "synth":
                audio, rate = model.synth(req["text"], req["ref_wav"], req.get("ref_text", ""))
                _write_wav(req["out"], audio, rate)
                send({"ok": True, "sample_rate": rate})
            else:
                send({"ok": False, "error": f"Unknown command {req.get('cmd')!r}"})
        except Exception as exc:  # report and keep serving
            send({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    main()
