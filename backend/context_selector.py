"""Pick the final sentence from the lip-reading n-best list.

Order of preference:
0. Word check (local text model, when ready) re-orders the lip-reading guesses by how likely
   each is as a reply in this conversation. Everything below then works on that order.
1. Phrases-only mode -> deterministic local matcher (instant, offline).
2. LLM configured (Groq, key kept server-side) -> context-aware repair of look-alike words.
3. Anything fails / no key / offline -> deterministic local matcher.

Safety: the LLM may only swap words that look identical on the lips. The response says
whether the text was "repaired" (not one of the raw lip-reading guesses) so the UI can
ask the user to confirm before speaking words they might not have said.
"""

from __future__ import annotations

import json
import os
import time
from typing import Iterable

import httpx

from starlette.concurrency import run_in_threadpool

from phrases import clean_beam_hallucinations, confidence_label, expand_homophenes, normalize_text, rank_locally
from word_check import check_guesses

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_LLM_MODEL = "moonshotai/kimi-k2-instruct"

SYSTEM_PROMPT = """You are SilentVoice's hypothesis disambiguator for a visual lip-reading (VSR) model with audio assistance.
The person using SilentVoice has impaired speech or is in a communication setting where speech needs assistance.
Whatever you choose will be spoken aloud as their words. Getting it wrong puts words in their mouth.

PRIORITY 1: MICROPHONE AUDIO TRANSCRIPTION HAS HIGHEST PRIORITY.
If "patient_audio_heard" is provided, the patient actually voiced these words into their microphone.
VSR models suffer from beam-search repetition loops (e.g. repeating phrases like "... dinosaur right dinosaur") or nonsense homophene guesses (e.g. "live in my medicine" instead of "give me my medicine").
NEVER override clear, sensible words in "patient_audio_heard" with garbled visual hallucinations.
Use the visual lip movement as a VISUAL VERIFIER to confirm or disambiguate visemes, not to override the patient's spoken words.

PRIORITY 2: ACTIVE USER CONTEXT HAS STRONG DISAMBIGUATION POWER.
The user's situation or state is given in "user_context" (e.g. "im VERY THIRSTY", "in hospital after surgery", "at a park").
Visual lip-reading cannot distinguish homophenes (sounds and words that look identical on lips).
- "I need water" and "I didn't want" look virtually identical on the mouth. If context is thirsty or hydration, select "I need water"!
- "give me my medicine" and "live in my medicine" look virtually identical. If context is medical or hospital, select "give me my medicine"!
- Heavily favor sentences, domain vocabulary, and personal phrases that directly match the active "user_context".

PRIORITY 3: PRAGMATIC HUMAN LIKELIHOOD & COMMON SENSE.
Always prefer pragmatically plausible, real-world human utterances over absurd word combinations or beam hallucinations:
- "I really want to eat a huge mountain of tacos right now" is natural and plausible; "huge mountain of dinosaur right dinosaur" is an absurd hallucination.
- "give me my medicine" or "bring my medicine" is plausible; "live in my medicine" is nonsensical.
- Strip any stuttered or repeated loop artifacts (e.g. "X right X" -> "X").

Lip reading homophene rules:
- {p, b, m} look identical; {f, v} look identical; {t, d, n, l} look very similar
- {k, g}, {ch, sh, j} and {s, z} look similar
- Vowels and short unstressed words are often dropped or swapped.

Your job:
1. If "patient_audio_heard" is present, favor it as the primary sentence and verify against visual visemes.
2. If "user_context" is present, strongly guide word choice and repair homophenes in favor of that context.
3. Pick or minimally repair the intended sentence. ONLY substitute visually confusable words.
4. Provide the 3 most plausible options in "alternatives".

Return strict JSON:
{"text": "best sentence", "confidence": 0.0-1.0, "alternatives": ["option 1", "option 2", "option 3"],
 "reasoning": "one short sentence"}"""


def _is_repaired(text: str, vsr_candidates: list[dict], phrases: list[str]) -> bool:
    key = normalize_text(text)
    pool = {normalize_text(c.get("text", "")) for c in vsr_candidates} | {normalize_text(p) for p in phrases}
    return key not in pool


async def select_best_hypothesis(
    vsr_candidates: list[dict],
    phrase_bank: Iterable[str],
    partner_text: str = "",
    history: list[dict] | None = None,
    closed_set: bool = False,
    api_key: str | None = None,
    llm_model: str | None = None,
    usage: dict[str, int] | None = None,
    names: list[str] | None = None,
    checker=None,
    user_context: str = "",
    patient_audio_text: str = "",
) -> dict:
    t0 = time.perf_counter()
    phrases = [p.strip() for p in phrase_bank if p and p.strip()]
    raw_candidates = vsr_candidates
    expanded_cands = expand_homophenes(vsr_candidates) if not closed_set else vsr_candidates
    check = None
    if not closed_set and expanded_cands:
        check = await run_in_threadpool(check_guesses, checker, expanded_cands, partner_text, history, user_context)
        if check:
            vsr_candidates = check["candidates"]
        else:
            vsr_candidates = expanded_cands

    def _finish(res: dict) -> dict:
        if check:
            res["word_check"] = {"changed_top": check["changed_top"], "ms": check["ms"]}
            res["provider"] = f"{res.get('provider', 'local')}+word-check"
            # The text model picked something other than the lips' first guess: always ask.
            if check["changed_top"] and normalize_text(res.get("text", "")) == normalize_text(vsr_candidates[0]["text"]):
                res["confidence"] = min(res.get("confidence", 0.0), 0.6)
                res["confidence_label"] = confidence_label(res["confidence"])
                res["reasoning"] = (
                    f"The word check preferred this over the lips' first guess ({raw_candidates[0]['text']!r}). "
                    + str(res.get("reasoning", ""))
                )
        res["llm_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return res

    def _local() -> dict:
        res = rank_locally(
            vsr_candidates,
            phrases,
            partner_text=partner_text,
            closed_set=closed_set,
            usage=usage,
            user_context=user_context,
            patient_audio_text=patient_audio_text,
        )
        res["repaired"] = False
        return _finish(res)

    if closed_set or not vsr_candidates:
        return _local()

    key = (api_key or os.environ.get("GROQ_API_KEY") or "").strip()
    if not key:
        return _local()

    clean_audio = clean_beam_hallucinations(patient_audio_text).strip()
    model = (llm_model or os.environ.get("SILENTVOICE_LLM_MODEL") or DEFAULT_LLM_MODEL).strip()
    payload = {
        "user_context": user_context or "(none provided)",
        "patient_audio_heard": clean_audio or "(none)",
        "partner_just_said": partner_text or "(nothing captured)",
        "recent_conversation": (history or [])[-6:],
        "vsr_nbest_hypotheses": [
            {"rank": i + 1, "text": clean_beam_hallucinations(c["text"]), "prob": c.get("prob", 0.0)}
            for i, c in enumerate(vsr_candidates[:10])
        ],
        "personal_phrases": sorted(phrases, key=lambda p: -(usage or {}).get(p, 0))[:40],
        "important_names": (names or [])[:20],
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                GROQ_CHAT_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(payload)},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 220,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception as exc:  # network down, bad key, bad JSON...
        res = _local()
        res["reasoning"] = f"AI unavailable ({type(exc).__name__}); used offline matcher. {res['reasoning']}"
        return res

    fallback_text = clean_audio or vsr_candidates[0]["text"]
    text = clean_beam_hallucinations(str(parsed.get("text") or fallback_text)).strip()
    conf = round(max(0.0, min(1.0, float(parsed.get("confidence", 0.85 if clean_audio else 0.5)))), 2)
    alts = [clean_beam_hallucinations(str(a)).strip() for a in (parsed.get("alternatives") or []) if str(a).strip()]
    if text and text not in alts:
        alts = [text] + alts
    if clean_audio and clean_audio not in alts:
        alts.insert(1, clean_audio)
    for c in vsr_candidates[:3]:
        cleaned_c = clean_beam_hallucinations(c["text"])
        if len(alts) >= 3:
            break
        if cleaned_c and cleaned_c not in alts:
            alts.append(cleaned_c)

    return _finish({
        "text": text,
        "confidence": conf,
        "confidence_label": confidence_label(conf),
        "alternatives": alts[:3],
        "provider": f"groq:{model}",
        "reasoning": str(parsed.get("reasoning") or "Chosen using conversation context."),
        "repaired": _is_repaired(text, raw_candidates, phrases),
    })
