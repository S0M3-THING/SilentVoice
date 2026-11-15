import pytest
from fastapi.testclient import TestClient

from app import create_app
from context_selector import select_best_hypothesis
from store import DEFAULT_PREFERENCES, Store
from word_check import build_context, check_guesses


class ContextAwareChecker:
    state = "ready"
    ready = True

    def __init__(self):
        self.received_contexts = []

    def availability(self):
        return True, ""

    def score(self, context, sentences):
        self.received_contexts.append(context)
        # If context mentions hospital, score medical words high
        # If context mentions park, score nature/park words high
        scores = []
        for s in sentences:
            score = -5.0
            if "hospital" in context.lower() and any(w in s.lower() for w in ["nurse", "pain", "doctor", "pills"]):
                score = -1.0
            elif "park" in context.lower() and any(w in s.lower() for w in ["bench", "dog", "trail", "trees"]):
                score = -1.0
            scores.append(score)
        return scores

    def status(self):
        return {"available": True, "state": "ready", "model": "fake", "reason": ""}


class FakeVSR:
    device = "cpu"

    def __init__(self, candidates):
        self.candidates = candidates

    def transcribe_video_bytes(self, raw_bytes, suffix, mode, top_k, hflip, enhance):
        return {
            "candidates": self.candidates,
            "frames": 40,
            "face_ratio": 1.0,
            "mode": mode,
            "device": "cpu",
            "latency_ms": {"total_ms": 1},
        }


def test_user_context_in_default_preferences(tmp_path):
    assert "user_context" in DEFAULT_PREFERENCES
    assert DEFAULT_PREFERENCES["user_context"] == ""
    store = Store(tmp_path)
    prof = store.get_profile()
    assert prof["preferences"]["user_context"] == ""

    # Test saving user context via profile update
    updated = store.update_profile({"preferences": {"user_context": "In a hospital ICU recovering from surgery"}})
    assert updated["preferences"]["user_context"] == "In a hospital ICU recovering from surgery"


def test_build_context_includes_user_context():
    # Without context
    ctx_plain = build_context("How are you feeling?", [{"speaker": "me", "text": "Okay."}])
    assert "Setting and context:" not in ctx_plain
    assert "Them: How are you feeling?" in ctx_plain

    # With hospital context
    ctx_hospital = build_context(
        "How are you feeling?",
        [{"speaker": "me", "text": "Okay."}],
        user_context="In the hospital ICU",
    )
    assert "Setting and context: In the hospital ICU." in ctx_hospital
    assert "Them: How are you feeling?" in ctx_hospital

    # With park context
    ctx_park = build_context("Where should we go?", [], user_context="At a public park with dogs")
    assert "Setting and context: At a public park with dogs." in ctx_park


def test_check_guesses_passes_user_context_to_checker():
    checker = ContextAwareChecker()
    cands = [{"text": "call the nurse", "prob": 0.4}, {"text": "call the purse", "prob": 0.5}]

    # 1. Hospital context boosts "nurse" over "purse"
    res = check_guesses(checker, cands, partner_text="Are you hurt?", user_context="In a hospital room")
    assert res is not None
    assert "hospital" in checker.received_contexts[-1].lower()
    assert res["candidates"][0]["text"] == "call the nurse"

    # 2. Park context
    park_cands = [{"text": "sit on the bench", "prob": 0.4}, {"text": "sit on the trench", "prob": 0.5}]
    res_park = check_guesses(checker, park_cands, user_context="At the city park")
    assert res_park is not None
    assert "park" in checker.received_contexts[-1].lower()
    assert res_park["candidates"][0]["text"] == "sit on the bench"


import asyncio

def test_select_best_hypothesis_with_user_context():
    checker = ContextAwareChecker()
    cands = [{"text": "call the purse", "prob": 0.5}, {"text": "call the nurse", "prob": 0.4}]
    res = asyncio.run(select_best_hypothesis(
        vsr_candidates=cands,
        phrase_bank=["Call the nurse."],
        checker=checker,
        user_context="in a hospital recovering from surgery",
    ))
    assert res["text"].lower().rstrip(".") == "call the nurse"
    assert "hospital" in checker.received_contexts[0].lower()


def test_lipread_endpoint_uses_saved_user_context(tmp_path):
    store = Store(tmp_path)
    store.update_profile({"preferences": {"user_context": "In a hospital after surgery"}})
    checker = ContextAwareChecker()
    app = create_app(
        store=store,
        vsr_service=FakeVSR([{"text": "call the purse", "prob": 0.5}, {"text": "call the nurse", "prob": 0.4}]),
        autoload=False,
        word_checker=checker,
    )
    client = TestClient(app)
    resp = client.post("/api/lipread", files={"video": ("c.webm", b"fake", "video/webm")}).json()
    assert resp["result"]["text"].lower().rstrip(".") == "call the nurse"
    assert "hospital" in checker.received_contexts[0].lower()


def test_lipread_endpoint_overrides_user_context_from_form(tmp_path):
    store = Store(tmp_path)
    checker = ContextAwareChecker()
    app = create_app(
        store=store,
        vsr_service=FakeVSR([{"text": "sit on the trench", "prob": 0.5}, {"text": "sit on the bench", "prob": 0.4}]),
        autoload=False,
        word_checker=checker,
    )
    client = TestClient(app)
    resp = client.post(
        "/api/lipread",
        files={"video": ("c.webm", b"fake", "video/webm")},
        data={"user_context": "At the city park"},
    ).json()
    assert resp["result"]["text"].lower().rstrip(".") == "sit on the bench"
    assert "park" in checker.received_contexts[0].lower()


def test_thirsty_context_disambiguates_need_water_from_didnt_want():
    from phrases import rank_locally

    vsr = [
        {"text": "i didnt want", "prob": 0.85},
        {"text": "i did not want", "prob": 0.15},
    ]
    phrases = ["I need water.", "I am in pain.", "I need the nurse."]
    res = rank_locally(vsr, phrases, user_context="im VERY THIRSTY")

    assert res["text"] == "I need water."
    assert "I need water." in res["alternatives"]


def test_thirsty_context_boosts_water_over_didnt_want_in_cands():
    from phrases import rank_locally

    vsr = [
        {"text": "i didnt want", "prob": 0.72},
        {"text": "i need water", "prob": 0.28},
    ]
    res = rank_locally(vsr, [], user_context="im VERY THIRSTY")

    assert res["text"] == "i need water"
