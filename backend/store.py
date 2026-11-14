"""Tiny JSON-file storage for everything that must stay on this machine.

- profile.json : the user's phrases (with usage counts), names, quick buttons, preferences
- secrets.json : API keys (Groq). Never sent back to the browser.
- log.jsonl    : conversation log, so clinicians/family can review and export it

All files live in backend/data/ (git-ignored). Override with SILENTVOICE_DATA_DIR.
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from phrases import DEFAULT_PHRASES, DEFAULT_QUICK_BUTTONS, DEFAULT_QUIET_BUTTONS

DEFAULT_PREFERENCES: dict[str, Any] = {
    "use": "",                     # "" (not chosen yet) | care | quiet
    "destination": "loud",         # loud (a speaker) | show (large on screen)
    "speaker_id": "",              # browser audio-output device id; "" = the computer's default
    "privacy_blur": False,         # blur earlier lines until hovered/touched
    "keep_history": True,          # save the conversation log
    "auto_clear_minutes": 0,       # clear the screen after N idle minutes (0 = never)
    "capture_mode": "tap",         # tap (start/stop) | hold
    "follow_lips": True,           # keep the lip slot centred on the mouth
    "word_check": True,            # local text model re-ranks lip-reading guesses
    "recognition_mode": "fast",    # fast | accurate
    "phrases_only": False,         # closed-set mode: only ever output saved phrases
    "confirm_policy": "unsure",    # always | unsure | never
    "low_light_boost": True,
    "unmirror": False,
    "voice_name": "",
    "voice_rate": 1.0,
    "voice_pitch": 1.0,
    "use_my_voice": False,
    "text_scale": 1.0,
    "high_contrast": False,
    "alert_sound": True,
    "partner_mic": False,
}


def _default_profile() -> dict[str, Any]:
    return {
        "name": "",
        "names": [],
        "phrases": [dict(p, uses=0) for p in DEFAULT_PHRASES],
        "quick_buttons": copy.deepcopy(DEFAULT_QUICK_BUTTONS),
        "preferences": dict(DEFAULT_PREFERENCES),
        "onboarded": False,
    }


class Store:
    def __init__(self, data_dir: str | Path | None = None):
        base = data_dir or os.environ.get("SILENTVOICE_DATA_DIR") or (Path(__file__).resolve().parent / "data")
        self.dir = Path(base)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.profile_path = self.dir / "profile.json"
        self.secrets_path = self.dir / "secrets.json"
        self.log_path = self.dir / "log.jsonl"

    # ---------- helpers ----------
    def _read_json(self, path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def _write_json(self, path: Path, data: Any, private: bool = False) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        if private:
            os.chmod(tmp, 0o600)
        tmp.replace(path)

    # ---------- profile ----------
    def get_profile(self) -> dict[str, Any]:
        with self._lock:
            prof = self._read_json(self.profile_path, None)
            if prof is None:
                prof = _default_profile()
                self._write_json(self.profile_path, prof)
            # Fill in any keys added in newer versions
            defaults = _default_profile()
            for k, v in defaults.items():
                prof.setdefault(k, v)
            prefs = {**DEFAULT_PREFERENCES, **(prof.get("preferences") or {})}
            # Options removed in later versions fall back to their replacements.
            if prefs.get("capture_mode") not in ("tap", "hold"):
                prefs["capture_mode"] = "tap"
            if prefs.get("destination") not in ("loud", "show"):
                prefs["destination"] = "show" if prefs.get("use") == "quiet" else "loud"
            prefs.pop("sensitivity", None)
            prof["preferences"] = prefs
            return prof

    def update_profile(self, patch: dict[str, Any]) -> dict[str, Any]:
        prof = self.get_profile()
        with self._lock:
            for key in ("name", "names", "quick_buttons", "onboarded"):
                if key in patch:
                    prof[key] = patch[key]
            if "phrases" in patch:
                old_uses = {p["text"]: p.get("uses", 0) for p in prof["phrases"]}
                cleaned, seen = [], set()
                for p in patch["phrases"]:
                    text = str(p.get("text", "")).strip()
                    if not text or text.lower() in seen:
                        continue
                    seen.add(text.lower())
                    cleaned.append(
                        {
                            "text": text[:200],
                            "category": str(p.get("category") or "Mine")[:40],
                            "uses": int(p.get("uses", old_uses.get(text, 0))),
                        }
                    )
                prof["phrases"] = cleaned
            if "preferences" in patch:
                prof["preferences"] = {**prof["preferences"], **patch["preferences"]}
            self._write_json(self.profile_path, prof)
            return prof

    def apply_setup(self, use: str) -> dict[str, Any]:
        """Answer to the first-run question. Sets starting defaults; every one can be changed later."""
        if use not in ("care", "quiet"):
            raise ValueError("use must be 'care' or 'quiet'")
        if use == "care":
            prefs = {"use": "care", "destination": "loud", "confirm_policy": "unsure", "privacy_blur": False,
                     "keep_history": True, "auto_clear_minutes": 0, "alert_sound": True, "text_scale": 1.1}
            buttons = copy.deepcopy(DEFAULT_QUICK_BUTTONS)
        else:
            prefs = {"use": "quiet", "destination": "show", "confirm_policy": "unsure", "privacy_blur": True,
                     "keep_history": False, "auto_clear_minutes": 2, "alert_sound": False, "text_scale": 1.0}
            buttons = copy.deepcopy(DEFAULT_QUIET_BUTTONS)
        return self.update_profile({"preferences": prefs, "quick_buttons": buttons, "onboarded": True})

    def reset_profile(self) -> dict[str, Any]:
        with self._lock:
            prof = _default_profile()
            self._write_json(self.profile_path, prof)
            return prof

    def record_use(self, text: str) -> None:
        """Learn from what the user actually said: bump usage, or add as a new phrase."""
        text = (text or "").strip()
        if not text:
            return
        prof = self.get_profile()
        with self._lock:
            for p in prof["phrases"]:
                if p["text"].lower() == text.lower():
                    p["uses"] = p.get("uses", 0) + 1
                    break
            else:
                prof["phrases"].append({"text": text[:200], "category": "Mine", "uses": 1})
            self._write_json(self.profile_path, prof)

    def phrase_texts(self) -> list[str]:
        prof = self.get_profile()
        return [p["text"] for p in prof["phrases"]]

    def usage(self) -> dict[str, int]:
        return {p["text"]: p.get("uses", 0) for p in self.get_profile()["phrases"]}

    # ---------- secrets ----------
    def get_secret(self, key: str) -> str:
        with self._lock:
            val = self._read_json(self.secrets_path, {}).get(key, "")
        return (val or os.environ.get(key.upper(), "")).strip()

    def set_secrets(self, values: dict[str, str | None]) -> None:
        with self._lock:
            data = self._read_json(self.secrets_path, {})
            for k, v in values.items():
                if v is None:
                    continue
                if v == "":
                    data.pop(k, None)
                else:
                    data[k] = v.strip()
            self._write_json(self.secrets_path, data, private=True)

    def secrets_status(self) -> dict[str, bool]:
        return {
            "groq_api_key": bool(self.get_secret("groq_api_key")),
        }

    # ---------- conversation log ----------
    def append_log(self, entry: dict[str, Any]) -> dict[str, Any]:
        item = {
            "id": uuid.uuid4().hex[:12],
            "ts": time.time(),
            "speaker": entry.get("speaker", "user"),
            "text": str(entry.get("text", ""))[:1000],
            "source": entry.get("source", "lipread"),
            "confidence": entry.get("confidence"),
            "raw": entry.get("raw"),
        }
        with self._lock:
            with self.log_path.open("a") as f:
                f.write(json.dumps(item) + "\n")
        return item

    def read_log(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            if not self.log_path.exists():
                return []
            lines = self.log_path.read_text().splitlines()
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def clear_log(self) -> None:
        with self._lock:
            self.log_path.unlink(missing_ok=True)
