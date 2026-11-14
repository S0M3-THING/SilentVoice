import pytest
from fastapi.testclient import TestClient

from app import create_app
from store import Store


class FakeVSR:
    device = "cpu"

    def __init__(self, candidates):
        self.candidates = candidates

    def transcribe_video_bytes(self, raw_bytes, suffix, mode, top_k, hflip, enhance):
        assert raw_bytes
        return {
            "candidates": self.candidates,
            "frames": 50,
            "face_ratio": 1.0,
            "mode": mode,
            "device": "cpu",
            "latency_ms": {"ffmpeg_ms": 1, "preprocess_ms": 1, "infer_ms": 1, "total_ms": 3},
        }


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    def _make(candidates=None, vsr=True):
        store = Store(tmp_path)
        fake = FakeVSR(candidates or [{"text": "i need water", "prob": 0.9}]) if vsr else None
        return TestClient(create_app(store=store, vsr_service=fake, autoload=False)), store

    return _make


def _clip():
    return {"video": ("clip.webm", b"fake-bytes", "video/webm")}


def test_health_and_profile_defaults(make_client):
    client, _ = make_client()
    h = client.get("/api/health").json()
    assert h["model_state"] == "ready" and h["ai_configured"] is False
    prof = client.get("/api/profile").json()
    assert any(p["text"] == "I need the nurse." for p in prof["phrases"])
    assert prof["preferences"]["capture_mode"] == "hold"


def test_lipread_offline_matcher_and_flags(make_client):
    client, _ = make_client([{"text": "i need water", "prob": 0.95}])
    data = client.post("/api/lipread", files=_clip(), data={"mode": "fast"}).json()
    r = data["result"]
    assert r["text"].lower().startswith("i need water")
    assert r["provider"].startswith("local")
    assert "needs_confirmation" in r and "urgent" in r
    assert data["latency_ms"]["end_to_end_ms"] >= 3


def test_urgent_result_flagged(make_client):
    client, _ = make_client([{"text": "i cant breathe", "prob": 0.9}])
    r = client.post("/api/lipread", files=_clip(), data={"phrases_only": "true"}).json()["result"]
    assert r["text"] == "I can't breathe."
    assert r["urgent"] is True


def test_confirm_policy_always(make_client):
    client, _ = make_client([{"text": "i need water", "prob": 0.99}])
    client.put("/api/profile", json={"preferences": {"confirm_policy": "always"}})
    r = client.post("/api/lipread", files=_clip()).json()["result"]
    assert r["needs_confirmation"] is True


def test_model_loading_returns_503(make_client):
    client, _ = make_client(vsr=False)
    resp = client.post("/api/lipread", files=_clip())
    assert resp.status_code == 503


def test_secrets_never_returned(make_client):
    client, store = make_client()
    out = client.put("/api/settings/secrets", json={"groq_api_key": "gsk_secret"}).json()
    assert out["groq_api_key"] is True
    assert "gsk_secret" not in client.get("/api/settings/secrets").text
    assert "gsk_secret" not in client.get("/api/health").text
    assert store.get_secret("groq_api_key") == "gsk_secret"
    client.put("/api/settings/secrets", json={"groq_api_key": ""})
    assert client.get("/api/settings/secrets").json()["groq_api_key"] is False


def test_log_learning_and_export(make_client):
    client, _ = make_client()
    client.post("/api/log", json={"speaker": "partner", "text": "Do you want tea?", "source": "mic"})
    client.post("/api/log", json={"speaker": "user", "text": "Peppermint tea please.", "source": "spell"})
    entries = client.get("/api/log").json()["entries"]
    assert [e["speaker"] for e in entries] == ["partner", "user"]
    # spelled sentence is learned into the phrase bank
    phrases = [p["text"] for p in client.get("/api/profile").json()["phrases"]]
    assert "Peppermint tea please." in phrases
    txt = client.get("/api/log/export?format=txt").text
    assert "Patient: Peppermint tea please." in txt
    csv_text = client.get("/api/log/export?format=csv").text
    assert csv_text.startswith("time,speaker,text")
    client.delete("/api/log")
    assert client.get("/api/log").json()["entries"] == []


def test_profile_phrase_edit_dedupes(make_client):
    client, _ = make_client()
    prof = client.put(
        "/api/profile",
        json={"phrases": [{"text": "Hi"}, {"text": "hi"}, {"text": "  "}, {"text": "Call Maria", "category": "Family"}],
              "names": ["Maria"]},
    ).json()
    assert [p["text"] for p in prof["phrases"]] == ["Hi", "Call Maria"]
    assert prof["names"] == ["Maria"]


def test_tts_without_voice_is_clear_error(make_client):
    client, _ = make_client()
    resp = client.post("/api/tts", json={"text": "hello"})
    assert resp.status_code == 400


def test_setup_quiet_and_care_defaults(make_client):
    client, _ = make_client()
    quiet = client.post("/api/profile/setup", json={"use": "quiet"}).json()
    p = quiet["preferences"]
    assert quiet["onboarded"] is True
    assert p["use"] == "quiet" and p["destination"] == "show"
    assert p["privacy_blur"] is True and p["keep_history"] is False and p["auto_clear_minutes"] == 2
    assert not any(b["urgent"] for b in quiet["quick_buttons"])
    care = client.post("/api/profile/setup", json={"use": "care"}).json()
    assert care["preferences"]["destination"] == "loud"
    assert any(b["id"] == "nurse" for b in care["quick_buttons"])
    assert client.post("/api/profile/setup", json={"use": "other"}).status_code == 422
