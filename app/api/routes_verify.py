"""
FaceFlow AI — Verification Routes
POST /api/verify
GET  /api/transaction/{tx_hash}
"""

from fastapi import APIRouter, HTTPException
from app.models.schemas import VerifyRequest, VerifyResponse, TransactionInfo
from app.services.verification_service import verify_record_against_chain
from app.services.blockchain_service import get_blockchain_registry
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["Verification"])


@router.post("/verify", response_model=VerifyResponse)
async def verify_record(request: VerifyRequest) -> VerifyResponse:
    """
    Independent verification endpoint.
    Recalculates fingerprint from the supplied record and compares with
    the fingerprint stored in the given blockchain transaction.

    Supports tampering demonstration — modify any field in 'record' and
    the fingerprint will not match the on-chain hash.
    """
    logger.info("Verification request for TX %s", request.transaction_hash)

    try:
        result = await verify_record_against_chain(
            record_dict=request.record,
            tx_hash=request.transaction_hash,
        )
    except Exception as e:
        logger.error("Verification error: %s", e)
        raise HTTPException(status_code=500, detail={
            "code": "VERIFICATION_FAILED",
            "message": "Verification could not be completed."
        })

    return VerifyResponse(
        verified=result.verified,
        local_fingerprint=result.local_fingerprint,
        onchain_fingerprint=result.onchain_fingerprint,
        transaction_hash=result.transaction_hash or request.transaction_hash,
        registered_at=result.registered_at,
        reason=result.reason,
    )


@router.get("/transaction/{tx_hash}", response_model=TransactionInfo)
async def get_transaction(tx_hash: str) -> TransactionInfo:
    """
    Look up a blockchain transaction and return the stored fingerprint.
    Useful for manual inspection and auditing.
    """
    registry = get_blockchain_registry()
    try:
        fingerprint = await registry.get_registered_fingerprint(tx_hash)
        confirmed = fingerprint is not None

        registered_at = None
        if fingerprint:
            _, ts = await registry.is_registered(fingerprint)
            registered_at = ts

        return TransactionInfo(
            transaction_hash=tx_hash,
            fingerprint=fingerprint,
            confirmed=confirmed,
            registered_at=registered_at,
        )
    except Exception as e:
        logger.error("TX lookup error %s: %s", tx_hash, e)
        raise HTTPException(status_code=500, detail={
            "code": "BLOCKCHAIN_RPC_ERROR",
            "message": "Could not retrieve transaction data."
        })
