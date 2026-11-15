"""Tests for audio device management and WAV playback helper."""

import io
import wave
import pytest
import numpy as np

from audio_device import (
    AudioDeviceError,
    find_device_index,
    list_audio_devices,
    play_wav_to_device,
    wav_bytes_to_numpy,
)


def _make_dummy_wav(duration_s=0.1, sample_rate=16000, n_channels=1, sampwidth=2):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        # Generate simple sine wave
        t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
        sig = (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
        wf.writeframes(sig.tobytes())
    return buf.getvalue()


def test_wav_bytes_to_numpy():
    wav_bytes = _make_dummy_wav(duration_s=0.05, sample_rate=8000, n_channels=1, sampwidth=2)
    data, sr = wav_bytes_to_numpy(wav_bytes)
    assert sr == 8000
    assert len(data) == 400
    assert data.dtype == np.int16


def test_wav_bytes_to_numpy_stereo():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        t = np.zeros(800, dtype=np.int16)
        wf.writeframes(t.tobytes())
    data, sr = wav_bytes_to_numpy(buf.getvalue())
    assert sr == 8000
    assert data.shape == (400, 2)


def test_wav_bytes_to_numpy_invalid():
    with pytest.raises(Exception):
        wav_bytes_to_numpy(b"not a real wav file")


def test_list_audio_devices():
    res = list_audio_devices()
    assert "devices" in res
    assert "blackhole_detected" in res
    assert isinstance(res["devices"], list)


def test_find_device_index():
    # If no blackhole, find_device_index("auto") returns None gracefully
    idx = find_device_index("auto")
    assert idx is None or isinstance(idx, (int, str))

    idx_int = find_device_index(3)
    assert idx_int == 3
