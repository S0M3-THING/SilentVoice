"""Word check, Mac voices, lip tracking and settings migration."""

import json

from fastapi.testclient import TestClient

import system_voice
from app import create_app
from store import Store
from word_check import blend, build_context, check_guesses


class FakeChecker:
    """Scores sentences by keyword, standing in for the text model."""

    state = "ready"
    ready = True

    def __init__(self, liked=("coffee",)):
        self.liked = liked
        self.contexts = []

    def availability(self):
        return True, ""

    def score(self, context, sentences):
        self.contexts.append(context)
        return [-1.5 if any(w in s for w in self.liked) else -5.0 for s in sentences]

    def status(self):
        return {"available": True, "state": "ready", "model": "fake", "reason": ""}


class FakeVSR:
    device = "cpu"

    def __init__(self, candidates):
        self.candidates = candidates

    def transcribe_video_bytes(self, raw_bytes, suffix, mode, top_k, hflip, enhance):
        return {"candidates": self.candidates, "frames": 40, "face_ratio": 1.0, "mode": mode, "device": "cpu",
                "latency_ms": {"total_ms": 1}}


class FakeMouth:
    def locate(self, jpeg):
        return {"found": True, "x": 0.4, "y": 0.6, "face_w": 0.3, "face_h": 0.3, "score": 0.9}


TOFFEE = [{"text": "i want some toffee", "prob": 0.4}, {"text": "i want some coffee", "prob": 0.35},
          {"text": "i want to be free", "prob": 0.25}]


def _client(tmp_path, checker=None, cands=TOFFEE):
    store = Store(tmp_path)
    app = create_app(store=store, vsr_service=FakeVSR(cands), autoload=False, word_checker=checker or FakeChecker(),
                     mouth_locator=FakeMouth())
    return TestClient(app), store


def test_blend_prefers_sensible_sentence():
    ranked = blend(TOFFEE, [-5.0, -1.5, -4.0])
    assert ranked[0]["text"] == "i want some coffee"
    assert abs(sum(c["prob"] for c in ranked) - 1) < 0.01
    assert ranked[0]["vsr_prob"] == 0.35


def test_blend_keeps_lip_order_when_text_model_is_neutral():
    ranked = blend(TOFFEE, [-3.0, -3.0, -3.0])
    assert [c["text"] for c in ranked] == [c["text"] for c in TOFFEE]


def test_context_includes_partner_question():
    ctx = build_context("Would you like a drink?", [{"speaker": "me", "text": "Hello."}])
    assert ctx.endswith("Them: Would you like a drink?\nMe:")
    assert "Me: Hello." in ctx


def test_check_guesses_skips_when_not_ready():
    class NotReady(FakeChecker):
        ready = False

    assert check_guesses(NotReady(), TOFFEE) is None
    assert check_guesses(None, TOFFEE) is None


def test_lipread_uses_word_check_and_asks_when_it_changes_the_top(tmp_path):
    checker = FakeChecker()
    client, _ = _client(tmp_path, checker)
    r = client.post("/api/lipread", files={"video": ("c.webm", b"x", "video/webm")},
                    data={"partner_text": "Would you like something to drink?"}).json()
    assert r["result"]["text"].rstrip(".") == "I want some coffee"
    assert r["result"]["needs_confirmation"] is True  # changed the lips' first guess -> ask
    assert "word-check" in r["result"]["provider"]
    assert "drink" in checker.contexts[0]


def test_word_check_can_be_turned_off(tmp_path):
    client, _ = _client(tmp_path)
    client.put("/api/profile", json={"preferences": {"word_check": False}})
    r = client.post("/api/lipread", files={"video": ("c.webm", b"x", "video/webm")}).json()
    assert "word-check" not in r["result"]["provider"]


def test_health_reports_word_check_and_mac_voice(tmp_path):
    client, _ = _client(tmp_path)
    h = client.get("/api/health").json()
    assert h["word_check"]["state"] == "ready"
    assert h["mac_voice"] in (True, False)


def test_mouth_endpoint(tmp_path):
    client, _ = _client(tmp_path)
    r = client.post("/api/mouth", files={"frame": ("f.jpg", b"\xff\xd8jpeg", "image/jpeg")}).json()
    assert r["found"] and r["x"] == 0.4


def test_parse_mac_voice_list():
    out = (
        "Albert              en_US    # Hello! My name is Albert.\n"
        "Eddy (English (UK)) en_GB    # Hello! My name is Eddy.\n"
        "Amélie              fr_CA    # Bonjour, je m’appelle Amélie.\n"
        "Samantha            en_US    # Hello, my name is Samantha.\n"
    )
    voices = system_voice.parse_voice_list(out)
    assert [v["name"] for v in voices] == ["Albert", "Eddy (English (UK))", "Amélie", "Samantha"]
    assert voices[1]["lang"] == "en-GB"


def test_mac_voice_endpoint_off_mac(tmp_path, monkeypatch):
    monkeypatch.setattr(system_voice, "available", lambda: False)
    client, _ = _client(tmp_path)
    assert client.post("/api/tts/system", json={"text": "Hi"}).status_code == 501
    assert client.get("/api/voices/system").json()["available"] is False


def test_old_settings_are_migrated(tmp_path):
    store = Store(tmp_path)
    prof = store.get_profile()
    prof["preferences"].update({"capture_mode": "auto", "destination": "copy", "use": "quiet", "sensitivity": 0.5})
    (tmp_path / "profile.json").write_text(json.dumps(prof))
    p = store.get_profile()["preferences"]
    assert p["capture_mode"] == "tap" and p["destination"] == "show" and "sensitivity" not in p
