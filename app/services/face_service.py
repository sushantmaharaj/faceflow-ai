"""
FaceFlow AI — Face Detection & Embedding Service
Uses InsightFace (buffalo_l) for detection + ArcFace embedding.
"""

from __future__ import annotations

import io
from typing import Optional, Tuple

import numpy as np

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Module-level lazy singleton ──────────────────────────────
_app = None


def _get_face_app():
    """Lazy-load InsightFace FaceAnalysis. Thread-safe enough for single-process."""
    global _app
    if _app is None:
        import insightface
        from insightface.app import FaceAnalysis

        logger.info("Loading InsightFace model: %s", settings.insightface_model_name)
        _app = FaceAnalysis(
            name=settings.insightface_model_name,
            providers=["CPUExecutionProvider"],
        )
        _app.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("InsightFace model loaded successfully.")
    return _app


def is_model_loaded() -> bool:
    """Quick check — does not trigger load."""
    return _app is not None


def preload_model() -> None:
    """Force model load at startup so first request is not slow."""
    _get_face_app()


# ── Public API ───────────────────────────────────────────────

class FaceDetectionResult:
    __slots__ = ("face_count", "embedding", "embedding_model", "embedding_dimension")

    def __init__(
        self,
        face_count: int,
        embedding: Optional[np.ndarray],
        embedding_model: str,
        embedding_dimension: int,
    ):
        self.face_count = face_count
        self.embedding = embedding
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension

class MultipleFacesError(ValueError):
    def __init__(self, bboxes: list[list[float]]):
        super().__init__("MULTIPLE_FACES")
        self.bboxes = bboxes


def detect_and_embed(image_bgr: np.ndarray, face_index: Optional[int] = None) -> FaceDetectionResult:
    """
    Detect faces in a BGR numpy array and return a normalized embedding.

    Raises:
        ValueError with codes: NO_FACE | DETECTION_ERROR | INVALID_FACE_INDEX
        MultipleFacesError if >1 face and no index provided
    """
    app = _get_face_app()

    try:
        faces = app.get(image_bgr)
    except Exception as e:
        logger.error("InsightFace detection error: %s", e)
        raise ValueError("DETECTION_ERROR") from e

    face_count = len(faces)

    if face_count == 0:
        raise ValueError("NO_FACE")

    # Sort faces left-to-right (by xmin) for stable indexing
    faces = sorted(faces, key=lambda f: f.bbox[0])

    if face_count > 1 and face_index is None:
        bboxes = [f.bbox.tolist() for f in faces]
        raise MultipleFacesError(bboxes)

    if face_index is not None:
        if face_index < 0 or face_index >= face_count:
            raise ValueError("INVALID_FACE_INDEX")
        face = faces[face_index]
    else:
        face = faces[0]
        
    embedding: np.ndarray = face.embedding  # 512-dim ArcFace embedding

    # L2 normalization
    norm = np.linalg.norm(embedding)
    if norm < 1e-10:
        raise ValueError("DETECTION_ERROR")
    normalized = embedding / norm

    return FaceDetectionResult(
        face_count=1,
        embedding=normalized,
        embedding_model=settings.insightface_model_name,
        embedding_dimension=len(normalized),
    )


def compute_cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two L2-normalized embeddings.
    Since both are already normalized, this reduces to a dot product.
    Returns value in [-1, 1]; typical face-match range is [0.0, 1.0].
    """
    similarity = float(np.dot(a, b))
    # Clamp to [0, 1] for display purposes (negative means very different)
    return max(0.0, min(1.0, similarity))


def similarity_label(score: float) -> str:
    """Map cosine similarity score to a human-readable label."""
    if score >= settings.face_strong_match_threshold:
        return "Strong match"
    elif score >= settings.face_match_threshold:
        return "Possible match"
    else:
        return "Weak match"


def detect_faces_for_candidate(image_bgr: np.ndarray) -> list[np.ndarray]:
    """
    Detect ALL faces in a candidate image and return list of normalized embeddings.
    Used for multi-face candidate images. Returns empty list on any error.
    """
    app = _get_face_app()
    try:
        faces = app.get(image_bgr)
    except Exception as e:
        logger.warning("Candidate face detection error: %s", e)
        return []

    embeddings = []
    for face in faces:
        emb = face.embedding
        norm = np.linalg.norm(emb)
        if norm < 1e-10:
            continue
        embeddings.append(emb / norm)

    return embeddings
