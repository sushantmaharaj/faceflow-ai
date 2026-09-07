"""
FaceFlow AI — Fingerprint Service
Builds canonical record from best candidate and generates SHA-256 fingerprint.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.models.schemas import CanonicalRecord, CandidateRecord
from app.utils.canonical_json import fingerprint_record
from app.utils.urls import extract_domain, canonicalize_url

logger = get_logger(__name__)


def build_canonical_record(candidate: CandidateRecord) -> CanonicalRecord:
    """
    Normalize a candidate result into a stable canonical record.
    Only stable fields are included — no timestamps, no request IDs.
    """
    source_url = canonicalize_url(candidate.url) if candidate.url else ""
    image_url = canonicalize_url(candidate.image_url) if candidate.image_url else ""
    domain = extract_domain(source_url) if source_url else ""

    return CanonicalRecord(
        schema_version="1",
        source_url=source_url,
        source_title=candidate.title.strip() if candidate.title else "",
        source_domain=domain,
        image_url=image_url,
        search_engine="google_lens",
        search_result_type=candidate.result_type,
        face_similarity=round(candidate.face_similarity, 6),
    )


def compute_fingerprint(record: CanonicalRecord) -> tuple[str, str]:
    """
    Compute the canonical JSON and SHA-256 fingerprint of a CanonicalRecord.
    Returns (canonical_json_str, fingerprint_hex).
    """
    record_dict = record.model_dump()
    canonical_json, fingerprint = fingerprint_record(record_dict)

    logger.info("Fingerprint computed: %s...", fingerprint[:16])
    return canonical_json, fingerprint
