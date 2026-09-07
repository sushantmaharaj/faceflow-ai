"""
FaceFlow AI — Canonical JSON & SHA-256 Fingerprinting
Deterministic, field-order-independent content fingerprinting.
"""

import json
import hashlib
from typing import Any


def canonicalize(record: dict[str, Any]) -> str:
    """
    Produce a deterministic JSON string from a dict.
    - Keys sorted recursively
    - Compact separators (no extra spaces)
    - UTF-8 safe (non-ASCII preserved, not escaped)
    - No timestamps, no random values
    """
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_fingerprint(canonical_json: str) -> str:
    """
    Return the SHA-256 hex digest of a canonical JSON string encoded as UTF-8.
    This is the content fingerprint that gets registered on-chain.
    """
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def fingerprint_record(record: dict[str, Any]) -> tuple[str, str]:
    """
    Convenience: canonicalize + fingerprint in one call.
    Returns (canonical_json, fingerprint_hex).
    """
    canonical = canonicalize(record)
    fingerprint = sha256_fingerprint(canonical)
    return canonical, fingerprint


def fingerprint_to_bytes32(fingerprint_hex: str) -> bytes:
    """Convert a 64-char hex fingerprint to a 32-byte value for Ethereum."""
    return bytes.fromhex(fingerprint_hex)
