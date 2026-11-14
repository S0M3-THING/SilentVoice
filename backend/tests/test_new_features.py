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
    assert p["capture_mode"] == "hold" and p["destination"] == "show" and "sensitivity" not in p


# ---------------------------------------------------------------- names
from phrases import name_variants, pretty  # noqa: E402
from voice_engine import CosyVoiceEngine  # noqa: E402
import sys  # noqa: E402


def test_name_variants_swap_look_alike_words():
    out = name_variants([{"text": "can you call a cash", "prob": 0.6}, {"text": "can you call a cat", "prob": 0.4}], ["Akash"])
    texts = [c["text"] for c in out]
    assert texts[0] == "can you call Akash"
    assert "can you call a cash" in texts  # the lips' own guess stays as an alternative


def test_name_variants_capitalise_exact_names_and_ignore_far_words():
    out = name_variants([{"text": "is priya here", "prob": 0.9}], ["Priya", "Sam"])
    assert [c["text"] for c in out] == ["is Priya here"]
    assert name_variants([{"text": "i want ham", "prob": 1}], ["Sam"]) == [{"text": "i want ham", "prob": 1}]


def test_pretty_keeps_names():
    assert pretty("can you call Akash") == "Can you call Akash"
    assert pretty("i think i'm fine") == "I think I'm fine"


def test_names_reach_the_lip_reading(tmp_path):
    checker = FakeChecker(liked=("Akash",))
    client, _ = _client(tmp_path, checker, cands=[{"text": "please call a cash", "prob": 0.7}, {"text": "please call a cab", "prob": 0.3}])
    client.put("/api/profile", json={"names": ["Akash", "Tejas"]})
    r = client.post("/api/lipread", files={"video": ("c.webm", b"x", "video/webm")}).json()["result"]
    assert r["text"] == "Please call Akash"
    assert r["needs_confirmation"] is True  # a swapped-in name is always checked with the user
    assert "Akash, Tejas" in checker.contexts[0]


# ---------------------------------------------------------------- CosyVoice
def test_cosyvoice_engine_talks_to_its_helper(tmp_path):
    import numpy as np
    import wave

    ref = tmp_path / "ref.wav"
    with wave.open(str(ref), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\0\0" * 24000)
    eng = CosyVoiceEngine(python=sys.executable, fake=True)
    try:
        assert eng.availability() == (True, "")
        audio, rate = eng.synthesize("Hello there.", str(ref), "hello")
        assert rate == 24000 and len(audio) == 7200 and np.abs(audio).max() > 0.1
        audio2, _ = eng.synthesize("Again.", str(ref), "hello")  # same helper, still alive
        assert len(audio2) == 7200
    finally:
        eng.close()


def test_cosyvoice_not_installed_explains(tmp_path):
    eng = CosyVoiceEngine(python=tmp_path / "missing" / "python", fake=True)
    ok, why = eng.availability()
    assert not ok and "setup.sh" in why


def test_switch_voice_model(tmp_path):
    from test_voice import FakeEngine

    store = Store(tmp_path)
    a, b = FakeEngine(), FakeEngine()
    b.name, b.model_id = "Fake Cosy", "fake/cosy"
    client = TestClient(create_app(store=store, autoload=False, voice_engines={"qwen3": a, "cosyvoice": b},
                                   word_checker=FakeChecker(), mouth_locator=FakeMouth()))
    v = client.get("/api/voice").json()
    assert v["engine_key"] == "qwen3" and [e["key"] for e in v["engines"]] == ["qwen3", "cosyvoice"]
    client.put("/api/profile", json={"preferences": {"voice_model": "cosyvoice"}})
    assert client.get("/api/voice").json()["engine"] == "Fake Cosy"
