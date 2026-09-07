"""
FaceFlow AI — Pydantic Schemas / Data Models
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────

class SearchResult(BaseModel):
    title: str = ""
    source: str = ""
    url: str = ""
    thumbnail_url: str = ""
    image_url: str = ""
    position: int = 0
    result_type: str = "visual_match"  # "exact_match" | "visual_match"


# ─────────────────────────────────────────────
# Candidate
# ─────────────────────────────────────────────

class CandidateRecord(BaseModel):
    url: str
    title: str = ""
    source: str = ""
    image_url: str = ""
    face_similarity: float
    candidate_face_count: int
    search_position: int
    result_type: str = "visual_match"


# ─────────────────────────────────────────────
# Canonical record stored / verified on-chain
# ─────────────────────────────────────────────

class CanonicalRecord(BaseModel):
    schema_version: str = "1"
    source_url: str
    source_title: str
    source_domain: str
    image_url: str
    search_engine: str = "google_lens"
    search_result_type: str
    face_similarity: float


# ─────────────────────────────────────────────
# Person identification
# ─────────────────────────────────────────────

class PersonProfile(BaseModel):
    name: str
    description: Optional[str] = None   # e.g. "Indian actor"
    extract: Optional[str] = None        # Wikipedia paragraph
    image_url: Optional[str] = None
    wikipedia_url: Optional[str] = None
    page_id: Optional[str] = None
    # Wikidata / Gemini / TMDB sourced
    wikidata_id: Optional[str] = None   # e.g. "Q37079"
    birth_date: Optional[str] = None    # e.g. "27 December 1965"
    nationality: Optional[str] = None   # e.g. "India"
    occupation: Optional[str] = None    # e.g. "Actor, Film producer"
    known_for: Optional[str] = None     # e.g. "Bajrangi Bhaijaan, Sultan"


# ─────────────────────────────────────────────
# Blockchain
# ─────────────────────────────────────────────

class BlockchainRecord(BaseModel):
    network: str = "Ethereum Sepolia"
    chain_id: int = 11155111
    transaction_hash: str
    fingerprint: str
    confirmed: bool
    block_number: Optional[int] = None
    registered_at: Optional[int] = None  # unix timestamp


# ─────────────────────────────────────────────
# Verification
# ─────────────────────────────────────────────

class VerificationResult(BaseModel):
    verified: bool
    local_fingerprint: str
    onchain_fingerprint: Optional[str] = None
    transaction_hash: Optional[str] = None
    registered_at: Optional[int] = None
    reason: str  # MATCH | NOT_REGISTERED | FINGERPRINT_MISMATCH | BLOCKCHAIN_UNAVAILABLE | INVALID_TRANSACTION


# ─────────────────────────────────────────────
# API Request / Response models
# ─────────────────────────────────────────────

class FaceDetectionInfo(BaseModel):
    face_count: int
    embedding_model: str
    embedding_dimension: int
    bboxes: Optional[list[list[float]]] = None


class ErrorDetail(BaseModel):
    code: str
    message: str


class ScanResponse(BaseModel):
    success: bool
    status: str  # "match" | "no_match" | error code
    # Face detection
    face_detection: Optional[FaceDetectionInfo] = None
    # Search
    search_results_count: int = 0
    candidates_evaluated: int = 0
    # Best candidate
    best_candidate: Optional[CandidateRecord] = None
    match_label: str = ""  # "Strong match" | "Possible match" | "Weak match" | "No match"
    # Person identification
    person: Optional[PersonProfile] = None
    # Canonical record (returned so browser can use for verify)
    canonical_record: Optional[CanonicalRecord] = None
    fingerprint: str = ""
    # Blockchain
    blockchain: Optional[BlockchainRecord] = None
    # Verification (done automatically after registration)
    verification: Optional[VerificationResult] = None
    # Error
    error: Optional[ErrorDetail] = None


class VerifyRequest(BaseModel):
    record: dict
    transaction_hash: str


class VerifyResponse(BaseModel):
    verified: bool
    local_fingerprint: str
    onchain_fingerprint: Optional[str] = None
    transaction_hash: str
    registered_at: Optional[int] = None
    reason: str


class HealthResponse(BaseModel):
    status: str
    services: dict


class TransactionInfo(BaseModel):
    transaction_hash: str
    fingerprint: Optional[str] = None
    confirmed: bool
    block_number: Optional[int] = None
    registered_at: Optional[int] = None
    network: str = "Ethereum Sepolia"
