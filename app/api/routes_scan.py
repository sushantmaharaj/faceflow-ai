"""
FaceFlow AI — Main Scan Route
POST /api/scan — Orchestrates the complete pipeline.
"""

from __future__ import annotations

import os
import tempfile
import traceback
from typing import Optional

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import (
    BlockchainRecord,
    CandidateRecord,
    CanonicalRecord,
    ErrorDetail,
    FaceDetectionInfo,
    ScanResponse,
    VerificationResult,
)
from app.services import face_service
from app.services.blockchain_service import get_blockchain_registry
from app.services.candidate_service import rank_candidates, select_best_candidate
from app.services.fingerprint_service import build_canonical_record, compute_fingerprint
from app.services.person_service import identify_person
from app.services.search_service import get_search_provider
from app.services.verification_service import verify_record_against_chain
from app.utils.image import image_to_bgr_array, validate_image_bytes
from app.services.face_service import similarity_label

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["Scan"])


@router.post("/scan", response_model=ScanResponse)
async def scan_image(
    image: UploadFile = File(...),
    face_index: Optional[int] = Form(None),
) -> ScanResponse:
    """
    Full pipeline:
    1. Validate image
    2. Detect face + generate embedding
    3. Google Lens search via SerpApi
    4. Download + rank candidate images by face similarity
    5. Select best candidate (above threshold)
    6. Build canonical record
    7. Generate SHA-256 fingerprint
    8. Register fingerprint on Ethereum Sepolia
    9. Independently verify the registered fingerprint
    """
    raw_bytes = await image.read()

    # ── Step 1: Validate image ───────────────────────────────
    try:
        pil_img, mime = validate_image_bytes(raw_bytes, image.filename or "")
    except ValueError as e:
        return _error("INVALID_IMAGE", str(e))

    # ── Step 2: Face Detection & Embedding ───────────────────
    try:
        img_bgr = image_to_bgr_array(raw_bytes)
    except ValueError as e:
        return _error("INVALID_IMAGE", str(e))

    try:
        face_result = face_service.detect_and_embed(img_bgr, face_index)
    except face_service.MultipleFacesError as e:
        info = FaceDetectionInfo(
            face_count=len(e.bboxes),
            embedding_model=settings.insightface_model_name,
            embedding_dimension=0,
            bboxes=e.bboxes,
        )
        return _error("MULTIPLE_FACES", "Multiple faces detected. Please select one.", face_detection=info)
    except ValueError as e:
        code = str(e)
        messages = {
            "NO_FACE": "No face detected in the uploaded image.",
            "DETECTION_ERROR": "Face detection failed. Please try another image.",
            "INVALID_FACE_INDEX": "Selected face index is invalid.",
        }
        return _error(code, messages.get(code, "Face detection error."))

    source_embedding: np.ndarray = face_result.embedding
    face_info = FaceDetectionInfo(
        face_count=face_result.face_count,
        embedding_model=face_result.embedding_model,
        embedding_dimension=face_result.embedding_dimension,
    )

    logger.info(
        "Face detected: model=%s dim=%d",
        face_result.embedding_model,
        face_result.embedding_dimension,
    )

    # ── Step 3: Web Search ───────────────────────────────────
    if not settings.serpapi_configured:
        return _error(
            "SEARCH_API_ERROR",
            "SERPAPI_API_KEY is not configured. See .env.example.",
            face_detection=face_info,
        )

    try:
        search_results = await get_search_provider().search(raw_bytes)
    except RuntimeError as e:
        return _error(str(e).split(":")[0], str(e), face_detection=face_info)
    except Exception as e:
        logger.error("Search error: %s", traceback.format_exc())
        return _error("SEARCH_API_ERROR", "Web search failed.", face_detection=face_info)

    if not search_results:
        return _error(
            "NO_SEARCH_RESULTS",
            "No results returned from web search.",
            face_detection=face_info,
            search_results_count=0,
        )

    logger.info("Search returned %d results", len(search_results))

    # ── Step 4: Candidate Evaluation ─────────────────────────
    candidates: list[CandidateRecord] = await rank_candidates(
        search_results, source_embedding
    )
    logger.info("Ranked %d candidates with detected faces", len(candidates))

    # ── Step 5: Candidate Selection ──────────────────────────
    best = select_best_candidate(candidates)

    if best is None:
        return ScanResponse(
            success=True,
            status="no_match",
            face_detection=face_info,
            search_results_count=len(search_results),
            candidates_evaluated=len(candidates),
            match_label="No match",
            error=ErrorDetail(
                code="NO_MATCH_ABOVE_THRESHOLD",
                message=f"No candidate exceeded the face similarity threshold of {settings.face_match_threshold}.",
            ),
        )

    match_label = similarity_label(best.face_similarity)
    logger.info(
        "Best candidate: similarity=%.4f label=%s url=%s",
        best.face_similarity,
        match_label,
        best.url[:60],
    )

    # ── Step 5.5: Person Identification ─────────────────────
    person_profile = None
    try:
        person_profile = await identify_person(raw_bytes, candidates, search_results)
    except Exception as e:
        logger.warning("Person identification failed: %s", e)


    # ── Step 6: Canonical Record ─────────────────────────────
    canonical_record: CanonicalRecord = build_canonical_record(best)
    canonical_json, fingerprint = compute_fingerprint(canonical_record)

    # ── Step 7: Blockchain Registration ──────────────────────
    if not settings.blockchain_configured:
        return ScanResponse(
            success=True,
            status="match",
            face_detection=face_info,
            search_results_count=len(search_results),
            candidates_evaluated=len(candidates),
            best_candidate=best,
            match_label=match_label,
            person=person_profile,
            canonical_record=canonical_record,
            fingerprint=fingerprint,
            error=ErrorDetail(
                code="BLOCKCHAIN_NOT_CONFIGURED",
                message="Blockchain credentials not configured. See .env.example.",
            ),
        )

    try:
        blockchain_record: BlockchainRecord = await get_blockchain_registry().register(fingerprint)
    except Exception as e:
        logger.error("Blockchain registration error: %s", traceback.format_exc())
        return ScanResponse(
            success=True,
            status="match",
            face_detection=face_info,
            search_results_count=len(search_results),
            candidates_evaluated=len(candidates),
            best_candidate=best,
            match_label=match_label,
            person=person_profile,
            canonical_record=canonical_record,
            fingerprint=fingerprint,
            error=ErrorDetail(
                code="TRANSACTION_FAILED",
                message=f"Blockchain registration failed: {str(e)[:200]}",
            ),
        )

    # ── Step 8: Independent Verification ─────────────────────
    verify_result: Optional[VerificationResult] = None
    try:
        verify_result = await verify_record_against_chain(
            record_dict=canonical_record.model_dump(),
            tx_hash=blockchain_record.transaction_hash,
        )
    except Exception as e:
        logger.error("Verification error: %s", e)
        verify_result = VerificationResult(
            verified=False,
            local_fingerprint=fingerprint,
            reason="VERIFICATION_FAILED",
        )

    return ScanResponse(
        success=True,
        status="match",
        face_detection=face_info,
        search_results_count=len(search_results),
        candidates_evaluated=len(candidates),
        best_candidate=best,
        match_label=match_label,
        person=person_profile,
        canonical_record=canonical_record,
        fingerprint=fingerprint,
        blockchain=blockchain_record,
        verification=verify_result,
    )


# ── Helper ───────────────────────────────────────────────────

def _error(
    code: str,
    message: str,
    face_detection: Optional[FaceDetectionInfo] = None,
    search_results_count: int = 0,
) -> ScanResponse:
    return ScanResponse(
        success=False,
        status=code,
        face_detection=face_detection,
        search_results_count=search_results_count,
        error=ErrorDetail(code=code, message=message),
    )
