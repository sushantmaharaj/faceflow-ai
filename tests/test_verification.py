"""
Tests for verification logic (mocked blockchain).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.utils.canonical_json import fingerprint_record


SAMPLE_RECORD = {
    "schema_version": "1",
    "source_url": "https://example.com/post/1",
    "source_title": "Sample Post",
    "source_domain": "example.com",
    "image_url": "https://example.com/img.jpg",
    "search_engine": "google_lens",
    "search_result_type": "visual_match",
    "face_similarity": 0.84,
}


@pytest.mark.asyncio
async def test_verify_matching_fingerprint():
    """Registered fingerprint A → verify with same record → VERIFIED."""
    _, fp = fingerprint_record(SAMPLE_RECORD)

    mock_registry = AsyncMock()
    mock_registry.get_registered_fingerprint.return_value = fp
    mock_registry.is_registered.return_value = (True, 1700000000)

    with patch("app.services.verification_service.get_blockchain_registry", return_value=mock_registry):
        from app.services.verification_service import verify_record_against_chain
        result = await verify_record_against_chain(SAMPLE_RECORD, "0xabc123")

    assert result.verified is True
    assert result.reason == "MATCH"
    assert result.local_fingerprint == fp
    assert result.onchain_fingerprint == fp


@pytest.mark.asyncio
async def test_verify_tampered_record():
    """Registered fingerprint A → verify with modified record → NOT VERIFIED."""
    _, original_fp = fingerprint_record(SAMPLE_RECORD)

    mock_registry = AsyncMock()
    mock_registry.get_registered_fingerprint.return_value = original_fp
    mock_registry.is_registered.return_value = (True, 1700000000)

    tampered_record = dict(SAMPLE_RECORD)
    tampered_record["source_title"] = "TAMPERED TITLE"

    with patch("app.services.verification_service.get_blockchain_registry", return_value=mock_registry):
        from app.services.verification_service import verify_record_against_chain
        result = await verify_record_against_chain(tampered_record, "0xabc123")

    assert result.verified is False
    assert result.reason == "FINGERPRINT_MISMATCH"
    assert result.local_fingerprint != result.onchain_fingerprint


@pytest.mark.asyncio
async def test_verify_unregistered_fingerprint():
    """TX not found → NOT REGISTERED."""
    mock_registry = AsyncMock()
    mock_registry.get_registered_fingerprint.return_value = None

    with patch("app.services.verification_service.get_blockchain_registry", return_value=mock_registry):
        from app.services.verification_service import verify_record_against_chain
        result = await verify_record_against_chain(SAMPLE_RECORD, "0xdead")

    assert result.verified is False
    assert result.reason == "INVALID_TRANSACTION"


@pytest.mark.asyncio
async def test_verify_blockchain_unavailable():
    """Blockchain RPC error → BLOCKCHAIN_UNAVAILABLE."""
    mock_registry = AsyncMock()
    mock_registry.get_registered_fingerprint.side_effect = RuntimeError("RPC down")

    with patch("app.services.verification_service.get_blockchain_registry", return_value=mock_registry):
        from app.services.verification_service import verify_record_against_chain
        result = await verify_record_against_chain(SAMPLE_RECORD, "0xfail")

    assert result.verified is False
    assert result.reason == "BLOCKCHAIN_UNAVAILABLE"


@pytest.mark.asyncio
async def test_different_records_different_fingerprints():
    """Two different records produce different fingerprints → correct mismatch detection."""
    record_a = dict(SAMPLE_RECORD)
    record_b = dict(SAMPLE_RECORD, source_title="Different Title")

    _, fp_a = fingerprint_record(record_a)
    _, fp_b = fingerprint_record(record_b)

    assert fp_a != fp_b
