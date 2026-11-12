import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="SilentVoice")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class Candidate(BaseModel):
    text: str = Field(min_length=1, max_length=500, pattern=r"\S")
    visual_score: float = Field(ge=0, le=1)


class RerankRequest(BaseModel):
    candidates: list[Candidate] = Field(min_length=1, max_length=10)
    partner_text: str = Field(default="", max_length=1000)
    personal_phrases: list[str] = Field(default_factory=list, max_length=20)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/rerank")
def rerank(request: RerankRequest) -> list[Candidate]:
    context_words = set(re.findall(r"\w+", request.partner_text.casefold()))
    personal_phrases = {phrase.strip().casefold() for phrase in request.personal_phrases}

    def score(candidate: Candidate) -> float:
        words = set(re.findall(r"\w+", candidate.text.casefold()))
        overlap = len(words & context_words) / max(len(words), 1)
        personal_match = candidate.text.strip().casefold() in personal_phrases
        return candidate.visual_score + 0.15 * overlap + 0.05 * personal_match

    return sorted(request.candidates, key=score, reverse=True)[:3]
