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
    return 0.45 * char_sim + 0.55 * vis_sim


_YES_NO_STARTS = ("do", "are", "is", "can", "will", "would", "did", "should", "have", "does", "could", "want")
_TOPICS = [
    ({"order", "drink", "coffee", "tea", "eat", "food", "hungry", "lunch", "dinner", "breakfast", "thirsty"},
     {"coffee", "tea", "water", "oat", "milk", "eat", "check", "hungry", "juice", "ice", "drink"}),
    ({"pain", "hurt", "hurts", "sore", "feel", "feeling", "comfortable"},
     {"pain", "hurts", "sick", "dizzy", "okay", "cold", "hot", "fine", "better", "worse"}),
    ({"family", "wife", "husband", "son", "daughter", "visit", "call", "mom", "dad"},
     {"family", "call", "love", "phone", "visit"}),
]
_STOP = {"the", "you", "and", "for", "are", "can", "what", "how", "your", "with", "that", "this", "would", "like"}


def _words(text: str) -> list[str]:
    return normalize_text(text).split()


def _context_boost(candidate: str, partner_text: str) -> float:
    """Whole-word context match between the partner's last line and a candidate reply."""
    p_words, c_words = _words(partner_text), set(_words(candidate))
    if not p_words or not c_words:
        return 0.0
    boost = 0.0
    if p_words[0] in _YES_NO_STARTS and c_words & {"yes", "no", "maybe"}:
        boost += 0.12
    overlap = ({w for w in p_words if len(w) >= 3} - _STOP) & c_words
    boost += min(0.12, 0.06 * len(overlap))
    p_set = set(p_words)
    for triggers, answers in _TOPICS:
        if p_set & triggers and c_words & answers:
            boost += 0.15
            break
    return min(0.3, boost)


def name_variants(candidates: list[dict], names: Iterable[str], max_new: int = 4) -> list[dict]:
    """Make the user's saved names show up in lip-reading guesses.

    Names are hard to lip-read: "call Akash" often comes back as "call a cash". For every
    guess, any run of 1-3 words that looks like a saved name on the lips becomes an extra
    guess with the name swapped in. Exact matches just get the name's capitals.
    Short names need a closer match, so "ham" doesn't turn into "Sam".
    """
    names = [n.strip() for n in names if n and n.strip()]
    if not names or not candidates:
        return candidates
    out = [dict(c) for c in candidates]
    extra: dict[str, dict] = {}
    for c in out[:5]:
        words = c["text"].split()
        prob = float(c.get("prob", 0.0))
        for name in names:
            key = normalize_text(name).replace(" ", "")
            if len(key) < 2:
                continue
            need = 0.7 if len(key) >= 5 else 0.8 if len(key) == 4 else 0.9
            best = None
            for i in range(len(words)):
                for j in range(i + 1, min(len(words), i + 3) + 1):
                    span = "".join(normalize_text(w) for w in words[i:j])
                    if not span or abs(len(span) - len(key)) > max(2, len(key) // 2):
                        continue
                    sim = viseme_similarity(span, key)
                    if sim >= need and (best is None or sim > best[0]):
                        best = (sim, i, j)
            if best is None:
                continue
            sim, i, j = best
            new_text = " ".join(words[:i] + [name] + words[j:])
            if sim >= 0.99 and j - i == 1:
                words = words[:i] + [name] + words[j:]  # same word: just use the right capitals
                c["text"] = new_text
                continue
            k = normalize_text(new_text)
            score = prob * (0.5 + 0.6 * sim)
            if k not in extra or extra[k]["prob"] < score:
                extra[k] = {"text": new_text, "prob": round(score, 4), "name_match": name}
    known = {normalize_text(c["text"]) for c in out}
    new = sorted((v for k, v in extra.items() if k not in known), key=lambda v: -v["prob"])[:max_new]
    return sorted(out + new, key=lambda c: -float(c.get("prob", 0.0)))


def rank_locally(
    vsr_candidates: list[dict],
    phrase_bank: Iterable[str],
    partner_text: str = "",
    closed_set: bool = False,
    usage: dict[str, int] | None = None,
) -> dict:
    """Choose the most likely sentence from the lip-reading n-best list.

    Open mode: the lip-reading guesses compete on probability + conversation context.
    A saved phrase can only replace them when it is a strong visual match (it "repairs"
    look-alike words). Closed set ("only my saved phrases"): always the closest phrase.
    `usage` (phrase -> times picked) nudges habitual phrases up.
    """
    phrases = [p.strip() for p in phrase_bank if p and p.strip()]
    usage = usage or {}
    if not vsr_candidates:
        return {
            "text": "",
            "confidence": 0.0,
            "confidence_label": "low",
            "alternatives": phrases[:3],
            "provider": "local",
            "reasoning": "No lip-reading guesses returned.",
        }

    cands = vsr_candidates[:5]
    total_prob = sum(float(c.get("prob", 0.0)) for c in cands) or 1.0
    probs = [float(c.get("prob", 0.0)) / total_prob for c in cands]
    top_vsr = cands[0]["text"]
    max_use = max(usage.values()) if usage else 0

    pool: dict[str, tuple[float, str, str, float]] = {}  # key -> (score, text, source, sim)

    def add(score: float, text: str, source: str, sim: float = 1.0) -> None:
        key = normalize_text(text)
        if key and (key not in pool or pool[key][0] < score):
            pool[key] = (score, text, source, sim)

    if not closed_set:
        for c, pr in zip(cands, probs):
            add(pr + _context_boost(c["text"], partner_text), c["text"], "lip-reading")

    strong = 0.0 if closed_set else 0.78
    for phrase in phrases:
        best_sim, best_pr = 0.0, 0.0
        for c, pr in zip(cands, probs):
            sim = viseme_similarity(phrase, c["text"])
            if sim > best_sim or (sim == best_sim and pr > best_pr):
                best_sim, best_pr = sim, pr
        if best_sim < strong:
            continue
        habit = 0.05 * (usage.get(phrase, 0) / max_use) if max_use else 0.0
        if closed_set:
            score = best_sim * (0.7 + 0.3 * best_pr) + _context_boost(phrase, partner_text) + habit
        else:
            score = best_pr * (0.6 + 0.6 * best_sim) + _context_boost(phrase, partner_text) + habit
        add(score, phrase, "phrase bank", best_sim)

    ranked = sorted(pool.values(), key=lambda x: x[0], reverse=True)
    if not ranked:
        ranked = [(0.3, top_vsr, "lip-reading", 1.0)]

    best_score, best_text, best_src, best_sim = ranked[0]
    top3 = sum(r[0] for r in ranked[:3]) or 1.0
    share = best_score / top3
    if closed_set:
        confidence = 0.2 + 0.5 * best_sim + 0.3 * max(0.0, share - 0.34) / 0.66
    else:
        confidence = 0.25 + 0.75 * share
    # A close runner-up means we are genuinely unsure.
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.05:
        confidence = min(confidence, 0.6)
    # Never assert an urgent/medical sentence from a weak visual match without asking.
    if best_src == "phrase bank" and best_sim < 0.9 and is_urgent(best_text):
        confidence = min(confidence, 0.6)
    confidence = round(max(0.05, min(0.98, confidence)), 2)

    return {
        "text": best_text,
        "confidence": confidence,
        "confidence_label": confidence_label(confidence),
        "alternatives": [r[1] for r in ranked[:3]],
        "provider": "local-closed-set" if closed_set else "local",
        "reasoning": f"Picked from {best_src} (raw lip-reading: '{top_vsr}').",
    }


def pretty(text: str) -> str:
    """Sentence-case raw lip-reading output ("i want coffee" -> "I want coffee")."""
    t = (text or "").strip()
    if not t:
        return t
    t = re.sub(r"\bi\b", "I", t)
    t = re.sub(r"\bi'(m|ll|ve|d)\b", lambda m: "I'" + m.group(1), t)
    return t[0].upper() + t[1:]


def confidence_label(conf: float) -> str:
    return "high" if conf >= 0.72 else ("medium" if conf >= 0.48 else "low")
