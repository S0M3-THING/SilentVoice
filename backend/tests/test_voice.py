import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy.io import wavfile

from app import create_app
from store import Store
from voice import READING_PASSAGE, VoiceError, pick_reference


class FakeEngine:
    """Stands in for Qwen3-TTS so tests run anywhere, without downloading a model."""

    name = "Fake"
    model_id = "fake/model"

    def __init__(self, available=True, transcript="hello this is my voice"):
        self._available = available
        self._transcript = transcript
        self.synth_calls = []

    def availability(self):
        return (True, "") if self._available else (False, "Needs an Apple Silicon Mac.")

    def load(self):
        pass

    def synthesize(self, text, ref_wav, ref_text):
        self.synth_calls.append((text, ref_text))
        t = np.linspace(0, 0.5, 12000, endpoint=False)
        return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 24000

    def transcribe(self, wav_path):
        return self._transcript


def speech_like(seconds=10.0, rate=24000, gap_every=1.2):
    """Bursts of a modulated tone separated by short silences, like sentences."""
    t = np.arange(int(seconds * rate)) / rate
    tone = 0.4 * np.sin(2 * np.pi * 180 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    gate = ((t % gap_every) < gap_every * 0.75).astype(np.float32)
    return (tone * gate).astype(np.float32)


def wav_bytes(audio, rate=24000):
    buf = io.BytesIO()
    wavfile.write(buf, rate, (audio * 32767).astype(np.int16))
    return buf.getvalue()


@pytest.fixture
def client_engine(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    engine = FakeEngine()
    store = Store(tmp_path)
    client = TestClient(create_app(store=store, vsr_service=None, autoload=False, voice_engine=engine))
    return client, engine


def upload(client, data, **form):
    files = [("files", ("old_voicemail.wav", data, "audio/wav"))]
    fields = {"consent": "true", "source": "upload", **form}
    return client.post("/api/voice/reference", files=files, data=fields)


def test_pick_reference_keeps_speech_and_trims():
    rate = 24000
    audio = np.concatenate([np.zeros(3 * rate, np.float32), speech_like(20), np.zeros(3 * rate, np.float32)])
    clip, speech = pick_reference(audio, rate)
    assert 6 <= len(clip) / rate <= 15.5
    assert speech >= 6


def test_pick_reference_rejects_too_little_speech():
    with pytest.raises(VoiceError):
        pick_reference(speech_like(3), 24000)


def test_status_before_setup(client_engine):
    client, _ = client_engine
    s = client.get("/api/voice").json()
    assert s["has_voice"] is False and s["available"] is True
    assert s["reading_passage"] == READING_PASSAGE


def test_consent_is_required(client_engine):
    client, _ = client_engine
    resp = upload(client, wav_bytes(speech_like(10)), consent="false")
    assert resp.status_code == 400
    assert "permission" in resp.json()["detail"]


def test_upload_auto_transcribes_and_speaks_with_cache(client_engine):
    client, engine = client_engine
    s = upload(client, wav_bytes(speech_like(14))).json()
    assert s["has_voice"] is True
    assert s["transcript"] == "hello this is my voice" and s["transcript_source"] == "auto"
    assert 6 <= s["seconds"] <= 15.5
    assert client.get("/api/voice/reference").headers["content-type"] == "audio/wav"

    a = client.post("/api/tts", json={"text": "I need water."})
    assert a.status_code == 200 and a.headers["content-type"] == "audio/wav"
    client.post("/api/tts", json={"text": "I need water."})
    assert len(engine.synth_calls) == 1  # second time comes from the cache
    assert engine.synth_calls[0][1] == "hello this is my voice"


def test_recording_uses_reading_passage(client_engine):
    client, _ = client_engine
    s = upload(client, wav_bytes(speech_like(12)), source="recording").json()
    assert s["transcript"] == READING_PASSAGE and s["transcript_source"] == "passage"


def test_edit_transcript_clears_cache(client_engine):
    client, engine = client_engine
    upload(client, wav_bytes(speech_like(12)), transcript="this is what I said")
    client.post("/api/tts", json={"text": "Hello."})
    s = client.put("/api/voice/transcript", json={"transcript": "this is what I really said"}).json()
    assert s["transcript"] == "this is what I really said" and s["cached_phrases"] == 0
    client.post("/api/tts", json={"text": "Hello."})
    assert len(engine.synth_calls) == 2


def test_too_short_recording_is_rejected(client_engine):
    client, _ = client_engine
    resp = upload(client, wav_bytes(speech_like(3)))
    assert resp.status_code == 400 and "seconds" in resp.json()["detail"]


def test_unreadable_file_is_rejected(client_engine):
    client, _ = client_engine
    resp = upload(client, b"not audio at all")
    assert resp.status_code == 400


def test_delete_removes_everything(client_engine):
    client, _ = client_engine
    upload(client, wav_bytes(speech_like(12)))
    s = client.delete("/api/voice").json()
    assert s["has_voice"] is False
    assert client.get("/api/voice/reference").status_code == 404
    assert client.post("/api/tts", json={"text": "Hi"}).status_code == 400


def test_unavailable_engine_explains_why(tmp_path):
    client = TestClient(create_app(store=Store(tmp_path), autoload=False, voice_engine=FakeEngine(available=False)))
    s = client.get("/api/voice").json()
    assert s["available"] is False and s["engine_state"] == "unavailable"
    resp = upload(client, wav_bytes(speech_like(12)))
    assert resp.status_code == 400 and "Apple Silicon" in resp.json()["detail"]
