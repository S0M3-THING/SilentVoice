from phrases import DEFAULT_PHRASE_BANK, is_urgent, rank_locally, to_viseme_skeleton, viseme_similarity


def test_viseme_skeleton_merges_lookalike_letters():
    assert to_viseme_skeleton("bat") == to_viseme_skeleton("pat") == to_viseme_skeleton("mat")


def test_lookalike_words_score_higher_than_different_words():
    assert viseme_similarity("toffee please", "coffee please") > viseme_similarity("toffee please", "good night")


def test_closed_set_snaps_to_phrase_bank():
    cands = [{"text": "i neet the nurf", "prob": 0.6}, {"text": "i meet the nurse", "prob": 0.3}]
    res = rank_locally(cands, DEFAULT_PHRASE_BANK, closed_set=True)
    assert res["text"] == "I need the nurse."
    assert len(res["alternatives"]) == 3


def test_usage_breaks_ties_toward_habitual_phrases():
    cands = [{"text": "i am too", "prob": 0.5}]
    bank = ["I am too cold.", "I am too hot."]
    a = rank_locally(cands, bank, closed_set=True, usage={"I am too hot.": 20})
    assert a["text"] == "I am too hot."


def test_partner_context_boosts_yes_no():
    cands = [{"text": "yes", "prob": 0.4}, {"text": "yet", "prob": 0.45}]
    res = rank_locally(cands, [], partner_text="Do you want some water?")
    assert res["text"] == "yes"


def test_urgent_detection():
    assert is_urgent("I can't breathe.")
    assert is_urgent("My pain is 8 out of 10 in my chest.")
    assert not is_urgent("Good morning.")


def test_drink_context_never_turns_into_cant_breathe():
    cands = [
        {"text": "i want some toffee", "prob": 0.4},
        {"text": "i want some coffee", "prob": 0.35},
        {"text": "i want to be free", "prob": 0.25},
    ]
    res = rank_locally(cands, DEFAULT_PHRASE_BANK, partner_text="Would you like a drink?")
    assert res["text"] == "i want some coffee"
    assert "I can't breathe." not in res["alternatives"]
    assert res["confidence_label"] != "high"


def test_dominant_clear_guess_is_confident():
    cands = [{"text": "i need water", "prob": 0.9}, {"text": "i need waiter", "prob": 0.1}]
    res = rank_locally(cands, DEFAULT_PHRASE_BANK)
    assert res["text"].lower().startswith("i need water")
    assert res["confidence_label"] == "high"


def test_open_mode_ignores_weak_phrase_matches():
    cands = [{"text": "turn left at the station", "prob": 0.7}, {"text": "turn left at the nation", "prob": 0.3}]
    res = rank_locally(cands, DEFAULT_PHRASE_BANK)
    assert res["text"] == "turn left at the station"


def test_pretty_sentence_case():
    from phrases import pretty
    assert pretty("i want some coffee") == "I want some coffee"
    assert pretty("can i go home") == "Can I go home"
    assert pretty("I need the nurse.") == "I need the nurse."
