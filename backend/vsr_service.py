"""Auto-AVSR (Chaplin / LRS3_V_WER19.1) visual speech recognition service with n-best extraction.

Privacy: uploaded clips only ever live inside a TemporaryDirectory and are deleted
as soon as frames are decoded. Nothing is written to disk permanently.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import torch
from huggingface_hub import hf_hub_download

BACKEND_DIR = Path(__file__).resolve().parent


def _find_chaplin_dir() -> Path:
    """Locate the vendored Chaplin / Auto-AVSR code (see setup.sh)."""
    candidates = [
        os.environ.get("CHAPLIN_DIR", ""),
        str(BACKEND_DIR / "vendor" / "chaplin"),
        str(BACKEND_DIR.parent / "chaplin"),
    ]
    for cand in candidates:
        if cand and (Path(cand) / "pipelines").is_dir():
            return Path(cand)
    raise RuntimeError(
        "Chaplin model code not found. Run ./setup.sh from the repo root "
        "(it clones it into backend/vendor/chaplin)."
    )


CHAPLIN_DIR = _find_chaplin_dir()
if str(CHAPLIN_DIR) not in sys.path:
    sys.path.insert(0, str(CHAPLIN_DIR))

from espnet.asr.asr_utils import parse_hypothesis  # noqa: E402
from pipelines.data.transforms import VideoTransform  # noqa: E402
from pipelines.detectors.mediapipe.detector import LandmarksDetector  # noqa: E402
from pipelines.detectors.mediapipe.video_process import VideoProcess  # noqa: E402
from pipelines.model import AVSR, get_beam_search_decoder  # noqa: E402


FFMPEG_BIN = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"


def ensure_chaplin_weights() -> tuple[Path, Path, Path, Path]:
    """Download Amanvir/LRS3_V_WER19.1 + lm_en_subword from Hugging Face if missing."""
    vsr_dir = CHAPLIN_DIR / "benchmarks" / "LRS3" / "models" / "LRS3_V_WER19.1"
    lm_dir = CHAPLIN_DIR / "benchmarks" / "LRS3" / "language_models" / "lm_en_subword"
    vsr_dir.mkdir(parents=True, exist_ok=True)
    lm_dir.mkdir(parents=True, exist_ok=True)

    downloads = [
        ("Amanvir/LRS3_V_WER19.1", "model.json", vsr_dir / "model.json"),
        ("Amanvir/LRS3_V_WER19.1", "model.pth", vsr_dir / "model.pth"),
        ("Amanvir/lm_en_subword", "model.json", lm_dir / "model.json"),
        ("Amanvir/lm_en_subword", "model.pth", lm_dir / "model.pth"),
    ]
    for repo_id, filename, target_path in downloads:
        if not target_path.exists() or target_path.stat().st_size == 0:
            cached = Path(hf_hub_download(repo_id=repo_id, filename=filename))
            # Symlink or copy into chaplin's expected benchmark directory
            if target_path.exists() or target_path.is_symlink():
                target_path.unlink()
            try:
                target_path.symlink_to(cached)
            except OSError:
                import shutil

                shutil.copy2(cached, target_path)

    return (
        vsr_dir / "model.pth",
        vsr_dir / "model.json",
        lm_dir / "model.pth",
        lm_dir / "model.json",
    )


def apply_clahe_rgb(frame_rgb: np.ndarray) -> np.ndarray:
    """Boost local facial contrast in dim webcam lighting without changing hue."""
    lab = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_eq = clahe.apply(l_ch)
    merged = cv2.merge((l_eq, a_ch, b_ch))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)


def normalize_video_to_25fps_rgb(
    raw_bytes: bytes,
    suffix: str = ".webm",
    hflip: bool = False,
    enhance: bool = True,
    max_seconds: float = 15.0,
) -> tuple[np.ndarray, float]:
    """Transcode incoming browser recording to 25fps silent video and return (T, H, W, 3) RGB uint8."""
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = Path(tmpdir) / f"input{suffix}"
        out_path = Path(tmpdir) / "norm_25fps.mp4"
        in_path.write_bytes(raw_bytes)

        vf_parts = []
        if hflip:
            vf_parts.append("hflip")
        vf_parts.append("fps=25")
        # Cap max width at 640px for faster MediaPipe + affine warping on laptop CPU
        vf_parts.append("scale='min(640,iw)':-2")

        ffmpeg_exe = FFMPEG_BIN if Path(FFMPEG_BIN).exists() else "ffmpeg"
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i",
            str(in_path),
            "-t",
            str(max_seconds),
            "-vf",
            ",".join(vf_parts),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if proc.returncode != 0 or not out_path.exists():
            raise RuntimeError(f"ffmpeg failed: {proc.stderr[-300:]}")

        cap = cv2.VideoCapture(str(out_path))
        frames: list[np.ndarray] = []
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            if enhance:
                rgb = apply_clahe_rgb(rgb)
            frames.append(rgb)
        cap.release()

    if not frames:
        raise ValueError("No video frames could be decoded from recording.")
    return np.asarray(frames, dtype=np.uint8), round((time.perf_counter() - t0) * 1000, 1)


class VSRService:
    """Thread-safe holder for Auto-AVSR model with fast and accurate beam decoders."""

    def __init__(self, device: str | None = None):
        env_dev = os.environ.get("SILENTVOICE_DEVICE", "").strip()
        if device:
            chosen = device
        elif env_dev:
            chosen = env_dev
        elif torch.cuda.is_available():
            chosen = "cuda:0"
        else:
            chosen = "cpu"
        if chosen == "mps" and not torch.backends.mps.is_available():
            chosen = "cpu"
        self.device = torch.device(chosen)

        model_pth, model_json, lm_pth, lm_json = ensure_chaplin_weights()

        # Load core model once in fast decoder config, then attach accurate decoder sharing weights
        self.avsr = AVSR(
            modality="video",
            model_path=str(model_pth),
            model_conf=str(model_json),
            rnnlm=str(lm_pth),
            rnnlm_conf=str(lm_json),
            penalty=0.0,
            ctc_weight=0.1,
            lm_weight=0.3,
            beam_size=25,
            device=self.device,
        )
        self.accurate_beam_search = self.avsr.beam_search
        self.fast_beam_search = get_beam_search_decoder(
            self.avsr.model,
            self.avsr.token_list,
            rnnlm=None,
            rnnlm_conf=None,
            penalty=0.0,
            ctc_weight=0.1,
            lm_weight=0.0,
            beam_size=10,
        )
        self.fast_beam_search.to(device=self.device).eval()

        self.landmarks_detector = LandmarksDetector()
        self.video_process = VideoProcess(convert_gray=True)
        self.video_transform = VideoTransform(speed_rate=1.0)

    def _detect_landmarks(self, frames: np.ndarray) -> tuple[list, float]:
        landmarks = self.landmarks_detector.detect(frames, self.landmarks_detector.full_range_detector)
        detected = sum(1 for lm in landmarks if lm is not None)
        if detected == 0:
            landmarks = self.landmarks_detector.detect(frames, self.landmarks_detector.short_range_detector)
            detected = sum(1 for lm in landmarks if lm is not None)
        ratio = detected / max(1, len(landmarks))
        return landmarks, round(ratio, 2)

    def _clean_text(self, raw_text: str) -> str:
        text = raw_text.replace("▁", " ").replace("<eos>", "").replace("<blank>", "").strip()
        return " ".join(text.split()).lower()

    def transcribe_video_bytes(
        self,
        raw_bytes: bytes,
        suffix: str = ".webm",
        mode: Literal["fast", "accurate"] = "fast",
        top_k: int = 10,
        hflip: bool = False,
        enhance: bool = True,
    ) -> dict:
        t_start = time.perf_counter()
        frames, ffmpeg_ms = normalize_video_to_25fps_rgb(
            raw_bytes, suffix=suffix, hflip=hflip, enhance=enhance
        )
        if len(frames) < 5:
            raise ValueError(f"Clip too short ({len(frames)} frames). Hold for at least 0.5–1.0s while mouthing.")

        t_prep = time.perf_counter()
        landmarks, face_ratio = self._detect_landmarks(frames)
        if face_ratio == 0.0:
            raise ValueError("No face detected in the recording. Ensure good front lighting and stay centered.")

        try:
            cropped = self.video_process(frames, landmarks)
        except Exception as exc:
            raise ValueError(
                f"Could not crop mouth cleanly ({exc}). Keep your whole face centered and upright."
            ) from exc
        if cropped is None or len(cropped) == 0:
            raise ValueError("Could not align mouth ROI across frames.")

        tensor = torch.tensor(cropped)
        tensor = self.video_transform(tensor)
        preprocess_ms = round((time.perf_counter() - t_prep) * 1000, 1)

        t_inf = time.perf_counter()
        beam = self.fast_beam_search if mode == "fast" else self.accurate_beam_search
        with torch.no_grad():
            enc_feats = self.avsr.model.encode(tensor.to(self.device))
            hyps = beam(enc_feats)

        # Convert beam log-scores to normalized softmax probabilities over top_k
        sliced = hyps[: min(len(hyps), top_k)]
        raw_scores = [float(h.score) for h in sliced]
        max_s = max(raw_scores) if raw_scores else 0.0
        exp_scores = [math.exp(max(-30.0, s - max_s)) for s in raw_scores]
        sum_exp = sum(exp_scores) or 1.0

        candidates: list[dict] = []
        seen: set[str] = set()
        for h, exp_s in zip(sliced, exp_scores):
            rec_text, _, _, score = parse_hypothesis(h.asdict(), self.avsr.token_list)
            cleaned = self._clean_text(rec_text)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                candidates.append(
                    {
                        "text": cleaned,
                        "score": round(float(score), 3),
                        "prob": round(exp_s / sum_exp, 3),
                    }
                )

        infer_ms = round((time.perf_counter() - t_inf) * 1000, 1)
        total_ms = round((time.perf_counter() - t_start) * 1000, 1)

        return {
            "candidates": candidates,
            "frames": int(len(frames)),
            "face_ratio": face_ratio,
            "mode": mode,
            "device": str(self.device),
            "latency_ms": {
                "ffmpeg_ms": ffmpeg_ms,
                "preprocess_ms": preprocess_ms,
                "infer_ms": infer_ms,
                "total_ms": total_ms,
            },
        }
