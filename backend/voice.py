"""Speak in the user's own voice, fully on this computer.

Flow:
1. The user either reads a short passage aloud (we know the transcript), or uploads old
   recordings of their voice (voicemails, videos). Consent is required either way.
2. ffmpeg cleans the audio (rumble filter, noise reduction, loudness), and we keep the
   clearest 6 to 15 seconds of speech as the reference clip.
3. If we don't have a transcript, the local Whisper model writes one, which the user can
   correct in Settings (a wrong transcript makes the copy sound worse).
4. Each sentence is synthesised by the local voice engine (Qwen3-TTS by default) and cached,
   so phrases said once replay instantly.

Files live in backend/data/voice/ (git-ignored). Deleting the voice removes all of them.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from voice_engine import EngineUnavailable, VoiceEngine, default_engine

REF_RATE = 24000
MIN_SPEECH_SECONDS = 5.0
TARGET_SECONDS = 12.0
MAX_SECONDS = 15.0

READING_PASSAGE = (
    "The sun was setting over the hills as we walked home. "
    "I asked my sister to pass the bread, and we laughed about the long day. "
    "Tomorrow I would like a cup of tea and a quiet morning."
)


class VoiceError(RuntimeError):
    pass


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if not Path(exe).exists() and not shutil.which(exe):
        raise VoiceError("ffmpeg is missing. Install it with: brew install ffmpeg")
    return exe


def clean_to_wav(src: Path, dst: Path) -> None:
    """Any audio/video file -> 24 kHz mono 16-bit wav, de-rumbled, de-noised, loudness-normalised."""
    cmd = [
        _ffmpeg(), "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", str(REF_RATE),
        "-af", "highpass=f=70,afftdn=nf=-25,loudnorm=I=-20:TP=-2:LRA=11",
        "-sample_fmt", "s16", str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0 or not dst.exists():
        raise VoiceError("Couldn’t read that recording. Try an MP3, M4A, WAV or video file.")


def _read_mono(path: Path) -> np.ndarray:
    rate, data = wavfile.read(str(path))
    if data.ndim > 1:
        data = data.mean(axis=1)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    else:
        data = data.astype(np.float32)
    if rate != REF_RATE:
        raise VoiceError("Unexpected sample rate after conversion.")
    return data


def pick_reference(audio: np.ndarray, rate: int = REF_RATE) -> tuple[np.ndarray, float]:
    """Choose the clearest stretch of speech, 6 to 15 seconds long.

    Speech frames are found with a relative energy threshold; we then slide a window
    over the recording and keep the one with the most speech and no clipping.
    Returns (clip, seconds_of_speech_in_clip).
    """
    frame = int(0.025 * rate)
    n_frames = len(audio) // frame
    if n_frames == 0:
        raise VoiceError("That recording is empty.")
    frames = audio[: n_frames * frame].reshape(n_frames, frame)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    peak = np.abs(frames).max(axis=1)
    floor = np.percentile(rms, 20)
    loud = np.percentile(rms, 95)
    threshold = max(floor * 3.0, loud * 0.12, 1e-3)
    voiced = rms > threshold
    clipped = peak > 0.99

    speech_seconds = voiced.sum() * 0.025
    if speech_seconds < MIN_SPEECH_SECONDS:
        raise VoiceError(
            f"We found about {speech_seconds:.0f} seconds of clear speech. "
            f"Add recordings with at least {MIN_SPEECH_SECONDS:.0f} seconds of your voice."
        )

    win = min(n_frames, int(TARGET_SECONDS / 0.025))
    score = voiced.astype(np.float32) - 2.0 * clipped.astype(np.float32)
    csum = np.concatenate([[0.0], np.cumsum(score)])
    best_start = int(np.argmax(csum[win:] - csum[:-win])) if n_frames > win else 0
    start, end = best_start, best_start + win

    # Trim leading/trailing silence, keep 0.2 s of padding.
    idx = np.where(voiced[start:end])[0]
    pad = 8
    s = max(0, start + idx[0] - pad)
    e = min(n_frames, start + idx[-1] + 1 + pad)
    e = min(e, s + int(MAX_SECONDS / 0.025))
    clip = audio[s * frame : e * frame]
    return clip, float(voiced[s:e].sum() * 0.025)


def _to_wav_bytes(audio: np.ndarray, rate: int) -> bytes:
    pcm = np.clip(audio, -1.0, 1.0)
    buf = io.BytesIO()
    wavfile.write(buf, rate, (pcm * 32767).astype(np.int16))
    return buf.getvalue()


class VoiceService:
    def __init__(self, store, engine: VoiceEngine | None = None):
        self.store = store
        self.engine = engine or default_engine()
        self.dir = store.dir / "voice"
        self.cache_dir = self.dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ref_path = self.dir / "reference.wav"
        self.profile_path = self.dir / "profile.json"
        self.engine_state = "idle"  # idle | loading | ready | error
        self.engine_error = ""
        self._state_lock = threading.Lock()

    # ------------------------------------------------------------------ profile
    def _profile(self) -> dict:
        try:
            return json.loads(self.profile_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_profile(self, data: dict) -> None:
        self.profile_path.write_text(json.dumps(data, indent=2))

    def has_voice(self) -> bool:
        return self.ref_path.exists() and bool(self._profile().get("transcript"))

    def status(self) -> dict:
        ok, why = self.engine.availability()
        prof = self._profile()
        return {
            "engine": self.engine.name,
            "model": self.engine.model_id,
            "available": ok,
            "unavailable_reason": why,
            "engine_state": self.engine_state if ok else "unavailable",
            "engine_error": self.engine_error,
            "has_voice": self.has_voice(),
            "seconds": prof.get("seconds"),
            "transcript": prof.get("transcript", ""),
            "transcript_source": prof.get("transcript_source", ""),
            "created_at": prof.get("created_at"),
            "cached_phrases": len(list(self.cache_dir.glob("*.wav"))),
            "reading_passage": READING_PASSAGE,
        }

    # ------------------------------------------------------------------ engine
    def warm_up(self) -> None:
        """Load the model in the background so the first sentence isn't slow."""
        ok, _ = self.engine.availability()
        with self._state_lock:
            if not ok or self.engine_state in ("loading", "ready"):
                return
            self.engine_state = "loading"
            self.engine_error = ""

        def run():
            try:
                self.engine.load()
                self.engine_state = "ready"
            except Exception as exc:  # pragma: no cover - depends on the local machine
                self.engine_state = "error"
                self.engine_error = f"{type(exc).__name__}: {exc}"

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------------ reference
    def create(self, files: list[tuple[str, bytes]], transcript: str, consent: bool, source: str) -> dict:
        if not consent:
            raise VoiceError("Please confirm this is your own voice, or that you have permission to use it.")
        if not files:
            raise VoiceError("Add at least one recording.")
        ok, why = self.engine.availability()
        if not ok:
            raise VoiceError(why)

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            pieces = []
            for i, (name, data) in enumerate(files[:10]):
                src = tmpdir / f"in{i}{Path(name or 'clip').suffix or '.bin'}"
                src.write_bytes(data)
                out = tmpdir / f"clean{i}.wav"
                clean_to_wav(src, out)
                pieces.append(_read_mono(out))
                pieces.append(np.zeros(int(0.3 * REF_RATE), dtype=np.float32))
            audio = np.concatenate(pieces)
            clip, seconds = pick_reference(audio)

            ref_tmp = tmpdir / "reference.wav"
            ref_tmp.write_bytes(_to_wav_bytes(clip, REF_RATE))

            transcript = " ".join((transcript or "").split())
            transcript_source = "given" if transcript else "auto"
            if source == "recording" and not transcript:
                transcript, transcript_source = READING_PASSAGE, "passage"
            if not transcript:
                try:
                    transcript = self.engine.transcribe(str(ref_tmp))
                except EngineUnavailable as exc:
                    raise VoiceError(str(exc)) from exc
                except Exception as exc:
                    raise VoiceError(
                        "Couldn’t write down what’s said in the recording. Type it in and try again."
                    ) from exc
                if not transcript:
                    raise VoiceError("No words were found in the recording. Try a clearer one.")

            self.dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ref_tmp, self.ref_path)

        self.clear_cache()
        self._save_profile(
            {
                "transcript": transcript,
                "transcript_source": transcript_source,
                "seconds": round(len(clip) / REF_RATE, 1),
                "speech_seconds": round(seconds, 1),
                "consent": True,
                "created_at": time.time(),
                "model": self.engine.model_id,
            }
        )
        self.warm_up()
        return self.status()

    def set_transcript(self, transcript: str) -> dict:
        transcript = " ".join((transcript or "").split())
        if not transcript:
            raise VoiceError("The transcript can’t be empty.")
        if not self.ref_path.exists():
            raise VoiceError("Set up your voice first.")
        prof = self._profile()
        prof.update(transcript=transcript, transcript_source="edited")
        self._save_profile(prof)
        self.clear_cache()
        return self.status()

    def delete(self) -> dict:
        self.ref_path.unlink(missing_ok=True)
        self.profile_path.unlink(missing_ok=True)
        self.clear_cache()
        return self.status()

    def clear_cache(self) -> None:
        for f in self.cache_dir.glob("*.wav"):
            f.unlink(missing_ok=True)

    # ------------------------------------------------------------------ speech
    def _cache_path(self, text: str) -> Path:
        prof = self._profile()
        key = f"{self.engine.model_id}|{prof.get('created_at')}|{prof.get('transcript')}|{text.strip().lower()}"
        return self.cache_dir / f"{hashlib.sha1(key.encode()).hexdigest()}.wav"

    def speak(self, text: str) -> bytes:
        text = " ".join((text or "").split())
        if not text:
            raise VoiceError("Nothing to say.")
        if not self.has_voice():
            raise VoiceError("Set up your voice first.")
        cached = self._cache_path(text)
        if cached.exists():
            return cached.read_bytes()
        try:
            audio, rate = self.engine.synthesize(text[:500], str(self.ref_path), self._profile()["transcript"])
        except EngineUnavailable as exc:
            raise VoiceError(str(exc)) from exc
        self.engine_state = "ready"
        data = _to_wav_bytes(audio, rate)
        cached.write_bytes(data)
        return data
