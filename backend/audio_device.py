"""Audio device management and routing for SilentVoice virtual microphone integration.

Supports macOS virtual audio loopback drivers (specifically BlackHole 2ch) to route
synthesized speech directly into Zoom or other meeting applications as microphone input.
"""

from __future__ import annotations

import io
import logging
import wave
from typing import Any

import numpy as np

logger = logging.getLogger("silentvoice.audio")

try:
    import sounddevice as sd
except Exception as exc:  # pragma: no cover
    sd = None
    logger.warning("sounddevice could not be imported: %s", exc)


class AudioDeviceError(Exception):
    """Raised when an audio output device cannot be found or opened."""
    pass


def wav_bytes_to_numpy(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """Parse standard RIFF/WAV bytes into a NumPy array and sample rate."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)

    if sampwidth == 1:
        dtype = np.uint8
    elif sampwidth == 2:
        dtype = np.int16
    elif sampwidth == 4:
        dtype = np.int32
    else:
        raise AudioDeviceError(f"Unsupported WAV sample width: {sampwidth} bytes")

    data = np.frombuffer(raw_data, dtype=dtype)
    if n_channels > 1:
        data = data.reshape(-1, n_channels)
    return data, framerate


def list_audio_devices() -> dict[str, Any]:
    """Enumerate audio devices on the host system, highlighting BlackHole devices."""
    devices: list[dict[str, Any]] = []
    blackhole_output: dict[str, Any] | None = None
    blackhole_input: dict[str, Any] | None = None

    if sd is not None:
        try:
            device_list = sd.query_devices()
            if isinstance(device_list, dict):
                device_list = [device_list]
            for idx, dev in enumerate(device_list):
                name = str(dev.get("name", ""))
                max_in = int(dev.get("max_input_channels", 0))
                max_out = int(dev.get("max_output_channels", 0))
                is_bh = "blackhole" in name.lower()

                item = {
                    "index": idx,
                    "name": name,
                    "max_input_channels": max_in,
                    "max_output_channels": max_out,
                    "default_samplerate": int(dev.get("default_samplerate", 44100)),
                    "is_blackhole": is_bh,
                }
                devices.append(item)
                if is_bh and max_out > 0 and blackhole_output is None:
                    blackhole_output = item
                if is_bh and max_in > 0 and blackhole_input is None:
                    blackhole_input = item
        except Exception as exc:
            logger.debug("Failed querying devices via sounddevice: %s", exc)

    blackhole_detected = (blackhole_output is not None or blackhole_input is not None)
    if not blackhole_detected:
        import os
        from pathlib import Path
        if Path("/Library/Audio/Plug-Ins/HAL/BlackHole2ch.driver").exists() or os.path.exists("/Library/Audio/Plug-Ins/HAL/BlackHole2ch.driver"):
            blackhole_detected = True

    return {
        "devices": devices,
        "blackhole_detected": blackhole_detected,
        "blackhole_output_device": blackhole_output,
        "blackhole_input_device": blackhole_input,
        "total_devices": len(devices),
    }


def find_device_index(target: str | int | None) -> int | str | None:
    """Find device index or name. If target is None or 'blackhole', attempts to match BlackHole."""
    if target is None or (isinstance(target, str) and target.lower() in ("blackhole", "auto")):
        # Auto-detect BlackHole output
        info = list_audio_devices()
        if info["blackhole_output_device"]:
            return info["blackhole_output_device"]["index"]
        return None

    if isinstance(target, int):
        return target

    # Try matching by name
    target_lower = str(target).lower().strip()
    info = list_audio_devices()
    for d in info["devices"]:
        if target_lower in d["name"].lower() and d["max_output_channels"] > 0:
            return d["index"]

    return target


def play_wav_to_device(wav_bytes: bytes, target_device: str | int | None = None) -> bool:
    """Route WAV audio directly to an audio output device (such as BlackHole 2ch)."""
    if sd is None:
        raise AudioDeviceError("sounddevice is not available on this system.")

    device_idx = find_device_index(target_device)
    data, samplerate = wav_bytes_to_numpy(wav_bytes)

    try:
        sd.play(data, samplerate=samplerate, device=device_idx)
        sd.wait()
        return True
    except Exception as exc:
        raise AudioDeviceError(f"Failed playing audio to device '{target_device}' ({device_idx}): {exc}") from exc
