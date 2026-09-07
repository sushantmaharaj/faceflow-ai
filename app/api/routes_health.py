"""
FaceFlow AI — Health Check Route
GET /health
"""

from fastapi import APIRouter
from app.models.schemas import HealthResponse
from app.services import face_service
from app.services.search_service import get_search_provider
from app.services.blockchain_service import get_blockchain_registry

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """
    Check application and dependency health.
    Does not fail if third-party services are down — reports them separately.
    """
    face_ok = face_service.is_model_loaded()

    try:
        search_ok = await get_search_provider().health_check()
    except Exception:
        search_ok = False

    try:
        blockchain_ok = await get_blockchain_registry().health_check()
    except Exception:
        blockchain_ok = False

    return HealthResponse(
        status="ok",
        services={
            "face_model": face_ok,
            "search_provider": search_ok,
            "blockchain_rpc": blockchain_ok,
        },
    )
