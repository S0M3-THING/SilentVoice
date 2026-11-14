"""SilentVoice API.

Run:  .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
The lip-reading model loads in the background, so the server (and the phrase board,
quick buttons, spelling, partner view...) is usable immediately.
"""

from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from context_selector import DEFAULT_LLM_MODEL, select_best_hypothesis
from phrases import is_urgent, pretty
from mouth import MouthLocator
from store import Store
from voice import VoiceError, VoiceService
from word_check import MLXWordChecker
import system_voice

load_dotenv(Path(__file__).resolve().parent / ".env")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class ProfilePatch(BaseModel):
    name: str | None = None
    names: list[str] | None = None
    phrases: list[dict] | None = None
    quick_buttons: list[dict] | None = None
    preferences: dict | None = None
    onboarded: bool | None = None


class SetupIn(BaseModel):
    use: Literal["care", "quiet"]


class UseIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class SecretsIn(BaseModel):
    groq_api_key: str | None = None


class LogIn(BaseModel):
    speaker: Literal["user", "partner"] = "user"
    text: str = Field(min_length=1, max_length=1000)
    source: str = "lipread"
    confidence: float | None = None
    raw: str | None = None


class TranscriptIn(BaseModel):
    transcript: str = Field(min_length=1, max_length=2000)


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class SystemTTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    voice: str = ""
    rate: float = 1.0


class ModelHolder:
    """Loads the VSR model on a background thread and reports its state."""

    def __init__(self):
        self.service = None
        self.state = "idle"  # idle | loading | ready | error
        self.error = ""
        self.loaded_at: float | None = None

    def start(self):
        if self.state in ("loading", "ready"):
            return
        self.state = "loading"
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            from vsr_service import VSRService  # heavy import (torch, mediapipe)

            self.service = VSRService()
            self.state = "ready"
            self.loaded_at = time.time()
        except Exception as exc:  # pragma: no cover - depends on local model install
            self.state = "error"
            self.error = f"{type(exc).__name__}: {exc}"


def create_app(
    store: Store | None = None,
    vsr_service: Any = None,
    autoload: bool = True,
    voice_engine: Any = None,
    voice_engines: dict | None = None,
    word_checker: Any = None,
    mouth_locator: Any = None,
) -> FastAPI:
    store = store or Store()
    voice = VoiceService(store, engine=voice_engine, engines=voice_engines)
    checker = word_checker if word_checker is not None else MLXWordChecker()
    mouth = mouth_locator if mouth_locator is not None else MouthLocator()
    model = ModelHolder()
    if vsr_service is not None:
        model.service, model.state = vsr_service, "ready"

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if autoload and model.state == "idle" and os.environ.get("SILENTVOICE_SKIP_MODEL") != "1":
            model.start()
        if autoload and voice.has_voice():
            voice.warm_up()
        if autoload and checker.state == "idle" and checker.availability()[0]:
            checker.load_in_background()
        yield

    app = FastAPI(title="SilentVoice API", version="1.0.0", lifespan=lifespan)
    app.state.store, app.state.model, app.state.voice = store, model, voice

    origins = os.environ.get("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

    # ------------------------------------------------------------------ health
    @app.get("/api/health")
    def health():
        svc = model.service
        return {
            "ok": True,
            "model_state": model.state,
            "model_error": model.error,
            "device": str(getattr(svc, "device", "")) if svc else None,
            "model": "Auto-AVSR LRS3_V_WER19.1 (local)",
            "ai_configured": bool(store.get_secret("groq_api_key")),
            "voice": voice.status(),
            "word_check": checker.status(),
            "mac_voice": system_voice.available(),
        }

    # ------------------------------------------------------------------ profile

    @app.get("/api/profile")
    def get_profile():
        return store.get_profile()

    @app.put("/api/profile")
    def put_profile(patch: ProfilePatch):
        prof = store.update_profile(patch.model_dump(exclude_none=True))
        if patch.preferences and "voice_model" in patch.preferences:
            voice.select(prof["preferences"].get("voice_model", "qwen3"))
        return prof

    @app.post("/api/profile/setup")
    def setup_profile(body: SetupIn):
        return store.apply_setup(body.use)

    @app.post("/api/profile/reset")
    def reset_profile():
        return store.reset_profile()


    @app.post("/api/phrases/use")
    def phrase_used(body: UseIn):
        store.record_use(body.text)
        return {"ok": True}

    # ------------------------------------------------------------------ secrets

    @app.get("/api/settings/secrets")
    def secrets_status():
        return store.secrets_status()

    @app.put("/api/settings/secrets")
    def set_secrets(body: SecretsIn):
        store.set_secrets(body.model_dump())
        return store.secrets_status()

    # ------------------------------------------------------------------ lip reading
    @app.post("/api/lipread")
    async def lipread(
        video: UploadFile = File(...),
        mode: Literal["fast", "accurate"] = Form("fast"),
        partner_text: str = Form(""),
        history_json: str = Form("[]"),
        phrases_only: bool = Form(False),
        hflip: bool = Form(False),
        enhance: bool = Form(True),
        groq_api_key: str = Form(""),
    ):
        if model.state != "ready" or model.service is None:
            detail = (
                f"Lip-reading model failed to load: {model.error}"
                if model.state == "error"
                else "Lip-reading model is still loading. Use the phrase board meanwhile."
            )
            raise HTTPException(status_code=503, detail=detail)

        raw = await video.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty video upload.")
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Clip too long. Keep it under ~10 seconds.")
        ext = Path(video.filename or "clip.webm").suffix or ".webm"

        try:
            history = json.loads(history_json or "[]")
            if not isinstance(history, list):
                history = []
        except json.JSONDecodeError:
            history = []

        try:
            vsr_out = model.service.transcribe_video_bytes(
                raw_bytes=raw, suffix=ext, mode=mode, top_k=10, hflip=hflip, enhance=enhance
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Lip-reading error: {exc}") from exc
        finally:
            del raw  # never keep the video around

        profile = store.get_profile()
        names = profile.get("names") or []
        phrase_bank = [p["text"] for p in profile["phrases"]]
        selection = await select_best_hypothesis(
            vsr_candidates=vsr_out["candidates"],
            phrase_bank=phrase_bank,
            partner_text=partner_text,
            history=history,
            closed_set=phrases_only,
            api_key=(groq_api_key or store.get_secret("groq_api_key") or "").strip(),
            llm_model=os.environ.get("SILENTVOICE_LLM_MODEL", DEFAULT_LLM_MODEL),
            usage=store.usage(),
            names=names,
            checker=checker if profile["preferences"].get("word_check", True) else None,
        )

        selection["text"] = pretty(selection.get("text", ""))
        selection["alternatives"] = list(dict.fromkeys(pretty(a) for a in selection.get("alternatives", [])))
        policy = profile["preferences"].get("confirm_policy", "unsure")
        urgent = is_urgent(selection.get("text", ""))
        needs_confirmation = (
            policy == "always"
            or (policy == "unsure" and (selection["confidence_label"] != "high" or selection.get("repaired")))
        )

        lat = vsr_out["latency_ms"]
        lat["llm_ms"] = selection.pop("llm_ms", 0.0)
        lat["end_to_end_ms"] = round(lat["total_ms"] + lat["llm_ms"], 1)

        return {
            "result": {**selection, "urgent": urgent, "needs_confirmation": needs_confirmation},
            "vsr_candidates": vsr_out["candidates"],
            "frames": vsr_out["frames"],
            "face_ratio": vsr_out["face_ratio"],
            "mode": vsr_out["mode"],
            "device": vsr_out["device"],
            "latency_ms": lat,
        }

    # ------------------------------------------------------------------ conversation log

    @app.get("/api/log")
    def get_log(limit: int = 200):
        return {"entries": store.read_log(limit=min(max(limit, 1), 2000))}

    @app.post("/api/log")
    def add_log(body: LogIn):
        entry = store.append_log(body.model_dump())
        if body.speaker == "user" and body.source in ("lipread", "spell", "typed"):
            store.record_use(body.text)
        return entry

    @app.delete("/api/log")
    def clear_log():
        store.clear_log()
        return {"ok": True}

    @app.get("/api/log/export")
    def export_log(format: Literal["txt", "csv"] = "txt"):
        entries = store.read_log(limit=100000)
        stamp = datetime.now().strftime("%Y-%m-%d")
        if format == "csv":
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["time", "speaker", "text", "source", "confidence", "raw_lipreading"])
            for e in entries:
                w.writerow([
                    datetime.fromtimestamp(e["ts"]).isoformat(timespec="seconds"),
                    e["speaker"], e["text"], e["source"], e.get("confidence") or "", e.get("raw") or "",
                ])
            return Response(
                buf.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="silentvoice-log-{stamp}.csv"'},
            )
        lines = [f"SilentVoice conversation log — exported {stamp}", ""]
        for e in entries:
            who = "Patient" if e["speaker"] == "user" else "Partner"
            t = datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d %H:%M")
            extra = f"  [{e['source']}" + (f", conf {e['confidence']}" if e.get("confidence") is not None else "") + "]"
            lines.append(f"{t}  {who}: {e['text']}{extra if e['speaker'] == 'user' else ''}")
        return PlainTextResponse(
            "\n".join(lines) + "\n",
            headers={"Content-Disposition": f'attachment; filename="silentvoice-log-{stamp}.txt"'},
        )

    # ------------------------------------------------------------------ own voice (local, Qwen3-TTS)
    @app.get("/api/voice")
    def voice_status():
        return voice.status()

    @app.post("/api/voice/reference")
    async def voice_reference(
        files: list[UploadFile] = File(...),
        transcript: str = Form(""),
        consent: bool = Form(False),
        source: Literal["upload", "recording"] = Form("upload"),
    ):
        payload = []
        total = 0
        for f in files[:10]:
            data = await f.read()
            total += len(data)
            if total > 200 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="Recordings are too large. Keep them under 200 MB in total.")
            if data:
                payload.append((f.filename or "recording.webm", data))
        try:
            return await run_in_threadpool(voice.create, payload, transcript, consent, source)
        except VoiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/voice/reference")
    def voice_reference_audio():
        if not voice.ref_path.exists():
            raise HTTPException(status_code=404, detail="No voice sample yet.")
        return FileResponse(voice.ref_path, media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @app.put("/api/voice/transcript")
    def voice_transcript(body: TranscriptIn):
        try:
            return voice.set_transcript(body.transcript)
        except VoiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/voice/warmup")
    def voice_warmup():
        voice.warm_up()
        return voice.status()

    @app.delete("/api/voice")
    def voice_delete():
        return voice.delete()

    @app.post("/api/tts")
    async def tts(body: TTSIn):
        try:
            audio = await run_in_threadpool(voice.speak, body.text)
        except VoiceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Your voice couldn’t be generated: {type(exc).__name__}") from exc
        return Response(audio, media_type="audio/wav")

    # ------------------------------------------------------------------ the Mac's voices
    @app.get("/api/voices/system")
    def system_voices():
        return {"available": system_voice.available(), "voices": system_voice.list_voices()}

    @app.post("/api/tts/system")
    async def tts_system(body: SystemTTSIn):
        if not system_voice.available():
            raise HTTPException(status_code=501, detail="The Mac voice is only available on macOS.")
        try:
            audio = await run_in_threadpool(system_voice.speak_to_wav, body.text, body.voice, body.rate)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"The Mac voice failed: {type(exc).__name__}") from exc
        return Response(audio, media_type="audio/wav")

    # ------------------------------------------------------------------ lip tracking
    @app.post("/api/mouth")
    async def find_mouth(frame: UploadFile = File(...)):
        data = await frame.read()
        if not data or len(data) > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Send one small JPEG frame.")
        try:
            return await run_in_threadpool(mouth.locate, data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            mouth.error = f"{type(exc).__name__}: {exc}"
            raise HTTPException(status_code=503, detail="Lip tracking is unavailable.") from exc
        finally:
            del data

    return app


app = create_app()
