"""
FaceFlow AI — Search Service
Uploads image to catbox.moe (free, no auth) to get a public URL,
then queries SerpApi Google Lens with that URL.
"""

from __future__ import annotations

import abc

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import SearchResult
from app.utils.image import compress_for_serpapi

logger = get_logger(__name__)

CATBOX_UPLOAD_URL = "https://catbox.moe/user/api.php"
SERPAPI_SEARCH_URL = "https://serpapi.com/search"


# ── Abstract interface ───────────────────────────────────────

class SearchProvider(abc.ABC):
    @abc.abstractmethod
    async def search(self, image_bytes: bytes) -> list[SearchResult]:
        """Perform reverse-image search. Return normalized SearchResult list."""
        ...

    async def health_check(self) -> bool:
        return True


# ── SerpApi Google Lens implementation ───────────────────────

class SerpApiGoogleLensProvider(SearchProvider):
    """
    Two-step pipeline:
      1. Upload compressed image to catbox.moe → public URL (free, no auth)
      2. Pass URL to SerpApi Google Lens → get visual matches
    """

    def __init__(self) -> None:
        self._api_key = settings.serpapi_api_key

    async def search(self, image_bytes: bytes) -> list[SearchResult]:
        if not settings.serpapi_configured:
            raise RuntimeError("SEARCH_API_ERROR: SerpApi key not configured.")

        compressed = compress_for_serpapi(image_bytes)
        logger.info("Image compressed to %d KB", len(compressed) // 1024)

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            # Step 1: get a public URL via catbox.moe
            image_url = await self._upload_to_catbox(client, compressed)
            logger.info("Image hosted at: %s", image_url)

            # Step 2: query SerpApi Google Lens with that URL
            raw = await self._query_lens(client, image_url)

        return self._normalize_results(raw)

    async def _upload_to_catbox(self, client: httpx.AsyncClient, image_bytes: bytes) -> str:
        """Upload image to catbox.moe. Returns a public HTTPS URL. Free, no API key needed."""
        try:
            resp = await client.post(
                CATBOX_UPLOAD_URL,
                data={"reqtype": "fileupload"},
                files={"fileToUpload": ("image.jpg", image_bytes, "image/jpeg")},
            )
            resp.raise_for_status()
            url = resp.text.strip()
            if not url.startswith("http"):
                raise RuntimeError(f"Unexpected catbox response: {url[:120]}")
            return url
        except httpx.HTTPStatusError as e:
            logger.error("catbox.moe upload error %s: %s", e.response.status_code, e.response.text[:200])
            raise RuntimeError("SEARCH_API_ERROR: Image hosting (catbox.moe) failed") from e
        except httpx.RequestError as e:
            logger.error("catbox.moe request error: %s", e)
            raise RuntimeError("SEARCH_API_ERROR: Cannot reach catbox.moe") from e

    async def _query_lens(self, client: httpx.AsyncClient, image_url: str) -> dict:
        """Query SerpApi Google Lens with a public image URL."""
        try:
            resp = await client.get(
                SERPAPI_SEARCH_URL,
                params={
                    "engine": "google_lens",
                    "url": image_url,
                    "api_key": self._api_key,
                },
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("SerpApi Lens error %s: %s", e.response.status_code, e.response.text[:300])
            raise RuntimeError(f"SEARCH_API_ERROR: Lens query failed ({e.response.status_code})") from e
        except httpx.RequestError as e:
            logger.error("SerpApi request error: %s", e)
            raise RuntimeError("SEARCH_API_ERROR: Cannot reach SerpApi") from e

    def _normalize_results(self, raw: dict) -> list[SearchResult]:
        results: list[SearchResult] = []
        position = 0

        for item in raw.get("exact_matches", []):
            position += 1
            results.append(self._parse_item(item, position, "exact_match"))

        for item in raw.get("visual_matches", []):
            position += 1
            results.append(self._parse_item(item, position, "visual_match"))

        logger.info(
            "SerpApi returned %d exact + %d visual matches",
            len(raw.get("exact_matches", [])),
            len(raw.get("visual_matches", [])),
        )
        return results[: settings.search_max_candidates]

    @staticmethod
    def _parse_item(item: dict, position: int, result_type: str) -> SearchResult:
        return SearchResult(
            title=str(item.get("title", "") or ""),
            source=str(item.get("source", "") or ""),
            url=str(item.get("link", "") or item.get("url", "") or ""),
            thumbnail_url=str(item.get("thumbnail", "") or ""),
            image_url=str(item.get("image", "") or item.get("image_url", "") or ""),
            position=position,
            result_type=result_type,
        )

    async def health_check(self) -> bool:
        if not settings.serpapi_configured:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://serpapi.com/account",
                    params={"api_key": self._api_key},
                )
                return resp.status_code == 200
        except Exception:
            return False


# ── Singleton ────────────────────────────────────────────────
_provider: SearchProvider | None = None


def get_search_provider() -> SearchProvider:
    global _provider
    if _provider is None:
        _provider = SerpApiGoogleLensProvider()
    return _provider
