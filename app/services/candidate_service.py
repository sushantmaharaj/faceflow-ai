"""
FaceFlow AI — Candidate Service
Downloads candidate images, detects faces, computes similarity, ranks results.
"""

from __future__ import annotations

import io
from typing import Optional

import httpx
import numpy as np

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import CandidateRecord, SearchResult
from app.services import face_service
from app.utils.image import image_to_bgr_array
from app.utils.urls import is_ssrf_safe

logger = get_logger(__name__)

# Max size to download per candidate image
MAX_CANDIDATE_BYTES = 5 * 1024 * 1024  # 5 MB

ALLOWED_CANDIDATE_MIMES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif",
}


async def download_and_analyze_candidate(
    search_result: SearchResult,
    source_embedding: np.ndarray,
    client: httpx.AsyncClient,
) -> Optional[CandidateRecord]:
    """
    Download a candidate image, detect faces in it, compute similarity.
    Returns CandidateRecord or None if candidate is unusable.
    """
    # Choose best URL: prefer direct image_url over page url
    image_url = search_result.image_url or search_result.thumbnail_url
    if not image_url:
        image_url = search_result.url

    if not image_url:
        logger.debug("Candidate %d: no image URL, skipping", search_result.position)
        return None

    # SSRF protection
    if not is_ssrf_safe(image_url):
        logger.warning("Candidate %d: SSRF block on %s", search_result.position, image_url)
        return None

    # Download
    image_bytes = await _download_image(client, image_url, search_result.position)
    if image_bytes is None:
        return None

    # Decode
    try:
        img_bgr = image_to_bgr_array(image_bytes)
    except ValueError as e:
        logger.debug("Candidate %d: decode error: %s", search_result.position, e)
        return None

    # Detect all faces in candidate
    candidate_embeddings = face_service.detect_faces_for_candidate(img_bgr)
    if not candidate_embeddings:
        logger.debug("Candidate %d: no faces detected", search_result.position)
        return None

    # Best similarity across all detected faces
    best_similarity = max(
        face_service.compute_cosine_similarity(source_embedding, emb)
        for emb in candidate_embeddings
    )

    logger.info(
        "Candidate %d [%s]: %d face(s), best similarity=%.4f",
        search_result.position,
        image_url[:60],
        len(candidate_embeddings),
        best_similarity,
    )

    return CandidateRecord(
        url=search_result.url or image_url,
        title=search_result.title,
        source=search_result.source,
        image_url=image_url,
        face_similarity=round(best_similarity, 6),
        candidate_face_count=len(candidate_embeddings),
        search_position=search_result.position,
        result_type=search_result.result_type,
    )


async def _download_image(
    client: httpx.AsyncClient,
    url: str,
    position: int,
) -> Optional[bytes]:
    """Download a candidate image with safety checks. Returns bytes or None."""
    try:
        async with client.stream("GET", url, follow_redirects=True) as resp:
            if resp.status_code != 200:
                logger.debug(
                    "Candidate %d: HTTP %d for %s",
                    position, resp.status_code, url[:60]
                )
                return None

            # Check content type
            content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type and content_type not in ALLOWED_CANDIDATE_MIMES:
                logger.debug(
                    "Candidate %d: rejected content-type '%s'",
                    position, content_type
                )
                return None

            # Stream with size limit
            chunks = []
            total = 0
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                total += len(chunk)
                if total > MAX_CANDIDATE_BYTES:
                    logger.debug("Candidate %d: size exceeded limit", position)
                    return None
                chunks.append(chunk)

            return b"".join(chunks)

    except httpx.TimeoutException:
        logger.debug("Candidate %d: download timeout for %s", position, url[:60])
        return None
    except httpx.RequestError as e:
        logger.debug("Candidate %d: request error: %s", position, e)
        return None
    except Exception as e:
        logger.warning("Candidate %d: unexpected error: %s", position, e)
        return None


async def rank_candidates(
    search_results: list[SearchResult],
    source_embedding: np.ndarray,
) -> list[CandidateRecord]:
    """
    Download and analyze ALL candidate images IN PARALLEL using asyncio.gather().
    Returns candidates sorted by face_similarity DESC.
    """
    import asyncio

    async with httpx.AsyncClient(
        timeout=10,  # tighter timeout per candidate
        follow_redirects=True,
        max_redirects=5,
        headers={"User-Agent": "Mozilla/5.0 (compatible; FaceFlowBot/1.0)"},
    ) as client:
        tasks = [
            download_and_analyze_candidate(result, source_embedding, client)
            for result in search_results
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    candidates: list[CandidateRecord] = []
    for item in results:
        if isinstance(item, CandidateRecord):
            candidates.append(item)
        elif isinstance(item, Exception):
            logger.debug("Candidate task error: %s", item)

    # Sort: face_similarity DESC, then exact_match before visual_match, then position ASC
    def sort_key(c: CandidateRecord):
        type_score = 0 if c.result_type == "exact_match" else 1
        return (-c.face_similarity, type_score, c.search_position)

    candidates.sort(key=sort_key)
    return candidates



def select_best_candidate(
    candidates: list[CandidateRecord],
) -> Optional[CandidateRecord]:
    """
    Return the best candidate if it meets the configured threshold.
    Returns None if no candidate meets FACE_MATCH_THRESHOLD.
    """
    if not candidates:
        return None
    best = candidates[0]
    if best.face_similarity < settings.face_match_threshold:
        logger.info(
            "Best candidate similarity %.4f is below threshold %.2f — no match",
            best.face_similarity,
            settings.face_match_threshold,
        )
        return None
    return best
