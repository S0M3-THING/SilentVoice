"""Speak in the user's own voice.

Uses ElevenLabs Instant Voice Cloning: the user uploads ~1 minute of old recordings of
their voice (voicemails, videos) and every phrase is then spoken in that voice.
Generated audio is cached on disk, so phrases that were spoken once (quick buttons,
favourite phrases) keep working in the user's voice even when offline.
If nothing is configured the browser falls back to the system voice.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

API = "https://api.elevenlabs.io/v1"
TTS_MODEL = "eleven_flash_v2_5"  # lowest-latency model


class VoiceError(RuntimeError):
    pass


class VoiceService:
    def __init__(self, store):
        self.store = store
        self.cache_dir = store.dir / "tts_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self) -> str:
        key = self.store.get_secret("elevenlabs_api_key")
        if not key:
            raise VoiceError("Add an ElevenLabs API key in Settings → Voice first.")
        return key

    def status(self) -> dict:
        return {
            "configured": bool(self.store.get_secret("elevenlabs_api_key")),
            "has_voice": bool(self.store.get_secret("elevenlabs_voice_id")),
            "cached_phrases": len(list(self.cache_dir.glob("*.mp3"))),
        }

    async def clone(self, name: str, files: list[tuple[str, bytes, str]]) -> str:
        if not files:
            raise VoiceError("Upload at least one recording of your voice.")
        key = self._key()
        multipart = [("files", (fname, data, ctype or "audio/mpeg")) for fname, data, ctype in files]
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{API}/voices/add",
                headers={"xi-api-key": key},
                data={"name": name or "My SilentVoice", "description": "Created by SilentVoice"},
                files=multipart,
            )
        if resp.status_code >= 400:
            raise VoiceError(f"Voice cloning failed ({resp.status_code}): {resp.text[:200]}")
        voice_id = resp.json().get("voice_id", "")
        if not voice_id:
            raise VoiceError("Voice cloning returned no voice id.")
        self.store.set_secrets({"elevenlabs_voice_id": voice_id})
        self.clear_cache()
        return voice_id

    async def delete_voice(self) -> None:
        voice_id = self.store.get_secret("elevenlabs_voice_id")
        key = self.store.get_secret("elevenlabs_api_key")
        if voice_id and key:
            async with httpx.AsyncClient(timeout=30) as client:
                await client.delete(f"{API}/voices/{voice_id}", headers={"xi-api-key": key})
        self.store.set_secrets({"elevenlabs_voice_id": ""})
        self.clear_cache()

    def clear_cache(self) -> None:
        for f in self.cache_dir.glob("*.mp3"):
            f.unlink(missing_ok=True)

    def _cache_path(self, voice_id: str, text: str) -> Path:
        digest = hashlib.sha1(f"{voice_id}|{text.strip().lower()}".encode()).hexdigest()
        return self.cache_dir / f"{digest}.mp3"

    async def tts(self, text: str) -> bytes:
        text = (text or "").strip()
        if not text:
            raise VoiceError("Nothing to say.")
        voice_id = self.store.get_secret("elevenlabs_voice_id")
        if not voice_id:
            raise VoiceError("No personal voice yet.")
        cached = self._cache_path(voice_id, text)
        if cached.exists():
            return cached.read_bytes()
        key = self._key()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{API}/text-to-speech/{voice_id}",
                headers={"xi-api-key": key, "Accept": "audio/mpeg"},
                json={"text": text[:500], "model_id": TTS_MODEL},
            )
        if resp.status_code >= 400:
            raise VoiceError(f"Speech failed ({resp.status_code}).")
        cached.write_bytes(resp.content)
        return resp.content
