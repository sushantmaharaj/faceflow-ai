"""
FaceFlow AI — Verification Service
Independent re-hash + blockchain read-back comparison.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.models.schemas import VerificationResult
from app.services.blockchain_service import get_blockchain_registry
from app.utils.canonical_json import fingerprint_record

logger = get_logger(__name__)


async def verify_record_against_chain(
    record_dict: dict,
    tx_hash: str,
) -> VerificationResult:
    """
    Independent verification:
    1. Recompute SHA-256 fingerprint from the given record dict
    2. Read the fingerprint stored in the given transaction from the blockchain
    3. Compare — Equal → VERIFIED, else → FINGERPRINT_MISMATCH

    This is INDEPENDENT of the initial registration step.
    """
    # Step 1: recompute local fingerprint
    canonical_json, local_fp = fingerprint_record(record_dict)
    logger.info("Verification: local fingerprint = %s...", local_fp[:16])

    # Step 2: read on-chain fingerprint from TX
    registry = get_blockchain_registry()
    try:
        onchain_fp = await registry.get_registered_fingerprint(tx_hash)
    except Exception as e:
        logger.error("Blockchain read error during verification: %s", e)
        return VerificationResult(
            verified=False,
            local_fingerprint=local_fp,
            onchain_fingerprint=None,
            transaction_hash=tx_hash,
            registered_at=None,
            reason="BLOCKCHAIN_UNAVAILABLE",
        )

    if onchain_fp is None:
        return VerificationResult(
            verified=False,
            local_fingerprint=local_fp,
            onchain_fingerprint=None,
            transaction_hash=tx_hash,
            registered_at=None,
            reason="INVALID_TRANSACTION",
        )

    # Step 3: compare
    if local_fp.lower() == onchain_fp.lower():
        # Also check the contract's registeredAt for timestamp
        registered_at = None
        try:
            found, ts = await registry.is_registered(local_fp)
            registered_at = ts
        except Exception:
            pass

        logger.info("Verification: MATCH ✓")
        return VerificationResult(
            verified=True,
            local_fingerprint=local_fp,
            onchain_fingerprint=onchain_fp,
            transaction_hash=tx_hash,
            registered_at=registered_at,
            reason="MATCH",
        )
    else:
        logger.info(
            "Verification: MISMATCH — local=%s... onchain=%s...",
            local_fp[:16],
            onchain_fp[:16],
        )
        return VerificationResult(
            verified=False,
            local_fingerprint=local_fp,
            onchain_fingerprint=onchain_fp,
            transaction_hash=tx_hash,
            registered_at=None,
            reason="FINGERPRINT_MISMATCH",
        )
