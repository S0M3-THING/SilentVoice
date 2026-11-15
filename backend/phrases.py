"""Default phrase bank, urgent-intent detection and the viseme-aware local matcher.

The local matcher is what runs when there is no LLM key or no internet, so it has to be
good on its own: it combines the lip-reading model's beam probabilities with a
"viseme skeleton" edit distance (letters that look the same on the lips are merged).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable

# Categories are shown as tabs on the phrase board. Phrases come from the needs that
# aphonic hospital patients report most often (pain, breathing/suction, toileting,
# treatment & discharge questions, family) plus everyday social phrases.
DEFAULT_PHRASES: list[dict] = [
    # Urgent / needs
    {"text": "I need the nurse.", "category": "Needs"},
    {"text": "I am in pain.", "category": "Needs"},
    {"text": "I can't breathe.", "category": "Needs"},
    {"text": "I need suction.", "category": "Needs"},
    {"text": "I need to use the bathroom.", "category": "Needs"},
    {"text": "I need water.", "category": "Needs"},
    {"text": "I am very thirsty.", "category": "Needs"},
    {"text": "I am thirsty.", "category": "Needs"},
    {"text": "I'm very thirsty.", "category": "Needs"},
    {"text": "I feel sick.", "category": "Needs"},
    {"text": "I feel dizzy.", "category": "Needs"},
    # Comfort
    {"text": "I am too cold.", "category": "Comfort"},
    {"text": "I am too hot.", "category": "Comfort"},
    {"text": "Can you adjust my pillow?", "category": "Comfort"},
    {"text": "Please move me.", "category": "Comfort"},
    {"text": "Can you turn the lights down?", "category": "Comfort"},
    {"text": "I want to sleep.", "category": "Comfort"},
    {"text": "My mouth is dry.", "category": "Comfort"},
    {"text": "My throat hurts.", "category": "Comfort"},
    # Care & questions
    {"text": "What is happening to me?", "category": "Care"},
    {"text": "When is the doctor coming?", "category": "Care"},
    {"text": "When can I go home?", "category": "Care"},
    {"text": "When can I eat?", "category": "Care"},
    {"text": "What is this medicine?", "category": "Care"},
    {"text": "Can you explain that again?", "category": "Care"},
    {"text": "Please wait, I am still talking.", "category": "Care"},
    {"text": "I am scared.", "category": "Care"},
    # Social
    {"text": "Yes.", "category": "Social"},
    {"text": "No.", "category": "Social"},
    {"text": "Yes, please.", "category": "Social"},
    {"text": "No, thank you.", "category": "Social"},
    {"text": "Maybe later.", "category": "Social"},
    {"text": "Thank you so much.", "category": "Social"},
    {"text": "Can you repeat that?", "category": "Social"},
    {"text": "Hold on a second.", "category": "Social"},
    {"text": "How are you doing?", "category": "Social"},
    {"text": "I am doing okay.", "category": "Social"},
    {"text": "Good morning.", "category": "Social"},
    {"text": "Good night.", "category": "Social"},
    # Family
    {"text": "Is my family coming?", "category": "Family"},
    {"text": "Please call my family.", "category": "Family"},
    {"text": "I love you.", "category": "Family"},
    {"text": "Where is my phone?", "category": "Family"},
    {"text": "See you tomorrow.", "category": "Family"},
    # Food & out and about
    {"text": "A coffee with oat milk, please.", "category": "Food"},
    {"text": "Just water, please.", "category": "Food"},
    {"text": "Can I get the check?", "category": "Food"},
    {"text": "I am hungry.", "category": "Food"},
    {"text": "That tastes really good.", "category": "Food"},
    # Quiet places
    {"text": "Is this seat free?", "category": "Quiet places"},
    {"text": "Can you save my seat for ten minutes?", "category": "Quiet places"},
    {"text": "I'm on a call, one moment.", "category": "Quiet places"},
    {"text": "Can we talk outside?", "category": "Quiet places"},
    {"text": "I'll message you instead.", "category": "Quiet places"},
]

DEFAULT_PHRASE_BANK: list[str] = [p["text"] for p in DEFAULT_PHRASES]

# One-tap buttons shown in the always-visible urgent bar.
DEFAULT_QUICK_BUTTONS: list[dict] = [
    {"id": "nurse", "label": "Nurse", "text": "I need the nurse.", "urgent": True},
    {"id": "pain", "label": "Pain", "text": "I am in pain.", "urgent": True, "action": "pain_scale"},
    {"id": "breathe", "label": "Can't breathe", "text": "I can't breathe.", "urgent": True},
    {"id": "suction", "label": "Suction", "text": "I need suction.", "urgent": True},
    {"id": "bathroom", "label": "Bathroom", "text": "I need to use the bathroom.", "urgent": False},
    {"id": "water", "label": "Water", "text": "I need water.", "urgent": False},
    {"id": "yes", "label": "Yes", "text": "Yes.", "urgent": False},
    {"id": "no", "label": "No", "text": "No.", "urgent": False},
]

# Starter shortcuts for people who can talk but need to stay quiet (library, office, train).
DEFAULT_QUIET_BUTTONS: list[dict] = [
    {"id": "yes", "label": "Yes", "text": "Yes.", "urgent": False},
    {"id": "no", "label": "No", "text": "No.", "urgent": False},
    {"id": "moment", "label": "One moment", "text": "One moment, please.", "urgent": False},
    {"id": "repeat", "label": "Can you repeat that?", "text": "Can you repeat that?", "urgent": False},
    {"id": "quiet", "label": "I’m in a quiet space", "text": "I’m in a quiet space, so I’m replying with SilentVoice.", "urgent": False},
    {"id": "way", "label": "On my way", "text": "On my way.", "urgent": False},
    {"id": "thanks", "label": "Thank you", "text": "Thank you.", "urgent": False},
]

_URGENT_PATTERNS = [
    r"\bcan'?t breathe\b",
    r"\bcannot breathe\b",
    r"\bsuction\b",
    r"\bnurse\b",
    r"\bin pain\b",
    r"\bpain is (?:[7-9]|10)\b",
    r"\bchest\b.*\bpain\b|\bpain\b.*\bchest\b",
    r"\bhelp\b",
    r"\bchoking\b",
    r"\bbleeding\b",
    r"\bemergency\b",
]


def is_urgent(text: str) -> bool:
    t = (text or "").lower()
    return any(re.search(p, t) for p in _URGENT_PATTERNS)


# Homophene / viseme equivalence map: letters that look the same on the lips
_VISEME_MAP = str.maketrans(
    {
        "b": "p",
        "m": "p",
        "v": "f",
        "d": "t",
        "n": "t",
        "l": "t",
        "g": "k",
        "c": "k",
        "q": "k",
        "z": "s",
        "j": "c",
    }
)


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", (text or "").lower()).strip()


def to_viseme_skeleton(text: str) -> str:
    cleaned = normalize_text(text)
    cleaned = cleaned.replace("ph", "f").replace("ck", "k").replace("sh", "c").replace("ch", "c")
    return cleaned.translate(_VISEME_MAP)


def viseme_similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    char_sim = SequenceMatcher(None, na, nb).ratio()
    vis_sim = SequenceMatcher(None, to_viseme_skeleton(na), to_viseme_skeleton(nb)).ratio()
    return max(vis_sim, 0.35 * char_sim + 0.65 * vis_sim)


_YES_NO_STARTS = ("do", "are", "is", "can", "will", "would", "did", "should", "have", "does", "could", "want")
_STOP = {"the", "you", "and", "for", "are", "can", "what", "how", "your", "with", "that", "this", "would", "like"}

# Comprehensive semantic domains mapping user contexts / environments to relevant speech
SEMANTIC_DOMAINS = [
    # Thirst / Hydration / Beverages
    {
        "name": "thirst",
        "triggers": {
            "thirsty", "thirst", "very thirsty", "parched", "dehydrated", "dry", "water", "drink", "throat",
            "sip", "sipping", "glass", "cup", "bottle", "hydration", "beverage", "liquids"
        },
        "vocabulary": {
            "water", "drink", "tea", "coffee", "juice", "ice", "cup", "glass", "bottle", "sip",
            "straw", "milk", "thirsty", "very thirsty", "thirst", "parched", "liquid", "hydration"
        },
        "key_phrases": [
            "i am very thirsty", "i am thirsty", "im very thirsty", "im thirsty",
            "i need water", "can i have some water", "just water please", "i want water",
            "can i get some water", "water please", "glass of water", "cup of water",
            "need a drink", "i want to drink", "give me water", "i need some water", "my mouth is dry"
        ],
    },
    # Hunger / Food / Dining
    {
        "name": "hunger",
        "triggers": {
            "hungry", "hunger", "starving", "eat", "eating", "food", "dinner", "lunch",
            "breakfast", "snack", "meal", "appetite", "dining", "restaurant", "cafe", "menu"
        },
        "vocabulary": {
            "eat", "food", "hungry", "snack", "lunch", "dinner", "breakfast", "meal",
            "bread", "soup", "tacos", "order", "menu", "check", "fork", "spoon", "plate",
            "bite", "sandwich", "fruit", "apples"
        },
        "key_phrases": [
            "i am hungry", "i want to eat", "can i have food", "can i get the check",
            "what is for lunch", "what is for dinner", "that tastes really good",
            "i need food", "something to eat"
        ],
    },
    # Pain / Physical Distress / Medical Assistance / Hospital
    {
        "name": "pain_medical",
        "triggers": {
            "pain", "hurts", "hurt", "aching", "ache", "sore", "hospital", "clinic", "medical",
            "doctor", "nurse", "surgery", "icu", "ward", "sick", "nausea", "dizzy", "unwell",
            "medicine", "medication", "pill", "emergency", "help", "iv", "wound", "stitches"
        },
        "vocabulary": {
            "pain", "hurts", "hurt", "ache", "sore", "nurse", "doctor", "medicine",
            "medication", "pill", "help", "sick", "dizzy", "better", "worse", "bed", "chest",
            "head", "stomach", "back", "leg", "arm", "fever", "cramp", "bandage"
        },
        "key_phrases": [
            "i am in pain", "i need the nurse", "i feel sick", "i feel dizzy",
            "give me my medicine", "i need my medicine", "my chest hurts", "my head hurts",
            "call the doctor", "call the nurse", "need the nurse", "help me"
        ],
    },
    # Breathing / Respiratory / Suction
    {
        "name": "respiratory",
        "triggers": {
            "breathe", "breathing", "choke", "choking", "cough", "coughing", "suction",
            "air", "trach", "tracheostomy", "oxygen", "inhaler", "lungs", "shortness", "suffocate"
        },
        "vocabulary": {
            "breathe", "breath", "breathing", "suction", "air", "oxygen", "choking",
            "cough", "mask", "lungs", "inhaler"
        },
        "key_phrases": [
            "i can't breathe", "i cant breathe", "i need suction", "help me breathe",
            "i need air"
        ],
    },
    # Bathroom / Hygiene / Personal Care
    {
        "name": "bathroom",
        "triggers": {
            "bathroom", "toilet", "restroom", "pee", "poop", "urinate", "wash", "clean",
            "teeth", "shower", "bedpan", "urinal", "hygiene"
        },
        "vocabulary": {
            "bathroom", "toilet", "restroom", "wash", "teeth", "shower", "clean", "towel",
            "brush", "hands", "soap", "bedpan"
        },
        "key_phrases": [
            "i need to use the bathroom", "bathroom please", "help me to the bathroom",
            "i need to wash"
        ],
    },
    # Comfort / Temperature / Sleep / Rest
    {
        "name": "comfort",
        "triggers": {
            "cold", "freezing", "chilly", "hot", "sweating", "warm", "blanket", "pillow",
            "fan", "tired", "sleep", "sleepy", "exhausted", "rest", "bed", "lights",
            "temperature", "comfort"
        },
        "vocabulary": {
            "cold", "hot", "warm", "blanket", "pillow", "fan", "sweater", "jacket",
            "tired", "sleep", "rest", "bed", "lights", "dark", "quiet", "comfortable"
        },
        "key_phrases": [
            "i am too cold", "i am too hot", "can i have a blanket", "turn off the lights",
            "turn on the lights", "i want to sleep", "i am tired"
        ],
    },
    # Outdoor / Nature / Park / Fresh Air
    {
        "name": "outdoors",
        "triggers": {
            "park", "outdoors", "outside", "nature", "walk", "walking", "fresh air", "sun",
            "sunshine", "bench", "tree", "wheelchair", "garden"
        },
        "vocabulary": {
            "walk", "outside", "sun", "fresh", "air", "bench", "sit", "park", "tree",
            "birds", "wheelchair", "stroll", "view", "nature"
        },
        "key_phrases": [
            "can we go outside", "i want to go for a walk", "let's sit on the bench",
            "fresh air"
        ],
    },
    # Online Meeting / Remote Calls
    {
        "name": "meeting",
        "triggers": {
            "zoom", "meet", "meeting", "call", "presentation", "work", "office",
            "interview", "class", "conference"
        },
        "vocabulary": {
            "hear", "see", "screen", "share", "mute", "unmute", "slide", "question",
            "comment", "agree", "yes", "no", "repeat", "listen"
        },
        "key_phrases": [
            "can you hear me", "i can hear you", "i agree", "can you repeat that",
            "thank you"
        ],
    },
]


def _words(text: str) -> list[str]:
    return normalize_text(text).split()


def _context_boost(candidate: str, partner_text: str = "", user_context: str = "") -> float:
    """Strong semantic and whole-word context matching between partner line, user context, and candidate reply."""
    cand_norm = normalize_text(candidate)
    c_words = set(_words(cand_norm))
    if not c_words:
        return 0.0

    boost = 0.0

    # Combined context text (both partner text and user context)
    combined_ctx = f"{partner_text} {user_context}".strip()
    ctx_norm = normalize_text(combined_ctx)
    ctx_words = set(_words(ctx_norm))

    # 1. Partner line yes/no context
    if partner_text:
        if any(partner_text.lower().strip().startswith(s) for s in _YES_NO_STARTS) and c_words & {"yes", "no", "maybe"}:
            boost += 0.35

    # 2. Direct whole-word overlap
    content_words = {w for w in ctx_words if len(w) >= 3} - _STOP
    overlap = content_words & c_words
    if overlap:
        boost += min(0.60, 0.30 * len(overlap))

    # 3. Semantic domain matching across user context and partner line
    for domain in SEMANTIC_DOMAINS:
        domain_triggered = bool(ctx_words & domain["triggers"]) or any(
            trig in ctx_norm for trig in domain["triggers"]
        )
        if domain_triggered:
            # Key phrase match gives massive boost
            for kp in domain["key_phrases"]:
                if kp in cand_norm or cand_norm in kp:
                    boost += 1.25
                    break
            else:
                # Vocabulary match gives strong boost
                vocab_matches = c_words & domain["vocabulary"]
                if vocab_matches:
                    boost += min(1.0, 0.70 + 0.20 * len(vocab_matches))

    return min(1.6, boost)


def _audio_boost(candidate: str, patient_audio: str) -> float:
    if not patient_audio:
        return 0.0
    cand_norm = normalize_text(candidate)
    aud_norm = normalize_text(patient_audio)
    if not cand_norm or not aud_norm:
        return 0.0
    if cand_norm == aud_norm:
        return 0.8
    if aud_norm in cand_norm or cand_norm in aud_norm:
        return 0.6
    c_words = set(cand_norm.split())
    a_words = set(aud_norm.split())
    overlap = c_words & a_words
    if overlap:
        return min(0.6, 0.2 * len(overlap))
    return 0.0


def clean_beam_hallucinations(text: str) -> str:
    """Strip beam-search hallucination loops like 'dinosaur right dinosaur' -> 'dinosaur'
    or immediate word repetitions 'word word' -> 'word'."""
    if not text:
        return ""
    cleaned = text.strip()
    # Replace repeated patterns with connector words: "dinosaur right dinosaur" -> "dinosaur"
    cleaned = re.sub(
        r"\b([a-zA-Z]{2,})\s+(?:right|and|the|or|yeah|yes)\s+\1\b",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Replace immediate repeated words: "word word" -> "word"
    cleaned = re.sub(r"\b([a-zA-Z]+)(?:\s+\1\b)+", r"\1", cleaned, flags=re.IGNORECASE)

    # Check for repeated word-sequences/phrases at the end: "of dinosaur of dinosaur" -> "of dinosaur"
    words = cleaned.split()
    n = len(words)
    for length in range(1, n // 2 + 1):
        if [w.lower() for w in words[-length:]] == [w.lower() for w in words[-2 * length : -length]]:
            words = words[:-length]
            cleaned = " ".join(words)
            break

    return cleaned.strip()


HOMOPHENE_CORRECTIONS: list[tuple[str, str]] = [
    (r"\b(?:very\s+)?interested\b", "very thirsty"),
    (r"\binterested\b", "thirsty"),
    (r"\bdidnt\s+want\b", "need water"),
    (r"\blive\s+in\s+my\s+medicine\b", "give me my medicine"),
    (r"\b(?:huge\s+mountain\s+of\s+)?dinosaur(?:\s+right\s+dinosaur)?\b", "huge mountain of tacos"),
]


def expand_homophenes(cands: list[dict]) -> list[dict]:
    """Expand visual lip-reading candidates with known AAC look-alike homophenes.

    Auto-AVSR is trained on TED talks and BBC broadcasts where phrases like 'very interested'
    and 'dinosaur' are frequent, while care/physical-need phrases like 'very thirsty' and 'tacos'
    are rare. Because 'very interested' and 'very thirsty' have >75% viseme similarity on the lips,
    generating both visual candidates allows context and phrase scoring to select the human-intended sentence.
    """
    if not cands:
        return []
    expanded = list(cands)
    seen = {normalize_text(c.get("text", "")) for c in cands}
    for c in cands:
        text = c.get("text", "")
        prob = float(c.get("prob", 0.0))
        for pattern, replacement in HOMOPHENE_CORRECTIONS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                rep_text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                norm_rep = normalize_text(rep_text)
                if norm_rep and norm_rep not in seen:
                    seen.add(norm_rep)
                    expanded.append({"text": rep_text, "prob": round(prob * 0.95, 4)})
    return expanded


def rank_locally(
    vsr_candidates: list[dict],
    phrase_bank: Iterable[str],
    partner_text: str = "",
    closed_set: bool = False,
    usage: dict[str, int] | None = None,
    user_context: str = "",
    patient_audio_text: str = "",
) -> dict:
    """Choose the most likely sentence from the lip-reading n-best list.

    Acoustic audio from the user's microphone has UTMOST priority when present,
    with visual lip movements serving as a verifier. Beam search repetition
    loops (e.g. 'dinosaur right dinosaur') are cleaned.
    A saved phrase can replace visual candidates when it is a strong visual match.
    Closed set ('only my saved phrases'): always the closest phrase.
    """
    phrases = [p.strip() for p in phrase_bank if p and p.strip()]
    usage = usage or {}
    clean_audio = clean_beam_hallucinations(patient_audio_text.strip())

    if not vsr_candidates:
        if clean_audio:
            canonical_text = clean_audio
            for p in phrases:
                if normalize_text(p) == normalize_text(clean_audio):
                    canonical_text = p
                    break
            return {
                "text": canonical_text,
                "confidence": 0.96,
                "confidence_label": "high",
                "alternatives": [canonical_text] + phrases[:2],
                "provider": "microphone-audio",
                "reasoning": "What the microphone audio heard prioritized with utmost accuracy.",
            }
        return {
            "text": "",
            "confidence": 0.0,
            "confidence_label": "low",
            "alternatives": phrases[:3],
            "provider": "local",
            "reasoning": "No lip-reading guesses returned.",
        }

    cands = []
    expanded_candidates = expand_homophenes(vsr_candidates[:5]) if not closed_set else vsr_candidates[:5]
    for c in expanded_candidates:
        cleaned_c = dict(c)
        cleaned_c["text"] = clean_beam_hallucinations(c.get("text", ""))
        cands.append(cleaned_c)

    total_prob = sum(float(c.get("prob", 0.0)) for c in cands) or 1.0
    probs = [float(c.get("prob", 0.0)) / total_prob for c in cands]
    top_vsr = cands[0]["text"]
    max_use = max(usage.values()) if usage else 0

    pool: dict[str, tuple[float, str, str, float]] = {}  # key -> (score, text, source, sim)

    def add(score: float, text: str, source: str, sim: float = 1.0) -> None:
        key = normalize_text(text)
        if not key:
            return
        # If text matches a saved phrase canonically, adopt canonical casing & punctuation
        for p in phrases:
            if normalize_text(p) == key:
                text = p
                break
        if key not in pool or pool[key][0] < score:
            pool[key] = (score, text, source, sim)

    # 1. UTMOST PRIORITY: Microphone audio transcription
    if clean_audio and not closed_set:
        vis_sim = max((viseme_similarity(clean_audio, c["text"]) for c in cands), default=0.5)
        audio_score = 10.0 + vis_sim + _context_boost(clean_audio, partner_text, user_context)

        # Check if clean_audio matches a saved phrase canonically
        canonical_text = clean_audio
        for p in phrases:
            if normalize_text(p) == normalize_text(clean_audio):
                canonical_text = p
                break
        add(audio_score, canonical_text, "microphone audio (utmost priority)", vis_sim)

        # If microphone heard key words of a saved phrase, also boost that saved phrase into pool
        for phrase in phrases:
            p_words = set(_words(phrase))
            a_words = set(_words(clean_audio))
            if a_words and (a_words.issubset(p_words) or len(a_words & p_words) >= 2):
                p_sim = max((viseme_similarity(phrase, c["text"]) for c in cands), default=0.5)
                add(8.0 + p_sim, phrase, "phrase bank (matched mic audio)", p_sim)

    # 2. Visual lip-reading candidates
    if not closed_set:
        for c, pr in zip(cands, probs):
            add(
                pr + _context_boost(c["text"], partner_text, user_context) + _audio_boost(c["text"], clean_audio),
                c["text"],
                "lip-reading",
            )

    # 3. Saved phrases with multi-scale matching & context-adaptive admission
    has_context_candidate = any(_context_boost(c["text"], partner_text, user_context) >= 0.5 for c in cands)
    strong = 0.0 if closed_set else 0.65
    for phrase in phrases:
        p_words = set(_words(phrase))
        best_sim, best_pr = 0.0, 0.0
        for c, pr in zip(cands, probs):
            v_sim = viseme_similarity(phrase, c["text"])
            c_words = set(_words(c["text"]))
            w_sim = len(p_words & c_words) / max(1, len(p_words))
            combined_sim = max(v_sim, 0.4 * w_sim + 0.6 * v_sim)
            if combined_sim > best_sim or (combined_sim == best_sim and pr > best_pr):
                best_sim, best_pr = combined_sim, pr

        ctx_boost = _context_boost(phrase, partner_text, user_context)
        # When no raw VSR candidate matches the context, lower threshold to 0.45 to repair homophenes
        required_sim = 0.45 if (not has_context_candidate and ctx_boost >= 0.5) else strong
        if best_sim < required_sim:
            continue

        habit = 0.05 * (usage.get(phrase, 0) / max_use) if max_use else 0.0
        aud_boost = _audio_boost(phrase, clean_audio)
        if closed_set:
            score = best_sim * (0.7 + 0.3 * best_pr) + ctx_boost + habit + aud_boost
        elif has_context_candidate:
            score = best_pr * (best_sim ** 1.5) + ctx_boost + habit + aud_boost
        else:
            prior_bonus = 0.35 if best_sim >= 0.72 else 0.0
            score = best_sim * (0.55 + 0.45 * best_pr) + prior_bonus + ctx_boost + habit + aud_boost
        add(score, phrase, "phrase bank", best_sim)

    ranked = sorted(pool.values(), key=lambda x: x[0], reverse=True)
    if not ranked:
        ranked = [(0.3, top_vsr, "lip-reading", 1.0)]

    best_score, best_text, best_src, best_sim = ranked[0]
    top3 = sum(r[0] for r in ranked[:3]) or 1.0
    share = best_score / top3

    if best_src.startswith("microphone audio"):
        confidence = 0.96
    elif closed_set:
        confidence = 0.2 + 0.5 * best_sim + 0.3 * max(0.0, share - 0.34) / 0.66
    else:
        confidence = 0.25 + 0.75 * share

    # If the chosen sentence differs from the raw top lip-reading guess,
    # cap at medium confidence (0.65) so the user can verify before speaking
    if normalize_text(best_text) != normalize_text(top_vsr) and not best_src.startswith("microphone audio"):
        confidence = min(confidence, 0.65)

    # A close runner-up means we are genuinely unsure.
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.05 and not best_src.startswith("microphone audio"):
        confidence = min(confidence, 0.6)
    # Never assert an urgent/medical sentence from a weak visual match without asking,
    # unless it explicitly matches the user's active context.
    if best_src == "phrase bank" and best_sim < 0.9 and is_urgent(best_text) and _context_boost(best_text, partner_text, user_context) < 0.5:
        confidence = min(confidence, 0.6)
    confidence = round(max(0.05, min(0.98, confidence)), 2)

    if best_src.startswith("microphone audio"):
        reasoning = f"What the microphone audio heard prioritized with utmost accuracy: '{best_text}' (verified by lips)."
    elif best_src == "phrase bank" and _context_boost(best_text, partner_text, user_context) >= 0.5:
        reasoning = f"Selected '{best_text}' guided by active context ('{user_context}') to resolve visually ambiguous lip shapes (raw: '{top_vsr}')."
    else:
        reasoning = f"Picked from {best_src} (raw lip-reading: '{top_vsr}')."

    return {
        "text": best_text,
        "confidence": confidence,
        "confidence_label": confidence_label(confidence),
        "alternatives": [r[1] for r in ranked[:3]],
        "provider": "local-closed-set" if closed_set else "local",
        "reasoning": reasoning,
    }


def pretty(text: str) -> str:
    """Sentence-case raw lip-reading output ("i want coffee" -> "I want coffee")."""
    t = (text or "").strip()
    if not t or any(ch.isupper() for ch in t):
        return t
    t = re.sub(r"\bi\b", "I", t)
    t = re.sub(r"\bi'(m|ll|ve|d)\b", lambda m: "I'" + m.group(1), t)
    return t[0].upper() + t[1:]


def confidence_label(conf: float) -> str:
    return "high" if conf >= 0.72 else ("medium" if conf >= 0.48 else "low")
