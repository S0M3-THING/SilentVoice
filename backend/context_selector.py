"""Pick the final sentence from the lip-reading n-best list.

Order of preference:
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

from phrases import confidence_label, normalize_text, rank_locally

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_LLM_MODEL = "moonshotai/kimi-k2-instruct"

SYSTEM_PROMPT = """You are SilentVoice's hypothesis disambiguator for a visual lip-reading (VSR) model.
The person using SilentVoice cannot make sound (for example after a tracheostomy or laryngectomy),
so whatever you choose will be spoken aloud as their words. Getting it wrong puts words in their mouth.

Lip reading cannot distinguish homophenes (sounds that look identical on lips):
- {p, b, m} look identical; {f, v} look identical; {t, d, n, l} look very similar
- {k, g}, {ch, sh, j} and {s, z} look similar
- Vowels and short unstressed words ("a", "the", "to") are often dropped or swapped.

Your job:
1. Examine the VSR n-best hypotheses (ordered by beam score), what the conversation partner just said,
   recent conversation, and the user's personal phrases and names.
2. Pick or minimally repair the intended sentence. ONLY substitute visually confusable words
   (e.g. "toffee" -> "coffee", "pat" -> "bat", "meat" -> "eat").
3. Never invent a sentence that is not supported by the hypotheses. If the hypotheses are garbled,
   set confidence below 0.45 and give the 3 most plausible options so the user can tap one.
4. Be conservative with anything medical (pain, breathing, medication): prefer lower confidence.

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
) -> dict:
    t0 = time.perf_counter()
    phrases = [p.strip() for p in phrase_bank if p and p.strip()]

    def _local() -> dict:
        res = rank_locally(vsr_candidates, phrases, partner_text=partner_text, closed_set=closed_set, usage=usage)
        res["repaired"] = False
        res["llm_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return res

    if closed_set or not vsr_candidates:
        return _local()

    key = (api_key or os.environ.get("GROQ_API_KEY") or "").strip()
    if not key:
        return _local()

    model = (llm_model or os.environ.get("SILENTVOICE_LLM_MODEL") or DEFAULT_LLM_MODEL).strip()
    payload = {
        "partner_just_said": partner_text or "(nothing captured)",
        "recent_conversation": (history or [])[-6:],
        "vsr_nbest_hypotheses": [
            {"rank": i + 1, "text": c["text"], "prob": c.get("prob", 0.0)} for i, c in enumerate(vsr_candidates[:10])
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

    text = str(parsed.get("text") or vsr_candidates[0]["text"]).strip()
    conf = round(max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))), 2)
    alts = [str(a).strip() for a in (parsed.get("alternatives") or []) if str(a).strip()]
    if text and text not in alts:
        alts = [text] + alts
    for c in vsr_candidates[:3]:
        if len(alts) >= 3:
            break
        if c["text"] and c["text"] not in alts:
            alts.append(c["text"])

    return {
        "text": text,
        "confidence": conf,
        "confidence_label": confidence_label(conf),
        "alternatives": alts[:3],
        "provider": f"groq:{model}",
        "reasoning": str(parsed.get("reasoning") or "Chosen using conversation context."),
        "repaired": _is_repaired(text, vsr_candidates, phrases),
        "llm_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
