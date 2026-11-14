"""Word check: a small local text model makes sense of lip-reading guesses.

Lip reading can't tell look-alike words apart ("coffee" / "toffee", "bat" / "pat"). A text
model can: given what the other person just asked, "I want some coffee" is far more likely
than "I want some toffee". We ask the model how probable each guess is as the next line of
the conversation (average log-probability per token) and blend that with the lip-reading
model's own score:

    score = log(p_lip_reading) + WEIGHT * avg_logprob_text_model

When the reading is unsure, the model also rewrites the guesses into up to three clear,
natural sentences that would look the same on the lips ("What do you think about your weight
all" -> "What do you think about the weather?"). Rewrites that drift too far from what the lips
showed are dropped, and SilentVoice always asks before saying a rewritten sentence.

Runs on the Mac with MLX: Gemma 4 E2B (Google, Apache 2.0, 4-bit, about 3.6 GB), chosen for
being quick (about 2.3B parameters do the work per word) and accurate for its size. Nothing
leaves the computer. Without Apple Silicon it switches itself off.
Override with SILENTVOICE_CHECK_MODEL (for example mlx-community/gemma-4-e4b-it-4bit on a
Mac with 16 GB or more, or mlx-community/Phi-4-mini-instruct-4bit).
"""

from __future__ import annotations

import math
import os
import platform
import re
import threading
import time

from mlx_guard import MLX_LOCK

DEFAULT_MODEL = "mlx-community/gemma-4-e2b-it-4bit"
MAX_REWRITES = 3
MIN_LIP_MATCH = 0.5  # a rewrite must still look like what the lips did
WEIGHT = 1.0  # how much the text model counts against the lip-reading score
MAX_CANDIDATES = 5

PREAMBLE = (
    "A short conversation. One person can't speak out loud right now, so they mouth short, "
    "plain sentences that are read from their lips.\n"
)


def build_context(partner_text: str = "", history: list[dict] | None = None, names: list[str] | None = None) -> str:
    """The conversation so far, ending where the user's sentence starts."""
    lines = [PREAMBLE]
    names = [n.strip() for n in (names or []) if n and n.strip()]
    if names:
        lines.append(f"People they often mention: {', '.join(names[:20])}.\n")
    for h in (history or [])[-4:]:
        text = str(h.get("text", "")).strip()
        if text:
            who = "Me" if h.get("speaker") == "me" else "Them"
            lines.append(f"{who}: {text}\n")
    partner_text = (partner_text or "").strip()
    if partner_text and not (lines[-1].startswith("Them:") and partner_text in lines[-1]):
        lines.append(f"Them: {partner_text}\n")
    lines.append("Me:")
    return "".join(lines)


def blend(candidates: list[dict], text_scores: list[float], weight: float = WEIGHT) -> list[dict]:
    """Combine lip-reading probabilities with text-model scores. Returns re-sorted copies
    whose `prob` is the blended probability, plus `vsr_prob` and `text_score` for the record."""
    if not candidates:
        return []
    raw = [max(float(c.get("prob", 0.0)), 1e-6) for c in candidates]
    total = sum(raw)
    logits = [math.log(p / total) + weight * s for p, s in zip(raw, text_scores)]
    top = max(logits)
    exps = [math.exp(v - top) for v in logits]
    z = sum(exps)
    out = [
        {**c, "prob": round(e / z, 4), "vsr_prob": round(p / total, 4), "text_score": round(s, 3)}
        for c, e, p, s in zip(candidates, exps, raw, text_scores)
    ]
    return sorted(out, key=lambda c: c["prob"], reverse=True)


REWRITE_PROMPT = """You help a person who can't speak out loud. A lip-reading model watched them mouth one short sentence and returned these guesses, best first:
{guesses}

Lip reading mixes up sounds that look the same on the lips: p/b/m, f/v, t/d/n/l, k/g, s/z, ch/sh/j. It also drops or garbles short words like "a", "the", "to".
{context}
Write the {n} most likely sentences they actually mouthed. Each one must be a short, natural, complete sentence that would look almost the same on the lips as the guesses: same rhythm, same mouth shapes. Prefer everyday requests and answers that fit the conversation. Don't add new ideas.
Reply with only the {n} sentences, one per line, no numbering."""


def build_rewrite_prompt(guesses: list[str], partner_text: str = "", history: list[dict] | None = None,
                         names: list[str] | None = None, n: int = MAX_REWRITES) -> str:
    ctx = []
    for h in (history or [])[-4:]:
        text = str(h.get("text", "")).strip()
        if text:
            ctx.append(f'{"They" if h.get("speaker") == "me" else "The other person"} said earlier: "{text}"')
    if (partner_text or "").strip():
        ctx.append(f'The other person just said: "{partner_text.strip()}"')
    names = [x.strip() for x in (names or []) if x and x.strip()]
    if names:
        ctx.append(f"People they often mention: {', '.join(names[:20])}.")
    listed = "\n".join(f"{i + 1}. {g}" for i, g in enumerate(guesses))
    return REWRITE_PROMPT.format(guesses=listed, context=("\n".join(ctx) + "\n") if ctx else "", n=n)


def parse_rewrites(text: str, n: int = MAX_REWRITES) -> list[str]:
    """Pull clean sentences out of the model's reply."""
    # Drop any hidden reasoning a model might print before its answer.
    text = re.split(r"<channel\|>|</think>", text)[-1]
    out = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip().strip('"').strip()
        if not line or len(line) > 160 or line.endswith(":"):
            continue
        if line.lower() not in (o.lower() for o in out):
            out.append(line)
    return out[:n]


def keep_close_rewrites(rewrites: list[str], guesses: list[str]) -> list[str]:
    """Drop rewrites that wouldn't look like what the lips did (the model inventing things)."""
    from phrases import viseme_similarity

    return [r for r in rewrites if max((viseme_similarity(r, g) for g in guesses), default=0) >= MIN_LIP_MATCH]


class MLXWordChecker:
    name = "Gemma 4 E2B (local)"

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id or os.environ.get("SILENTVOICE_CHECK_MODEL") or DEFAULT_MODEL
        self.state = "idle"  # idle | loading | ready | error | off
        self.error = ""
        self._model = None
        self._tok = None
        self._lock = threading.Lock()

    def availability(self) -> tuple[bool, str]:
        if os.environ.get("SILENTVOICE_WORD_CHECK", "1") == "0":
            return False, "Turned off with SILENTVOICE_WORD_CHECK=0."
        if not (platform.system() == "Darwin" and platform.machine() == "arm64"):
            return False, "The word check needs a Mac with Apple Silicon."
        try:
            import mlx_lm  # noqa: F401
        except Exception:
            return False, "The word check isn't installed. Run ./setup.sh again."
        return True, ""

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            ok, why = self.availability()
            if not ok:
                self.state, self.error = "off", why
                return
            self.state = "loading"
            try:
                from huggingface_hub import snapshot_download
                from mlx_lm import load

                # Download first without holding the GPU lock, so your voice keeps working meanwhile.
                path = snapshot_download(
                    self.model_id,
                    allow_patterns=["*.json", "*.safetensors", "*.py", "*.model", "*.tiktoken", "*.txt", "*.jinja"],
                )
                with MLX_LOCK:
                    self._model, self._tok = load(path)
                self.state, self.error = "ready", ""
            except Exception as exc:  # download failed, out of memory...
                self.state, self.error = "error", f"{type(exc).__name__}: {exc}"

    def load_in_background(self) -> None:
        threading.Thread(target=self.load, daemon=True).start()

    @property
    def ready(self) -> bool:
        return self.state == "ready"

    def score(self, context: str, sentences: list[str]) -> list[float]:
        """Average log-probability per token of each sentence (plus a line end) after `context`."""
        import mlx.core as mx

        # Don't hold up the reading if the GPU is busy (say, making your voice): skip the check.
        if not MLX_LOCK.acquire(timeout=3):
            raise TimeoutError("GPU busy")
        try:
            prefix = list(self._tok.encode(context))
            scores = []
            for s in sentences:
                ids = list(self._tok.encode(context + " " + s.strip() + "\n"))
                start = _shared_prefix(prefix, ids)
                if start == 0 or start >= len(ids):
                    scores.append(-20.0)
                    continue
                logits = self._model(mx.array(ids)[None])[0]  # (T, vocab)
                logp = logits - mx.logsumexp(logits, axis=-1, keepdims=True)
                targets = mx.array(ids[start:])
                picked = mx.take_along_axis(logp[start - 1 : len(ids) - 1], targets[:, None], axis=-1)
                scores.append(float(picked.mean().item()))
            return scores
        finally:
            MLX_LOCK.release()

    def rewrite(self, prompt: str) -> str:
        """Generate the model's answer to a rewrite prompt. Turns off "thinking" to stay quick."""
        from mlx_lm import generate

        messages = [{"role": "user", "content": prompt}]
        try:
            text = self._tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False, enable_thinking=False)
        except Exception:
            text = prompt + "\n"
        if not MLX_LOCK.acquire(timeout=5):
            raise TimeoutError("GPU busy")
        try:
            return generate(self._model, self._tok, prompt=text, max_tokens=120, verbose=False)
        finally:
            MLX_LOCK.release()

    def status(self) -> dict:
        ok, why = self.availability()
        return {"available": ok, "state": self.state if ok else "off", "model": self.name, "reason": why or self.error}


def _shared_prefix(a: list[int], b: list[int]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def check_guesses(
    checker, candidates: list[dict], partner_text: str = "", history: list[dict] | None = None, names: list[str] | None = None
) -> dict | None:
    """Rescore lip-reading guesses with the text model. None when the checker isn't ready."""
    if checker is None or not getattr(checker, "ready", False) or len(candidates) < 2:
        return None
    t0 = time.perf_counter()
    cands = [c for c in candidates[:MAX_CANDIDATES] if c.get("text", "").strip()]
    if len(cands) < 2:
        return None
    try:
        scores = checker.score(build_context(partner_text, history, names), [c["text"] for c in cands])
    except Exception:
        return None
    ranked = blend(cands, scores)
    return {
        "candidates": ranked,
        "changed_top": ranked[0]["text"] != cands[0]["text"],
        "ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def rewrite_guesses(
    checker, candidates: list[dict], partner_text: str = "", history: list[dict] | None = None, names: list[str] | None = None
) -> dict | None:
    """Turn unclear lip-reading guesses into clear sentences. None when it can't help."""
    if checker is None or not getattr(checker, "ready", False) or not hasattr(checker, "rewrite"):
        return None
    guesses = [c["text"] for c in candidates[:5] if c.get("text", "").strip()]
    if not guesses:
        return None
    t0 = time.perf_counter()
    try:
        reply = checker.rewrite(build_rewrite_prompt(guesses, partner_text, history, names))
    except Exception:
        return None
    sentences = keep_close_rewrites(parse_rewrites(reply), guesses)
    if not sentences:
        return None
    return {"sentences": sentences, "ms": round((time.perf_counter() - t0) * 1000, 1)}
