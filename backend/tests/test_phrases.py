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


def test_audio_boost_disambiguates_homophenes():
    # Visual homophenes: "pat" and "bat" look identical on lips
    candidates = [
        {"text": "pat", "prob": 0.5},
        {"text": "bat", "prob": 0.5},
    ]
    # Without audio, order is preserved
    res_no_audio = rank_locally(candidates, [])
    assert res_no_audio["text"] == "pat"

    # With faint audio heard: "bat"
    res_audio = rank_locally(candidates, [], patient_audio_text="bat")
    assert res_audio["text"] == "bat"


def test_clean_beam_hallucinations():
    from phrases import clean_beam_hallucinations

    assert clean_beam_hallucinations("huge mountain of dinosaur right dinosaur") == "huge mountain of dinosaur"
    assert clean_beam_hallucinations("hello hello hello world") == "hello world"
    assert clean_beam_hallucinations("water right water") == "water"


def test_microphone_audio_highest_priority_over_vsr_hallucinations():
    # User said tacos, but VSR hallucinated dinosaur repetition loop
    vsr = [
        {"text": "I really wanted to get a huge mountain of dinosaur right dinosaur", "prob": 0.88},
        {"text": "I really wanted to get a huge mountain", "prob": 0.12},
    ]
    spoken_audio = "i really want to eat a huge mountain of tacos right now"
    res = rank_locally(vsr, [], patient_audio_text=spoken_audio)

    assert res["text"] == spoken_audio
    assert res["confidence"] >= 0.85
    assert "microphone audio" in res["reasoning"]


def test_microphone_audio_overrides_nonsense_homophenes():
    # VSR homophene nonsense vs actual spoken request
    vsr = [
        {"text": "id really like to live in my medicine", "prob": 0.75},
        {"text": "id really like to leave in my medicine", "prob": 0.25},
    ]
    spoken_audio = "give me my medicine"
    res = rank_locally(vsr, ["I need my medicine."], patient_audio_text=spoken_audio)

    assert res["text"] == spoken_audio
    assert res["confidence"] >= 0.85


def test_interested_vsr_hallucination_resolves_to_thirsty_phrase_bank():
    # VSR visual homophene: 'im very interested' is visually 76% identical to 'I am very thirsty'
    vsr = [
        {"text": "im very interested", "prob": 0.85},
        {"text": "i am very interested", "prob": 0.15},
    ]
    # Even without context, the AAC communication phrase outranks the TED talk hallucination
    res = rank_locally(vsr, DEFAULT_PHRASE_BANK)
    assert res["text"] in ("I am very thirsty.", "I'm very thirsty.")
    assert any("thirsty" in alt.lower() for alt in res["alternatives"])


def test_interested_vsr_hallucination_with_thirsty_context():
    vsr = [
        {"text": "im very interested", "prob": 0.85},
        {"text": "i am very interested", "prob": 0.15},
    ]
    res = rank_locally(vsr, DEFAULT_PHRASE_BANK, user_context="im VERY THIRSTY")
    assert res["text"] in ("I am very thirsty.", "I'm very thirsty.")
    assert "I am too cold." not in res["alternatives"]
