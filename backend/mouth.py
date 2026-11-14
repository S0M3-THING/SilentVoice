"""Find the mouth in a camera frame, so the lip slot can follow the user when they move.

The browser sends a small JPEG a few times a second; this returns where the mouth is as
fractions of the frame. Uses MediaPipe's face detector (already installed for lip reading),
which gives a mouth-centre keypoint. Frames are decoded in memory and never written to disk.
"""

from __future__ import annotations

import threading

import numpy as np


class MouthLocator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._detector = None
        self.error = ""

    def _load(self):
        if self._detector is None:
            import mediapipe as mp  # heavy import, only when first needed

            # model_selection=1 is the full-range model: works from bed-tray distance too.
            self._detector = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
        return self._detector

    def locate(self, jpeg: bytes) -> dict:
        import cv2

        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Could not read the camera frame.")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        with self._lock:
            result = self._load().process(rgb)
        if not result.detections:
            return {"found": False}
        det = max(result.detections, key=lambda d: d.location_data.relative_bounding_box.width)
        box = det.location_data.relative_bounding_box
        kp = det.location_data.relative_keypoints  # 0/1 eyes, 2 nose tip, 3 mouth centre
        clamp = lambda v: float(min(1.0, max(0.0, v)))
        return {
            "found": True,
            "x": clamp(kp[3].x),
            "y": clamp(kp[3].y),
            "face_w": clamp(box.width),
            "face_h": clamp(box.height),
            "score": round(float(det.score[0]), 3),
        }
